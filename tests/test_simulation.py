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
