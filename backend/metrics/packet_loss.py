"""
Packet Loss Calculation Engine based on RFC 3550 Sequence Tracking
Handles sequence gaps, packet reordering, and initial/trailing dropped packets accurately.
"""
from collections import deque
from typing import Dict, Any

class PacketLossCalculator:
    """
    Detects packet loss using RTP sequence number continuity with reordering compensation.
    Calculates total packets expected, total received, total lost, and loss percentage.
    """

    def __init__(self, window_size: int = 250):
        # Rolling window of the most recent packet outcomes (True = arrived,
        # False = lost). 250 packets is about 5 seconds of a 50 packets/sec call.
        # The live loss percentage uses this window so the dashboard recovers
        # soon after the network improves. Full-run totals are still kept.
        self.window_size: int = window_size
        self._window = deque(maxlen=window_size)
        self.packets_sent: int = 0
        self.packets_received: int = 0
        self.sequence_gap_lost: int = 0
        self.max_seq_received: int = -1

    def record_sent(self):
        """Called whenever a packet is dispatched by the generator."""
        self.packets_sent += 1

    def add_received_packet(self, packet: Dict[str, Any]):
        """
        Processes received packet using RFC 3550 sequence tracking.
        Compensates for out-of-order arrivals caused by jitter.
        """
        seq = packet["sequence_number"]
        self.packets_received += 1

        if self.max_seq_received == -1:
            self.max_seq_received = seq
            self._window.append(True)
            return

        # Calculate forward difference with 16-bit wraparound (65536)
        diff = (seq - self.max_seq_received) % 65536

        if diff < 30000:
            # Packet arrived with sequence > max_seq_received
            gap = diff - 1
            if gap > 0:
                self.sequence_gap_lost += gap
                for _ in range(min(gap, self.window_size)):
                    self._window.append(False)
            self._window.append(True)
            self.max_seq_received = seq
        else:
            # Reordered / late packet (seq <= max_seq_received)
            # Reduce gap count if previously counted as lost
            if self.sequence_gap_lost > 0:
                self.sequence_gap_lost -= 1
            # The late packet was marked lost earlier, so mark the most recent
            # lost slot in the window as arrived.
            for i in range(len(self._window) - 1, -1, -1):
                if not self._window[i]:
                    self._window[i] = True
                    break

    def get_packets_lost(self, final: bool = False) -> int:
        """
        Returns total packets lost.

        While a call is live, only sequence gaps count as lost. A packet that
        is still travelling (for example under a long delay) has not arrived
        yet, but it is not lost either, so sent minus received is not used.

        When final=True (sender stopped and in-flight packets have drained),
        sent minus received is also checked so drops at the very end of a run
        are counted too.
        """
        if final:
            sent_delta_lost = max(0, self.packets_sent - self.packets_received)
            return max(self.sequence_gap_lost, sent_delta_lost)
        return self.sequence_gap_lost

    def get_loss_percentage(self, final: bool = False) -> float:
        """
        Calculates loss percentage relative to total expected packets.
        """
        if not final:
            # Live view: loss over the last window_size packets only
            if not self._window:
                return 0.0
            window_lost = sum(1 for arrived in self._window if not arrived)
            return (window_lost / len(self._window)) * 100.0

        lost = self.get_packets_lost(final)
        total_expected = max(self.packets_sent, self.packets_received + lost)
        if total_expected == 0:
            return 0.0

        loss_pct = (lost / total_expected) * 100.0
        return min(100.0, max(0.0, loss_pct))

    def get_metrics(self, final: bool = False) -> Dict[str, Any]:
        """Returns snapshot of packet loss statistics."""
        lost = self.get_packets_lost(final)
        return {
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "packets_lost": lost,
            "loss_percentage": round(self.get_loss_percentage(final), 2)
        }

    def reset(self):
        """Resets all counters."""
        self.packets_sent = 0
        self.packets_received = 0
        self.sequence_gap_lost = 0
        self.max_seq_received = -1
        self._window.clear()
