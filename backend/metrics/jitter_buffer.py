"""
Receiver-side jitter (playout) buffer.

A real VoIP phone does not play each packet the moment it arrives. It holds
packets for a short time and plays them at an even pace. A packet that arrives
after its playout time is too late to be useful and is discarded.

This module models that trade-off:
  - a bigger buffer smooths more jitter and discards fewer packets,
    but adds delay to the call
  - a smaller buffer adds less delay, but discards more late packets

Modes:
  off       no buffer, packets are used as they arrive (default)
  fixed     buffer depth chosen by the user
  adaptive  buffer depth follows the measured RFC 3550 jitter
"""
from collections import deque
from typing import Dict, Any, Optional


class JitterBuffer:
    MODES = ("off", "fixed", "adaptive")
    # Adaptive depth = factor x RFC 3550 jitter, clamped. The RFC jitter value is only
    # about 0.56 x the jitter spread, and the buffer must also cover the gap between the
    # fastest packet and a typical one, so a factor of 5 is needed to keep late packets low.
    ADAPTIVE_FACTOR = 5.0
    ADAPTIVE_MIN_MS = 20.0
    ADAPTIVE_MAX_MS = 200.0
    # The "fastest transit" baseline is the minimum over the most recent packets only
    # (about 3 seconds at 50 packets/sec). An all-time minimum would never recover when
    # the network delay rises, and every packet would be judged late against the old,
    # faster baseline.
    BASELINE_WINDOW = 150

    def __init__(self, mode: str = "off", fixed_ms: float = 40.0, window_size: int = 250):
        self.mode: str = mode if mode in self.MODES else "off"
        self.fixed_ms: float = float(fixed_ms)
        self.window_size: int = window_size
        self._window = deque(maxlen=window_size)   # True = played on time, False = late
        self._transits = deque(maxlen=self.BASELINE_WINDOW)   # recent transit times (ms)
        self.min_transit_ms: Optional[float] = None
        self.current_ms: float = self.fixed_ms if self.mode == "fixed" else 0.0
        self.on_time_count: int = 0
        self.late_count: int = 0

    def configure(self, mode: Optional[str] = None, fixed_ms: Optional[float] = None):
        """Changes mode and/or fixed depth. Switching mode restarts the statistics."""
        if fixed_ms is not None:
            self.fixed_ms = max(0.0, min(300.0, float(fixed_ms)))
        if mode is not None and mode in self.MODES and mode != self.mode:
            self.mode = mode
            self.reset()
        elif self.mode == "fixed":
            self.current_ms = self.fixed_ms

    def process(self, packet: Dict[str, Any], jitter_ms: float = 0.0) -> bool:
        """
        Decides whether a received packet is on time.
        A packet is on time if its transit time is within the buffer depth
        of the fastest transit seen so far (the best estimate of the base delay).
        Returns True if the packet would be played, False if it is discarded as late.
        """
        if self.mode == "off":
            return True

        transit_ms = max(0.0, (packet["receive_time"] - packet["send_time"]) * 1000.0)
        self._transits.append(transit_ms)
        self.min_transit_ms = min(self._transits)

        if self.mode == "fixed":
            self.current_ms = self.fixed_ms
        else:
            depth = self.ADAPTIVE_FACTOR * jitter_ms
            self.current_ms = max(self.ADAPTIVE_MIN_MS, min(self.ADAPTIVE_MAX_MS, depth))

        on_time = transit_ms <= self.min_transit_ms + self.current_ms
        if on_time:
            self.on_time_count += 1
        else:
            self.late_count += 1
        self._window.append(on_time)
        return on_time

    def late_pct(self, final: bool = False) -> float:
        """Share of received packets discarded as late (recent window, or whole run if final)."""
        if final:
            total = self.on_time_count + self.late_count
            return (self.late_count / total) * 100.0 if total else 0.0
        if not self._window:
            return 0.0
        late = sum(1 for ok in self._window if not ok)
        return (late / len(self._window)) * 100.0

    def playout_delay_ms(self) -> float:
        """Delay a listener experiences: fastest transit plus buffer depth."""
        base = self.min_transit_ms if self.min_transit_ms is not None else 0.0
        return base + self.current_ms

    def reset(self):
        self._window.clear()
        self._transits.clear()
        self.min_transit_ms = None
        self.on_time_count = 0
        self.late_count = 0
        self.current_ms = self.fixed_ms if self.mode == "fixed" else 0.0
