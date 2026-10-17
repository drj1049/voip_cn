"""
Unit tests for Packet Loss Calculation Engine (RFC 3550 sequence tracking)
"""
import pytest
from backend.metrics.packet_loss import PacketLossCalculator


def test_packet_loss_detection():
    # Sequence 101, 102, 103, 105 received (101 to 105 expected) -> 104 is missing
    calc = PacketLossCalculator()

    for seq in range(101, 106):
        calc.record_sent()

    for seq in (101, 102, 103, 105):
        calc.add_received_packet({"sequence_number": seq})

    metrics = calc.get_metrics()
    assert metrics["packets_sent"] == 5
    assert metrics["packets_received"] == 4
    assert metrics["packets_lost"] == 1
    assert metrics["loss_percentage"] == 20.0


def test_in_flight_packets_not_counted_as_lost():
    # 10 sent, first 6 arrived in order, 4 are still travelling (long delay)
    calc = PacketLossCalculator()
    for _ in range(10):
        calc.record_sent()
    for seq in range(1, 7):
        calc.add_received_packet({"sequence_number": seq})

    live = calc.get_metrics()
    assert live["packets_lost"] == 0
    assert live["loss_percentage"] == 0.0

    # Once the stream has ended and nothing more arrives, the 4 are lost
    final = calc.get_metrics(final=True)
    assert final["packets_lost"] == 4
    assert final["loss_percentage"] == 40.0
