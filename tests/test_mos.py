"""
Unit tests for ITU-T G.107 MOS Estimation Engine
"""
import pytest
from backend.metrics.mos import MOSEstimator

def test_mos_perfect_conditions():
    # Delay 10ms, Jitter 0ms, Loss 0% -> Expected MOS ~ 4.4 - 4.5 EXCELLENT
    metrics = MOSEstimator.get_metrics(latency_ms=10.0, jitter_ms=0.0, packet_loss_pct=0.0)
    assert metrics["mos"] >= 4.3
    assert metrics["quality"] == "EXCELLENT"

def test_mos_poor_conditions():
    # Delay 250ms, Jitter 80ms, Loss 15% -> Expected MOS low (BAD/POOR)
    metrics = MOSEstimator.get_metrics(latency_ms=250.0, jitter_ms=80.0, packet_loss_pct=15.0)
    assert metrics["mos"] < 3.1
    assert metrics["quality"] == "BAD"

def test_mos_classification_scale():
    assert MOSEstimator.classify_quality(4.4) == "EXCELLENT"
    assert MOSEstimator.classify_quality(4.1) == "GOOD"
    assert MOSEstimator.classify_quality(3.8) == "FAIR"
    assert MOSEstimator.classify_quality(3.3) == "POOR"
    assert MOSEstimator.classify_quality(2.5) == "BAD"
