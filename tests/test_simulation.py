"""
Integration test for the VoIP simulator lifecycle (live UDP on localhost)
"""
import time
import pytest
from backend.simulation.simulator import VoIPSimulator


def test_simulator_lifecycle():
    # Use a dedicated port so the test never clashes with a running server on 5005
    sim = VoIPSimulator(target_port=5099)
    sim.update_config(delay_ms=10.0, jitter_ms=0.0, packet_loss_pct=0.0)

    assert sim.start() is True
    time.sleep(0.5)

    running = sim.get_current_metrics()
    assert running["status"] == "RUNNING"
    assert running["packets_sent"] > 0
    assert running["packets_received"] > 0

    assert sim.stop() is True

    stopped = sim.get_current_metrics()
    assert stopped["status"] == "STOPPED"


def test_simulator_applies_burst_and_buffer_settings():
    sim = VoIPSimulator(target_port=5098)
    sim.update_config(packet_loss_pct=5.0, loss_mode="burst", burst_length=6.0,
                      buffer_mode="fixed", buffer_ms=60.0)
    cfg = sim.get_config()
    assert cfg["loss_mode"] == "burst"
    assert cfg["burst_length"] == 6.0
    assert cfg["buffer_mode"] == "fixed"
    assert cfg["buffer_ms"] == 60.0
    metrics = sim.get_current_metrics()
    assert metrics["buffer_mode"] == "fixed"
    assert "burst_ratio" in metrics and "late_pct" in metrics
