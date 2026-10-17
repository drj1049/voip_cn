"""
Tests for the receiver jitter buffer (off / fixed / adaptive)
"""
import pytest
from backend.metrics.jitter_buffer import JitterBuffer


def pkt(transit_ms, send=0.0):
    return {"send_time": send, "receive_time": send + transit_ms / 1000.0}


def test_buffer_off_accepts_everything():
    buf = JitterBuffer(mode="off")
    assert buf.process(pkt(20)) is True
    assert buf.process(pkt(900)) is True
    assert buf.late_pct(final=True) == 0.0


def test_fixed_buffer_discards_late_packets():
    buf = JitterBuffer(mode="fixed", fixed_ms=40.0)
    assert buf.process(pkt(50)) is True      # sets the fastest transit (50 ms)
    assert buf.process(pkt(85)) is True      # 35 ms above fastest, inside 40 ms buffer
    assert buf.process(pkt(100)) is False    # 50 ms above fastest, too late
    assert buf.late_pct(final=True) == pytest.approx(100.0 / 3.0, abs=0.01)


def test_bigger_buffer_discards_fewer_but_adds_delay():
    transits = [50, 62, 95, 55, 130, 58, 70, 52, 110, 60]
    small, large = JitterBuffer("fixed", 20.0), JitterBuffer("fixed", 100.0)
    for t in transits:
        small.process(pkt(t))
        large.process(pkt(t))
    assert large.late_pct(final=True) < small.late_pct(final=True)
    assert large.playout_delay_ms() > small.playout_delay_ms()


def test_adaptive_buffer_follows_jitter_and_is_clamped():
    buf = JitterBuffer(mode="adaptive")
    buf.process(pkt(50), jitter_ms=0.5)
    assert buf.current_ms == JitterBuffer.ADAPTIVE_MIN_MS      # factor x 0.5 is below the minimum
    buf.process(pkt(50), jitter_ms=15.0)
    assert buf.current_ms == pytest.approx(JitterBuffer.ADAPTIVE_FACTOR * 15.0)
    buf.process(pkt(50), jitter_ms=500.0)
    assert buf.current_ms == JitterBuffer.ADAPTIVE_MAX_MS      # clamped at the maximum


def test_switching_mode_resets_statistics():
    buf = JitterBuffer(mode="fixed", fixed_ms=10.0)
    buf.process(pkt(50))
    buf.process(pkt(200))
    assert buf.late_count == 1
    buf.configure(mode="adaptive")
    assert buf.late_count == 0 and buf.mode == "adaptive"
