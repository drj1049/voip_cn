"""
Unit tests for Latency Calculation Engine
"""
import pytest
from backend.metrics.latency import LatencyCalculator

# Latency is simply arrival time minus send time. Two packets give us a current value,
# an average, a minimum and a maximum to check.
def test_latency_calculation():
    calc = LatencyCalculator(window_size=10)
    
    packet1 = {"send_time": 100.0, "receive_time": 100.05} # 50ms
    lat1 = calc.add_packet(packet1)
    assert abs(lat1 - 50.0) < 1e-4

    packet2 = {"send_time": 101.0, "receive_time": 101.03} # 30ms
    lat2 = calc.add_packet(packet2)
    assert abs(lat2 - 30.0) < 1e-4

    metrics = calc.get_metrics()
    assert metrics["current_ms"] == 30.0
    assert metrics["avg_ms"] == 40.0     # (50 + 30) / 2
    assert metrics["min_ms"] == 30.0
    assert metrics["max_ms"] == 50.0

# Reset should bring every number back to zero.
def test_latency_reset():
    calc = LatencyCalculator()
    calc.add_packet({"send_time": 10.0, "receive_time": 10.1})
    calc.reset()
    metrics = calc.get_metrics()
    assert metrics["current_ms"] == 0.0
    assert metrics["avg_ms"] == 0.0
