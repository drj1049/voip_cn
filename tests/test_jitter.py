"""
Unit tests for RFC 3550 Jitter Calculation Engine
"""
import pytest
from backend.metrics.jitter import RFC3550JitterCalculator

def test_rfc3550_jitter():
    calc = RFC3550JitterCalculator()

    # Packet 1: send = 0.0, receive = 0.02 (transit = 0.02)
    calc.add_packet({"send_time": 0.0, "receive_time": 0.02})
    assert calc.get_jitter_ms() == 0.0

    # Packet 2: send = 0.02, receive = 0.05 (transit = 0.03, D = 0.01)
    # J = 0 + (0.01 - 0)/16 = 0.01 / 16 = 0.000625 sec = 0.625 ms
    j2 = calc.add_packet({"send_time": 0.02, "receive_time": 0.05})
    assert abs(j2 - 0.625) < 1e-3

def test_jitter_reset():
    calc = RFC3550JitterCalculator()
    calc.add_packet({"send_time": 0.0, "receive_time": 0.02})
    calc.add_packet({"send_time": 0.02, "receive_time": 0.08})
    calc.reset()
    assert calc.get_jitter_ms() == 0.0
