"""
Tests for bursty packet loss and the burst ratio in the MOS model
"""
import random
import pytest
from backend.simulation.impairment import ImpairmentEngine
from backend.metrics.packet_loss import PacketLossCalculator
from backend.metrics.mos import MOSEstimator


def _loss_pattern(mode, loss_pct=10.0, burst_length=5.0, n=40000):
    random.seed(1234)
    eng = ImpairmentEngine(delay_ms=0, jitter_ms=0, packet_loss_pct=loss_pct)
    eng.update_config(loss_mode=mode, burst_length=burst_length)
    return [eng.process_packet({"send_time": 0.0}) is None for _ in range(n)]


def _mean_run_length(lost_flags):
    runs, current = [], 0
    for lost in lost_flags:
        if lost:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return sum(runs) / len(runs)


def test_burst_mode_keeps_average_loss_rate():
    pattern = _loss_pattern("burst")
    rate = 100.0 * sum(pattern) / len(pattern)
    assert 8.0 < rate < 12.0


def test_burst_mode_loses_packets_in_clumps():
    random_runs = _mean_run_length(_loss_pattern("random"))
    burst_runs = _mean_run_length(_loss_pattern("burst", burst_length=5.0))
    assert random_runs < 1.5          # random loss is mostly single packets
    assert 4.0 < burst_runs < 6.0     # about the configured burst length


def test_burst_ratio_measured_from_sequence_gaps():
    # Random-looking loss: every 5th packet missing, so runs of 1
    calc = PacketLossCalculator()
    for seq in range(1, 101):
        calc.record_sent()
        if seq % 5 != 0:
            calc.add_received_packet({"sequence_number": seq})
    assert calc.get_burst_ratio(final=True) < 1.3

    # Clumped loss: 5 in a row missing, then 20 received, repeated
    calc = PacketLossCalculator()
    seq = 0
    for _ in range(8):
        seq += 5                      # 5 lost in a row
        for _ in range(20):
            seq += 1
            calc.record_sent()
            calc.add_received_packet({"sequence_number": seq})
    assert calc.get_burst_ratio(final=True) > 3.0


def test_burst_lowers_mos_for_same_average_loss():
    random_mos = MOSEstimator.calculate_mos(50.0, 0.0, 5.0, burst_ratio=1.0)
    burst_mos = MOSEstimator.calculate_mos(50.0, 0.0, 5.0, burst_ratio=3.0)
    assert burst_mos < random_mos     # clumped loss sounds worse than scattered loss
