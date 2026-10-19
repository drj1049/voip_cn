"""
Audio mode: run a real audio clip through the same network model used by the
live simulator, then rebuild the audio from whatever the receiver kept.

Pipeline (offline, so it finishes instantly instead of taking real time):

  audio samples -> 20 ms frames -> one RTP-style packet per frame
      -> ImpairmentEngine (loss, delay, jitter)       same class as the live simulator
      -> RFC 3550 jitter, latency, loss, jitter buffer  same classes as the live simulator
      -> G.107 E-model MOS                             same class as the live simulator
      -> frames the receiver would actually play -> damaged audio

Lost frames and frames discarded as late by the jitter buffer become silence.
The damaged clip is kept aligned with the original so the two can be compared
by ear. The base delay therefore shows up in the MOS score, not as a shift in
the audio.
"""
import io
import math
import wave
from typing import Dict, Any, List

import numpy as np

from backend.simulation.impairment import ImpairmentEngine
from backend.metrics.jitter import RFC3550JitterCalculator
from backend.metrics.jitter_buffer import JitterBuffer
from backend.metrics.packet_loss import PacketLossCalculator
from backend.metrics.mos import MOSEstimator

SAMPLE_RATE = 8000                      # G.711 telephone audio
FRAME_SEC = 0.02                        # 20 ms per packet
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_SEC)   # 160 samples, same as PacketGenerator
MAX_SECONDS = 30.0

# Frame outcomes used in the "frames" string returned to the dashboard
PLAYED, LOST, LATE = "0", "1", "2"


def decode_wav(data: bytes) -> np.ndarray:
    """Reads WAV bytes and returns mono 8 kHz 16-bit samples."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wf:
            channels = wf.getnchannels()
            width = wf.getsampwidth()
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
    except (wave.Error, EOFError):
        raise ValueError("Not a valid WAV file (PCM WAV expected)")

    if width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0) * 256.0
    elif width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    elif width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 65536.0
    else:
        raise ValueError("Only 8, 16 and 32-bit PCM WAV files are supported")

    if channels > 1:
        usable = (len(samples) // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)

    if rate != SAMPLE_RATE and len(samples) > 0:
        if rate > SAMPLE_RATE:
            # Crude low-pass (moving average) before dropping samples, to limit aliasing
            k = max(1, int(round(rate / SAMPLE_RATE)))
            samples = np.convolve(samples, np.ones(k) / k, mode="same")
        new_len = int(len(samples) * SAMPLE_RATE / rate)
        old_t = np.arange(len(samples)) / rate
        new_t = np.arange(new_len) / SAMPLE_RATE
        samples = np.interp(new_t, old_t, samples)

    if len(samples) / SAMPLE_RATE > MAX_SECONDS:
        raise ValueError(f"Clip is too long (maximum {int(MAX_SECONDS)} seconds)")
    if len(samples) < FRAME_SAMPLES:
        raise ValueError("Clip is too short (at least 20 ms needed)")

    return np.clip(np.round(samples), -32768, 32767).astype(np.int16)


def encode_wav(samples: np.ndarray) -> bytes:
    """Writes mono 8 kHz 16-bit samples to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(np.asarray(samples, dtype="<i2").tobytes())
    return buf.getvalue()


def make_demo_clip(seconds: float = 8.0) -> np.ndarray:
    """
    Built-in test clip so the feature works without uploading anything:
    a short rising and falling melody with a soft attack on every note.
    Gaps are easy to hear in it.
    """
    notes = [262, 330, 392, 523, 392, 330, 262, 330, 392, 523, 659, 523, 392, 330, 262, 196]
    note_sec = seconds / len(notes)
    n = int(SAMPLE_RATE * note_sec)
    t = np.arange(n) / SAMPLE_RATE
    envelope = np.minimum(1.0, t / 0.02) * np.minimum(1.0, (note_sec - t) / 0.05)
    parts = []
    for f in notes:
        tone = np.sin(2 * math.pi * f * t) + 0.3 * np.sin(2 * math.pi * 2 * f * t)
        parts.append(tone * envelope)
    wave_data = np.concatenate(parts)
    wave_data = wave_data / np.max(np.abs(wave_data)) * 0.6 * 32767
    return np.round(wave_data).astype(np.int16)


def _score(avg_latency: float, jitter_ms: float, loss_pct: float, burst_ratio: float,
           buffer: JitterBuffer, final: bool = True) -> Dict[str, Any]:
    """Same MOS branching as VoIPSimulator.get_current_metrics, for a finished run."""
    if buffer.mode == "off":
        late_pct = 0.0
        effective_loss = loss_pct
        playout_delay = avg_latency
        mos = MOSEstimator.get_metrics(avg_latency, jitter_ms, loss_pct, burst_ratio)
    else:
        late_pct = buffer.late_pct(final)
        effective_loss = 100.0 * (1.0 - (1.0 - loss_pct / 100.0) * (1.0 - late_pct / 100.0))
        playout_delay = buffer.playout_delay_ms()
        mos = MOSEstimator.get_metrics(playout_delay, 0.0, effective_loss, burst_ratio)
    return {
        "late_pct": late_pct,
        "effective_loss": effective_loss,
        "playout_delay": playout_delay,
        "mos": mos["mos"],
        "r_factor": mos["r_factor"],
        "quality": mos["quality"],
    }


def process_audio(samples: np.ndarray,
                  delay_ms: float = 20.0,
                  jitter_ms: float = 2.0,
                  packet_loss_pct: float = 0.0,
                  loss_mode: str = "random",
                  burst_length: float = 5.0,
                  buffer_mode: str = "fixed",
                  buffer_ms: float = 40.0) -> Dict[str, Any]:
    """
    Sends the clip through the simulated network and returns metrics, the
    per-frame outcome string, and the damaged audio as WAV bytes.
    """
    samples = np.asarray(samples, dtype=np.int16)
    n_frames = int(math.ceil(len(samples) / FRAME_SAMPLES))
    padded = np.zeros(n_frames * FRAME_SAMPLES, dtype=np.int16)
    padded[:len(samples)] = samples
    frames = padded.reshape(n_frames, FRAME_SAMPLES)

    engine = ImpairmentEngine(delay_ms=delay_ms, jitter_ms=jitter_ms, packet_loss_pct=packet_loss_pct)
    engine.update_config(loss_mode=loss_mode, burst_length=burst_length)

    loss_calc = PacketLossCalculator()
    jitter_calc = RFC3550JitterCalculator()
    buffer = JitterBuffer(mode=buffer_mode, fixed_ms=buffer_ms)

    # 1. Build one packet per frame on a virtual clock (no real waiting) and apply the network
    arrived: List[Dict[str, Any]] = []
    for i in range(n_frames):
        send_time = i * FRAME_SEC
        packet = {
            "sequence_number": (i + 1) % 65536,
            "timestamp": (i * FRAME_SAMPLES) % (2 ** 32),
            "send_time": send_time,
            "payload_size": FRAME_SAMPLES,
            "frame_index": i,
        }
        loss_calc.record_sent()
        out = engine.process_packet(packet)
        if out is None:
            continue                      # lost in the network
        out["receive_time"] = send_time + out["simulated_delay_sec"]
        arrived.append(out)

    # 2. The receiver sees packets in arrival order (jitter can reorder them)
    arrived.sort(key=lambda p: (p["receive_time"], p["frame_index"]))

    status = [LOST] * n_frames
    transit_ms: List[float] = []
    for p in arrived:
        loss_calc.add_received_packet(p)
        jitter_now = jitter_calc.add_packet(p)
        on_time = buffer.process(p, jitter_now)
        transit_ms.append((p["receive_time"] - p["send_time"]) * 1000.0)
        status[p["frame_index"]] = PLAYED if on_time else LATE

    # 3. Metrics, using the same classes and formulas as the live simulator
    loss_data = loss_calc.get_metrics(True)
    burst_ratio = loss_calc.get_burst_ratio(True)
    avg_latency = float(np.mean(transit_ms)) if transit_ms else 0.0
    max_latency = float(np.max(transit_ms)) if transit_ms else 0.0
    jitter_val = jitter_calc.get_jitter_ms()
    score = _score(avg_latency, jitter_val, loss_data["loss_percentage"], burst_ratio, buffer)

    # 4. Rebuild the audio: silence wherever the receiver has nothing to play
    damaged = frames.copy()
    for i, s in enumerate(status):
        if s != PLAYED:
            damaged[i, :] = 0
    damaged = damaged.reshape(-1)[:len(samples)]

    return {
        "settings": {
            "delay_ms": delay_ms, "jitter_ms": jitter_ms, "packet_loss_pct": packet_loss_pct,
            "loss_mode": loss_mode, "burst_length": burst_length,
            "buffer_mode": buffer_mode, "buffer_ms": buffer_ms,
        },
        "metrics": {
            "packets_sent": loss_data["packets_sent"],
            "packets_received": loss_data["packets_received"],
            "packets_lost": status.count(LOST),
            "packets_late": status.count(LATE),
            "network_loss_pct": round(loss_data["loss_percentage"], 2),
            "late_pct": round(score["late_pct"], 2),
            "effective_loss_pct": round(score["effective_loss"], 2),
            "latency_avg": round(avg_latency, 2),
            "latency_max": round(max_latency, 2),
            "jitter": round(jitter_val, 2),
            "playout_delay": round(score["playout_delay"], 1),
            "mos": score["mos"],
            "r_factor": score["r_factor"],
            "quality": score["quality"],
        },
        "frames": "".join(status),
        "duration_sec": round(len(samples) / SAMPLE_RATE, 2),
        "original_wav": encode_wav(samples),
        "damaged_wav": encode_wav(damaged),
    }
