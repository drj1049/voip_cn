"""
Latency Calculation Engine
"""
from typing import Dict, Any, List

class LatencyCalculator:
    """
    Calculates one-way network delay (latency) for received packets.
    Maintains current, rolling average, minimum, and maximum latency metrics.
    """

    def __init__(self, window_size: int = 50):
        self.window_size: int = window_size
        self.history: List[float] = []
        self.current_latency_ms: float = 0.0
        self.min_latency_ms: float = float('inf')
        self.max_latency_ms: float = 0.0

    def add_packet(self, packet: Dict[str, Any]) -> float:
        """
        Computes latency = (receive_time - send_time) * 1000 in milliseconds.
        Updates internal historical tracking.
        """
        send_time = packet["send_time"]
        receive_time = packet["receive_time"]

        latency_ms = max(0.0, (receive_time - send_time) * 1000.0)
        self.current_latency_ms = latency_ms

        self.history.append(latency_ms)
        if len(self.history) > self.window_size:
            self.history.pop(0)

        if latency_ms < self.min_latency_ms:
            self.min_latency_ms = latency_ms
        if latency_ms > self.max_latency_ms:
            self.max_latency_ms = latency_ms

        return latency_ms

    def get_avg_latency(self) -> float:
        """Returns the rolling average latency in ms."""
        if not self.history:
            return 0.0
        return sum(self.history) / len(self.history)

    def get_metrics(self) -> Dict[str, float]:
        """Returns summary dictionary of latency statistics."""
        return {
            "current_ms": round(self.current_latency_ms, 2),
            "avg_ms": round(self.get_avg_latency(), 2),
            "min_ms": round(self.min_latency_ms if self.min_latency_ms != float('inf') else 0.0, 2),
            "max_ms": round(self.max_latency_ms, 2)
        }

    def reset(self):
        """Resets all latency statistics."""
        self.history.clear()
        self.current_latency_ms = 0.0
        self.min_latency_ms = float('inf')
        self.max_latency_ms = 0.0
