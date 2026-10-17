"""
Network Impairment Engine for Controlled Delay, Jitter, and Packet Loss Simulation
"""
import random
import time
from typing import Dict, Any, Optional

class ImpairmentEngine:
    """
    Simulates physical network impairments on outgoing packets:
    - Probabilistic packet loss
    - Base propagation / queuing delay
    - Interarrival jitter variation
    """

    def __init__(self, delay_ms: float = 20.0, jitter_ms: float = 2.0, packet_loss_pct: float = 0.0):
        self.delay_ms: float = float(delay_ms)
        self.jitter_ms: float = float(jitter_ms)
        self.packet_loss_pct: float = float(packet_loss_pct)

    def update_config(self, delay_ms: Optional[float] = None, jitter_ms: Optional[float] = None, packet_loss_pct: Optional[float] = None):
        """Dynamically updates network impairment parameters during live runtime."""
        if delay_ms is not None:
            self.delay_ms = max(0.0, min(500.0, float(delay_ms)))
        if jitter_ms is not None:
            self.jitter_ms = max(0.0, min(100.0, float(jitter_ms)))
        if packet_loss_pct is not None:
            self.packet_loss_pct = max(0.0, min(30.0, float(packet_loss_pct)))

    def process_packet(self, packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Applies network impairments to a packet.
        Returns:
            - None if packet is dropped due to packet loss
            - Modified packet dict with added calculated impairment delay and transmit schedule
        """
        # 1. Packet Loss Simulation (Probabilistic Drop)
        if self.packet_loss_pct > 0.0:
            drop_roll = random.uniform(0.0, 100.0)
            if drop_roll < self.packet_loss_pct:
                # Packet lost in simulated network channel
                return None

        # 2. Base Delay + Random Jitter Calculation
        base_delay_sec = self.delay_ms / 1000.0
        
        # Use a realistic normal/uniform jitter distribution bounded by jitter_ms
        if self.jitter_ms > 0.0:
            # Gaussian jitter variation centered at 0 with standard deviation jitter_ms / 2
            jitter_offset_sec = random.gauss(0.0, self.jitter_ms / 2.0) / 1000.0
            # Clamp jitter offset to [-jitter_ms, +jitter_ms] range
            max_offset = self.jitter_ms / 1000.0
            jitter_offset_sec = max(-max_offset, min(max_offset, jitter_offset_sec))
        else:
            jitter_offset_sec = 0.0

        total_delay_sec = max(0.0, base_delay_sec + jitter_offset_sec)

        # Store impairment execution timing in packet metadata
        packet_copy = dict(packet)
        packet_copy["simulated_delay_sec"] = total_delay_sec
        packet_copy["scheduled_send_time"] = packet["send_time"] + total_delay_sec

        return packet_copy
