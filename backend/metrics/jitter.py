"""
Interarrival Jitter Calculation Engine based on RFC 3550 Standard
"""
from typing import Dict, Any, Optional

class RFC3550JitterCalculator:
    """
    Implements the standard interarrival jitter calculation algorithm specified in RFC 3550 Section 6.4.1.
    
    Formula:
      Transit time difference: D(i-1, i) = (R_i - S_i) - (R_{i-1} - S_{i-1})
      Interarrival jitter:     J(i) = J(i-1) + (|D(i-1, i)| - J(i-1)) / 16
    """

    def __init__(self):
        self.last_send_time: Optional[float] = None
        self.last_receive_time: Optional[float] = None
        self.jitter_sec: float = 0.0

    def add_packet(self, packet: Dict[str, Any]) -> float:
        """
        Updates exponentially smoothed RFC 3550 interarrival jitter.
        Returns jitter in milliseconds.
        """
        send_time = packet["send_time"]
        receive_time = packet["receive_time"]

        if self.last_send_time is not None and self.last_receive_time is not None:
            # Transit time difference D(i-1, i) = (R_i - S_i) - (R_{i-1} - S_{i-1})
            current_transit = receive_time - send_time
            previous_transit = self.last_receive_time - self.last_send_time

            d = abs(current_transit - previous_transit)

            # Exponentially smoothed estimate: J = J + (|D| - J) / 16.0
            self.jitter_sec += (d - self.jitter_sec) / 16.0

        # Save previous packet timing
        self.last_send_time = send_time
        self.last_receive_time = receive_time

        return self.get_jitter_ms()

    def get_jitter_ms(self) -> float:
        """Returns the current estimated jitter in milliseconds."""
        return self.jitter_sec * 1000.0

    def get_metrics(self) -> Dict[str, float]:
        """Returns snapshot of jitter metrics."""
        return {
            "jitter_ms": round(self.get_jitter_ms(), 2)
        }

    def reset(self):
        """Resets jitter calculation state."""
        self.last_send_time = None
        self.last_receive_time = None
        self.jitter_sec = 0.0
