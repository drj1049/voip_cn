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

        # Threading state control
        self.is_running: bool = False
        self._sender_thread: Optional[threading.Thread] = None
        self._receiver_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def update_config(self, delay_ms: Optional[float] = None, jitter_ms: Optional[float] = None, packet_loss_pct: Optional[float] = None):
        """Updates impairment engine parameters in real time."""
        with self._lock:
            self.impairment.update_config(delay_ms, jitter_ms, packet_loss_pct)

    def get_config(self) -> Dict[str, float]:
        """Returns current impairment settings."""
        with self._lock:
            return {
                "delay_ms": self.impairment.delay_ms,
                "jitter_ms": self.impairment.jitter_ms,
                "packet_loss_pct": self.impairment.packet_loss_pct
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
                    self.jitter_calc.add_packet(packet)

    def get_current_metrics(self) -> Dict[str, Any]:
        """Returns compiled snapshot of metrics for frontend WebSocket/REST API."""
        with self._lock:
            latency_data = self.latency_calc.get_metrics()
            loss_data = self.packet_loss_calc.get_metrics()
            jitter_data = self.jitter_calc.get_metrics()

            # MOS Estimation using current metrics
            avg_latency = latency_data["avg_ms"]
            jitter_ms = jitter_data["jitter_ms"]
            loss_pct = loss_data["loss_percentage"]

            mos_data = MOSEstimator.get_metrics(avg_latency, jitter_ms, loss_pct)

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
                "mos": mos_data["mos"],
                "r_factor": mos_data["r_factor"],
                "quality": mos_data["quality"]
            }
