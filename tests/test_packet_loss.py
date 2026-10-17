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
