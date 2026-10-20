"""
Replay a captured real call through the same metric pipeline the simulator uses.

ReplaySimulator is a VoIPSimulator whose packets come from a recording instead of a packet
generator. Everything after the packets arrive (latency, RFC 3550 jitter, loss, burst ratio,
jitter buffer, E-model, MOS) is the SAME code the live simulator runs.

The impairment sliders still work, but now they add EXTRA delay, jitter and loss on top of
whatever the real call already had. At 0 / 0 / 0 you are looking at the call exactly as recorded.
"""
import heapq
import os
import re
import threading
from typing import Any, Dict, List, Optional

import time

from backend.replay.pcap_reader import (
    CaptureError, ReplayPacket, choose_default_stream, prepare_replay, read_rtp_streams,
)
from backend.simulation.simulator import VoIPSimulator

CAPTURE_EXTENSIONS = (".pcap", ".pcapng", ".cap")


# --------------------------------------------------------------------------------------
# Capture files on disk
# --------------------------------------------------------------------------------------

def capture_dir() -> str:
    """Folder that holds capture files. Defaults to <project>/captures, override with CAPTURE_DIR."""
    default = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "captures")
    return os.environ.get("CAPTURE_DIR", default)


def safe_capture_name(name: str) -> str:
    """Keeps only a plain file name (no folders, no odd characters) and checks the extension."""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base)
    if not base or base.startswith("."):
        raise ValueError("Give the capture a file name.")
    if not base.lower().endswith(CAPTURE_EXTENSIONS):
        raise ValueError("Capture files must end in .pcap, .pcapng or .cap")
    return base


def capture_path(name: str) -> str:
    folder = os.path.abspath(capture_dir())
    path = os.path.abspath(os.path.join(folder, safe_capture_name(name)))
    if os.path.dirname(path) != folder:
        raise ValueError("Invalid capture name.")
    return path


def list_captures() -> List[Dict[str, Any]]:
    folder = capture_dir()
    if not os.path.isdir(folder):
        return []
    out = []
    for fname in sorted(os.listdir(folder)):
        if fname.lower().endswith(CAPTURE_EXTENSIONS):
            out.append({"name": fname, "size_bytes": os.path.getsize(os.path.join(folder, fname))})
    return out


def summarize_capture(data: bytes) -> Dict[str, Any]:
    """Lists the RTP streams in a capture and which one would be replayed by default."""
    streams = read_rtp_streams(data)
    if not streams:
        raise CaptureError(
            "No RTP audio was found in this capture. Record a call that uses RTP over UDP "
            "(most VoIP and WebRTC calls do) and make sure the capture includes the media packets."
        )
    default = choose_default_stream(streams)
    listing = sorted((s.summary() for s in streams.values()), key=lambda s: -s["packets"])
    return {"streams": listing, "default_ssrc": default.ssrc if default else None}


# --------------------------------------------------------------------------------------
# The replayer
# --------------------------------------------------------------------------------------

class ReplaySimulator(VoIPSimulator):
    """Same interface as VoIPSimulator, but fed from a recorded capture."""

    def __init__(self):
        super().__init__()
        # Extra impairment starts switched off, so a fresh replay shows the real call untouched
        self.impairment.update_config(0.0, 0.0, 0.0, "random", 5.0)
        self.packets: List[ReplayPacket] = []
        self.capture_name: Optional[str] = None
        self.stream_info: Dict[str, Any] = {}
        self.speed: float = 1.0
        self._duration: float = 0.0
        self._position: float = 0.0       # how far into the recording we are, in seconds
        self._finished: bool = False
        self._feed_thread: Optional[threading.Thread] = None
        self._first_ext: Optional[int] = None
        self._max_ext: Optional[int] = None

    # ---- loading -----------------------------------------------------------------

    def load_capture(self, name: str, data: bytes, ssrc: Optional[int] = None,
                     base_delay_ms: float = 40.0, speed: float = 1.0) -> Dict[str, Any]:
        """Parses a capture, picks the voice stream and prepares it. Returns a description of it."""
        self.stop()
        streams = read_rtp_streams(data)
        if not streams:
            raise CaptureError("No RTP audio was found in this capture.")
        if ssrc is not None:
            matches = [s for s in streams.values() if s.ssrc == ssrc]
            if not matches:
                raise CaptureError(f"No stream with SSRC {ssrc} in this capture.")
            stream = max(matches, key=lambda s: len(s.packets))
        else:
            stream = choose_default_stream(streams)

        packets, info = prepare_replay(stream, base_delay_ms)
        summary = stream.summary()
        summary.update(info)
        with self._lock:
            self.packets = packets
            self.capture_name = name
            self.stream_info = summary
            self.speed = max(0.25, min(100.0, float(speed)))
            self._duration = packets[-1].arrival if packets else 0.0
            self._clear_metrics_locked()
        return summary

    # ---- control -----------------------------------------------------------------

    def start(self) -> bool:
        """Starts (or restarts) the replay from the beginning of the recording."""
        with self._lock:
            if self.is_running or not self.packets:
                return False
            self._clear_metrics_locked()
            self.is_running = True
            self._sender_active = True
            self._feed_thread = threading.Thread(target=self._feed_loop, daemon=True)
            self._feed_thread.start()
            return True

    def stop(self) -> bool:
        with self._lock:
            if not self.is_running:
                return False
            self.is_running = False
        thread = self._feed_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        return True

    def reset(self):
        was_running = self.is_running
        if was_running:
            self.stop()
        with self._lock:
            self._clear_metrics_locked()
        if was_running:
            self.start()

    def _clear_metrics_locked(self):
        """Wipes every counter. The caller must already hold the lock."""
        self.latency_calc.reset()
        self.packet_loss_calc.reset()
        self.jitter_calc.reset()
        self.jitter_buffer.reset()
        self.impairment.reset_state()
        self._first_ext = None
        self._max_ext = None
        self._position = 0.0
        self._finished = False

    # ---- the replay loop ---------------------------------------------------------

    def _count_sent(self, ext_seq: int):
        """'Sent' means every sequence number the sender used, up to the highest one seen so far."""
        if self._first_ext is None:
            self._first_ext = self._max_ext = ext_seq
        elif ext_seq > self._max_ext:
            self._max_ext = ext_seq
        target = self._max_ext - self._first_ext + 1
        if target > self.packet_loss_calc.packets_sent:
            self.packet_loss_calc.packets_sent = target

    def _feed_loop(self):
        packets = self.packets
        total = len(packets)
        index = 0
        in_flight: list = []          # packets delayed by extra impairment, ordered by delivery time
        order = 0
        wall_start = time.monotonic()

        while True:
            with self._lock:
                if not self.is_running or not self._sender_active:
                    return            # stopped by the user
                speed = self.speed
            now = (time.monotonic() - wall_start) * speed   # position in the recording, seconds
            self._position = now

            # 1. Packets whose recorded arrival time has been reached
            while index < total and packets[index].arrival <= now:
                p = packets[index]
                index += 1
                raw = {"sequence_number": p.seq, "timestamp": p.timestamp,
                       "send_time": p.send_time, "payload_size": p.payload_len}
                with self._lock:
                    self._count_sent(p.ext_seq)
                    impaired = self.impairment.process_packet(raw)   # may drop it or add extra delay
                if impaired is None:
                    continue
                order += 1
                heapq.heappush(in_flight, (p.arrival + impaired["simulated_delay_sec"], order, p))

            # 2. Deliver everything whose (possibly delayed) arrival time has been reached
            while in_flight and in_flight[0][0] <= now:
                arrival, _, p = heapq.heappop(in_flight)
                pkt = {"sequence_number": p.seq, "timestamp": p.timestamp, "send_time": p.send_time,
                       "payload_size": p.payload_len, "receive_time": arrival}
                with self._lock:
                    # exactly what the live receiver does with every arriving packet
                    self.latency_calc.add_packet(pkt)
                    self.packet_loss_calc.add_received_packet(pkt)
                    jitter_now = self.jitter_calc.add_packet(pkt)
                    self.jitter_buffer.process(pkt, jitter_now)

            if index >= total and not in_flight:
                break
            time.sleep(0.004)

        with self._lock:
            self._position = self._duration
            self._finished = True
            self.is_running = False
            self._sender_active = False

    # ---- reporting ---------------------------------------------------------------

    def get_current_metrics(self) -> Dict[str, Any]:
        data = super().get_current_metrics()
        with self._lock:
            if not self.packets:
                state = "empty"
            elif self._finished:
                state = "finished"
            elif self.is_running:
                state = "playing"
            else:
                state = "stopped"
            progress = (self._position / self._duration) if self._duration > 0 else 0.0
            data.update({
                "source": "replay",
                "replay_state": state,
                "capture": self.capture_name,
                "stream": self.stream_info,
                "progress": round(min(1.0, max(0.0, progress)), 3),
                "position_s": round(min(self._position, self._duration), 1),
                "duration_s": round(self._duration, 1),
                "speed": self.speed,
                "assumed_base_delay_ms": self.stream_info.get("assumed_base_delay_ms"),
            })
        return data
