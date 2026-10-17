"""
VoIP Network Simulator Controller
Manages background packet transmission/reception threads and metrics aggregation.
"""
import time
import threading
from typing import Dict, Any, Optional

from backend.config import config
from backend.simulation.packet_generator import PacketGenerator
from backend.simulation.impairment import ImpairmentEngine
from backend.simulation.udp_sender import UDPSender
from backend.simulation.udp_receiver import UDPReceiver

from backend.metrics.latency import LatencyCalculator
from backend.metrics.packet_loss import PacketLossCalculator
from backend.metrics.jitter import RFC3550JitterCalculator
from backend.metrics.jitter_buffer import JitterBuffer
from backend.metrics.mos import MOSEstimator

class VoIPSimulator:
    """
    Main Simulation Controller orchestrating:
    Packet Generator -> Impairment Engine -> UDP Sender -> UDP Receiver -> Metrics Engine
    """

    def __init__(self, target_ip: str = config.UDP_IP, target_port: int = config.UDP_PORT):
        self.target_ip: str = target_ip
        self.target_port: int = target_port

        # Components initialization
        self.generator = PacketGenerator()
        self.impairment = ImpairmentEngine(
            delay_ms=config.DEFAULT_DELAY_MS,
            jitter_ms=config.DEFAULT_JITTER_MS,
            packet_loss_pct=config.DEFAULT_PACKET_LOSS_PCT
        )
        self.sender: Optional[UDPSender] = None
        self.receiver: Optional[UDPReceiver] = None

        # Metrics Engines
        self.latency_calc = LatencyCalculator()
        self.packet_loss_calc = PacketLossCalculator()
        self.jitter_calc = RFC3550JitterCalculator()
        self.jitter_buffer = JitterBuffer()

        # Threading state control
        self.is_running: bool = False
        self._sender_thread: Optional[threading.Thread] = None
        self._receiver_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def update_config(self, delay_ms: Optional[float] = None, jitter_ms: Optional[float] = None, packet_loss_pct: Optional[float] = None,
                      loss_mode: Optional[str] = None, burst_length: Optional[float] = None,
                      buffer_mode: Optional[str] = None, buffer_ms: Optional[float] = None):
        """Updates impairment engine and jitter buffer parameters in real time."""
        with self._lock:
            self.impairment.update_config(delay_ms, jitter_ms, packet_loss_pct, loss_mode, burst_length)
            self.jitter_buffer.configure(buffer_mode, buffer_ms)

    def get_config(self) -> Dict[str, float]:
        """Returns current impairment settings."""
        with self._lock:
            return {
                "delay_ms": self.impairment.delay_ms,
                "jitter_ms": self.impairment.jitter_ms,
                "packet_loss_pct": self.impairment.packet_loss_pct,
                "loss_mode": self.impairment.loss_mode,
                "burst_length": self.impairment.burst_length,
                "buffer_mode": self.jitter_buffer.mode,
                "buffer_ms": self.jitter_buffer.fixed_ms
            }

    def start(self) -> bool:
        """Starts the local UDP sender and receiver threads."""
        with self._lock:
            if self.is_running:
                return False

            self.sender = UDPSender(self.target_ip, self.target_port)
            self.receiver = UDPReceiver(self.target_ip, self.target_port)

            self.is_running = True
            self._sender_active = True
            self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
            self._receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)

            self._receiver_thread.start()
            self._sender_thread.start()
            return True

    def stop(self) -> bool:
        """Stops simulation threads and cleans up sockets."""
        with self._lock:
            if not self.is_running:
                return False

            self.is_running = False

        if self._sender_thread and self._sender_thread.is_alive():
            self._sender_thread.join(timeout=1.0)

        if self._receiver_thread and self._receiver_thread.is_alive():
            self._receiver_thread.join(timeout=1.0)

        with self._lock:
            if self.sender:
                self.sender.close()
                self.sender = None
            if self.receiver:
                self.receiver.close()
                self.receiver = None

        return True

    def stop_sender(self):
        """Stops the packet generator thread while keeping the receiver active to drain in-flight packets."""
        with self._lock:
            self._sender_active = False

        if self._sender_thread and self._sender_thread.is_alive():
            self._sender_thread.join(timeout=1.0)

    def reset(self):
        """Resets all simulation counters and metric history."""
        was_running = self.is_running
        if was_running:
            self.stop()

        with self._lock:
            self.generator.reset()
            self.latency_calc.reset()
            self.packet_loss_calc.reset()
            self.jitter_calc.reset()
            self.jitter_buffer.reset()
            self.impairment.reset_state()

        if was_running:
            self.start()

    def _sender_loop(self):
        """Background thread generating and sending synthetic voice packets over UDP."""
        while True:
            with self._lock:
                if not self.is_running or not getattr(self, '_sender_active', True):
                    break
                
                # 1. Generate synthetic RTP packet
                raw_packet = self.generator.generate_packet()
                self.packet_loss_calc.record_sent()

                # 2. Process through Network Impairment Engine
                impaired_packet = self.impairment.process_packet(raw_packet)
                
                sender_ref = self.sender

            # Send impaired packet asynchronously if not dropped so 50Hz frame pacing is maintained
            if impaired_packet is not None and sender_ref is not None:
                threading.Thread(
                    target=self._dispatch_delayed_packet,
                    args=(impaired_packet, sender_ref),
                    daemon=True
                ).start()

            # Maintain frame pacing (20ms interval = 50 Hz)
            time.sleep(config.PACKET_INTERVAL_SEC)

    def _dispatch_delayed_packet(self, packet: Dict[str, Any], sender: UDPSender):
        """Dispatches packet over UDP after simulated network delay."""
        send_delay = packet.get("simulated_delay_sec", 0.0)
        if send_delay > 0:
            time.sleep(send_delay)
        try:
            sender.send_packet(packet)
        except Exception:
            pass

    def _receiver_loop(self):
        """Background thread receiving packets from UDP socket and updating metrics."""
        while True:
            with self._lock:
                if not self.is_running:
                    break
                receiver_ref = self.receiver

            if receiver_ref is None:
                break

            packet = receiver_ref.receive_packet()
            if packet is not None:
                with self._lock:
                    # Update metrics engines
                    self.latency_calc.add_packet(packet)
                    self.packet_loss_calc.add_received_packet(packet)
                    jitter_now = self.jitter_calc.add_packet(packet)
                    self.jitter_buffer.process(packet, jitter_now)

    def get_current_metrics(self) -> Dict[str, Any]:
        """Returns compiled snapshot of metrics for frontend WebSocket/REST API."""
        with self._lock:
            latency_data = self.latency_calc.get_metrics()
            # In-flight packets only count as lost once the stream has ended
            # (sender stopped or simulation stopped) and they have had time to arrive.
            final = (not self.is_running) or (not getattr(self, '_sender_active', True))
            loss_data = self.packet_loss_calc.get_metrics(final)
            jitter_data = self.jitter_calc.get_metrics()
            burst_ratio = self.packet_loss_calc.get_burst_ratio(final)

            avg_latency = latency_data["avg_ms"]
            jitter_ms = jitter_data["jitter_ms"]
            loss_pct = loss_data["loss_percentage"]

            buf = self.jitter_buffer
            if buf.mode == "off":
                # No buffer: use measured latency, jitter and network loss directly
                late_pct = 0.0
                effective_loss = loss_pct
                playout_delay = avg_latency
                mos_data = MOSEstimator.get_metrics(avg_latency, jitter_ms, loss_pct, burst_ratio)
            else:
                # Buffer on: late packets are discarded (counted as loss) and the
                # listener hears a steady playout delay, so jitter itself is no
                # longer added to the delay.
                late_pct = buf.late_pct(final)
                effective_loss = 100.0 * (1.0 - (1.0 - loss_pct / 100.0) * (1.0 - late_pct / 100.0))
                playout_delay = buf.playout_delay_ms()
                mos_data = MOSEstimator.get_metrics(playout_delay, 0.0, effective_loss, burst_ratio)

            return {
                "timestamp": time.time(),
                "status": "RUNNING" if self.is_running else "STOPPED",
                "latency": latency_data["current_ms"],
                "latency_avg": latency_data["avg_ms"],
                "latency_min": latency_data["min_ms"],
                "latency_max": latency_data["max_ms"],
                "jitter": jitter_data["jitter_ms"],
                "packet_loss": loss_data["loss_percentage"],
                "packets_sent": loss_data["packets_sent"],
                "packets_received": loss_data["packets_received"],
                "packets_lost": loss_data["packets_lost"],
                "burst_ratio": round(burst_ratio, 2),
                "buffer_mode": buf.mode,
                "buffer_ms": round(buf.current_ms, 1),
                "late_pct": round(late_pct, 2),
                "effective_loss": round(effective_loss, 2),
                "playout_delay": round(playout_delay, 1),
                "mos": mos_data["mos"],
                "r_factor": mos_data["r_factor"],
                "quality": mos_data["quality"]
            }
