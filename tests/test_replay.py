"""
Tests for the real-call replay: the capture reader and the replay pipeline.

The capture files used here are SYNTHETIC (built by tests/capture_factory.py with known jitter
and loss), so the reader and the metrics can be checked against numbers we know in advance.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capture_factory import make_call, noise_frames, write_pcap, write_pcapng   # noqa: E402
from backend.metrics.jitter import RFC3550JitterCalculator                       # noqa: E402
from backend.replay.pcap_reader import (                                          # noqa: E402
    CaptureError, prepare_replay, read_rtp_streams, choose_default_stream,
)
from backend.replay.replayer import ReplaySimulator, safe_capture_name, summarize_capture  # noqa: E402


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _only_stream(path):
    streams = read_rtp_streams(_read(path))
    assert len(streams) == 1
    return next(iter(streams.values()))


# ---------------- file formats and link types ----------------

def test_pcap_ethernet(tmp_path):
    frames, truth = make_call(packets=300)
    p = tmp_path / "a.pcap"
    write_pcap(p, frames)
    s = _only_stream(p)
    assert len(s.packets) == truth["received"] == 300
    assert s.clock_rate() == 8000
    assert s.summary()["looks_like_audio"] is True


def test_pcap_nanosecond_and_big_endian(tmp_path):
    frames, _ = make_call(packets=100)
    p = tmp_path / "b.pcap"
    write_pcap(p, frames, nano=True, big_endian=True)
    assert len(_only_stream(p).packets) == 100


def test_pcapng_microseconds_and_nanoseconds(tmp_path):
    frames, _ = make_call(packets=120)
    for res, name in ((6, "c.pcapng"), (9, "d.pcapng")):
        p = tmp_path / name
        write_pcapng(p, frames, tsresol=res)
        s = _only_stream(p)
        assert len(s.packets) == 120
        assert abs((s.packets[-1].arrival - s.packets[0].arrival) - (frames[-1][0] - frames[0][0])) < 1e-4


def test_loopback_and_raw_ip_link_types(tmp_path):
    frames, _ = make_call(packets=80)
    for lt, name in ((0, "lo.pcap"), (101, "raw.pcap")):
        p = tmp_path / name
        write_pcap(p, frames, linktype=lt)
        assert len(_only_stream(p).packets) == 80


def test_non_rtp_traffic_is_ignored(tmp_path):
    frames, _ = make_call(packets=100)
    frames = sorted(frames + noise_frames(), key=lambda x: x[0])
    p = tmp_path / "noise.pcap"
    write_pcap(p, frames)
    streams = read_rtp_streams(_read(p))
    assert len(streams) == 1
    assert len(next(iter(streams.values())).packets) == 100


def test_bad_files_give_clear_errors(tmp_path):
    with pytest.raises(CaptureError):
        read_rtp_streams(b"this is not a capture file at all")
    with pytest.raises(CaptureError):
        read_rtp_streams(b"\x1f\x8b\x08\x00 gzip bytes")
    p = tmp_path / "empty.pcap"
    write_pcap(p, noise_frames())
    with pytest.raises(CaptureError):
        summarize_capture(_read(p))


def test_capture_name_is_made_safe():
    assert safe_capture_name("../../etc/passwd.pcap") == "passwd.pcap"
    assert safe_capture_name("my call (1).pcapng") == "my call _1_.pcapng"
    with pytest.raises(ValueError):
        safe_capture_name("notes.txt")
    with pytest.raises(ValueError):
        safe_capture_name("")


# ---------------- sequence numbers, loss, duplicates ----------------

def test_sequence_wraparound_is_handled(tmp_path):
    frames, truth = make_call(packets=400, start_seq=65400)   # wraps past 65535 during the call
    p = tmp_path / "wrap.pcap"
    write_pcap(p, frames)
    packets, info = prepare_replay(_only_stream(p))
    ext = [x.ext_seq for x in packets]
    assert max(ext) - min(ext) == 399
    assert info["packets_missing_in_capture"] == 0


def test_loss_is_counted_from_sequence_gaps(tmp_path):
    frames, truth = make_call(packets=1000, loss=0.10, seed=7)
    p = tmp_path / "loss.pcap"
    write_pcap(p, frames)
    packets, info = prepare_replay(_only_stream(p))
    # trailing losses cannot be seen from the capture, so missing <= truth.lost and close to it
    assert info["packets_missing_in_capture"] <= truth["lost"]
    assert truth["lost"] - info["packets_missing_in_capture"] <= 5


def test_duplicates_are_removed(tmp_path):
    frames, _ = make_call(packets=200, duplicate_every=10)
    p = tmp_path / "dup.pcap"
    write_pcap(p, frames)
    packets, info = prepare_replay(_only_stream(p))
    assert info["duplicates_removed"] == 20
    assert len(packets) == 200


# ---------------- the numbers ----------------

def test_replayed_jitter_matches_the_true_jitter(tmp_path):
    """RFC 3550 jitter worked out from the capture must equal jitter from the true send and arrival times."""
    frames, truth = make_call(packets=600, jitter_sigma=0.015, seed=3)
    p = tmp_path / "j.pcap"
    write_pcap(p, frames)
    packets, _ = prepare_replay(_only_stream(p))

    from_capture = RFC3550JitterCalculator()
    for rp in packets:
        from_capture.add_packet({"send_time": rp.send_time, "receive_time": rp.arrival})

    expected = RFC3550JitterCalculator()
    for sent, transit in zip(truth["sends"], truth["transits"]):
        expected.add_packet({"send_time": sent, "receive_time": sent + transit})

    # The capture stores times to the microsecond, so allow a tiny rounding difference
    assert abs(from_capture.get_jitter_ms() - expected.get_jitter_ms()) < 0.05
    assert 3.0 < from_capture.get_jitter_ms() < 25.0


def test_fastest_packet_gets_the_assumed_delay(tmp_path):
    frames, _ = make_call(packets=300)
    p = tmp_path / "d.pcap"
    write_pcap(p, frames)
    packets, info = prepare_replay(_only_stream(p), base_delay_ms=55.0)
    transits = [rp.arrival - rp.send_time for rp in packets]
    assert abs(min(transits) - 0.055) < 1e-9
    assert info["assumed_base_delay_ms"] == 55.0


def test_default_stream_prefers_the_audio_stream(tmp_path):
    audio, _ = make_call(packets=300, ssrc=0x1111, pt=0)
    other, _ = make_call(packets=900, pps=50, clock=90000, ssrc=0x2222, pt=96, seed=2)   # video-like clock
    p = tmp_path / "two.pcap"
    write_pcap(p, sorted(audio + other, key=lambda x: x[0]))
    chosen = choose_default_stream(read_rtp_streams(_read(p)))
    assert chosen.ssrc == 0x1111


# ---------------- full replay through the metric pipeline ----------------

def _run_replay(path, speed=100.0, config=None, timeout=15.0):
    sim = ReplaySimulator()
    sim.load_capture("test.pcap", _read(path), speed=speed)
    if config:
        sim.update_config(**config)
    assert sim.start() is True
    deadline = time.time() + timeout
    while sim.is_running and time.time() < deadline:
        time.sleep(0.02)
    return sim


def test_full_replay_gives_clean_call_a_high_mos(tmp_path):
    frames, truth = make_call(packets=500, jitter_sigma=0.002, base_delay=0.030)
    p = tmp_path / "clean.pcap"
    write_pcap(p, frames)
    sim = _run_replay(p)
    m = sim.get_current_metrics()
    assert m["source"] == "replay" and m["replay_state"] == "finished"
    assert m["packets_received"] == 500
    assert m["packet_loss"] == 0.0
    assert m["mos"] >= 4.2


def test_full_replay_reports_real_loss(tmp_path):
    frames, truth = make_call(packets=1000, loss=0.08, seed=11)
    p = tmp_path / "lossy.pcap"
    write_pcap(p, frames)
    m = _run_replay(p).get_current_metrics()
    assert m["packets_received"] == truth["received"]
    assert 5.0 < m["packet_loss"] < 11.0
    assert m["mos"] < 3.0


def test_extra_impairment_is_added_on_top(tmp_path):
    frames, _ = make_call(packets=400, jitter_sigma=0.001, base_delay=0.030)
    p = tmp_path / "x.pcap"
    write_pcap(p, frames)
    plain = _run_replay(p).get_current_metrics()
    extra = _run_replay(p, config={"delay_ms": 120.0, "jitter_ms": 0.0, "packet_loss_pct": 0.0}).get_current_metrics()
    assert 100.0 < extra["latency_avg"] - plain["latency_avg"] < 140.0
    assert extra["mos"] < plain["mos"]

    lossy = _run_replay(p, config={"delay_ms": 0.0, "jitter_ms": 0.0, "packet_loss_pct": 20.0}).get_current_metrics()
    assert lossy["packet_loss"] > 8.0


def test_replay_can_be_stopped_and_restarted(tmp_path):
    frames, _ = make_call(packets=500)
    p = tmp_path / "s.pcap"
    write_pcap(p, frames)
    sim = ReplaySimulator()
    sim.load_capture("s.pcap", _read(p), speed=1.0)
    assert sim.start() is True
    time.sleep(0.3)
    assert sim.stop() is True
    mid = sim.get_current_metrics()
    assert mid["replay_state"] == "stopped" and 0 < mid["packets_received"] < 500
    assert sim.start() is True            # starts again from the beginning
    sim.stop()


# ---------------- trimming a capture down to one stream ----------------

def test_trim_keeps_only_the_voice_stream_and_the_same_numbers(tmp_path):
    from backend.replay.trim_capture import trim_capture
    audio, _ = make_call(packets=400, ssrc=0x1111, pt=0, jitter_sigma=0.012, seed=4)
    video, _ = make_call(packets=900, clock=90000, ssrc=0x2222, pt=96, seed=2)
    mixed = sorted(audio + video + noise_frames(), key=lambda x: x[0])
    p = tmp_path / "mixed.pcapng"
    write_pcapng(p, mixed)

    trimmed, info = trim_capture(_read(p))
    assert info["packets_kept"] == 400 and info["ssrc"] == "0x00001111"
    assert len(trimmed) < len(_read(p)) / 2

    q = tmp_path / "trimmed.pcap"
    q.write_bytes(trimmed)
    streams = read_rtp_streams(_read(q))
    assert len(streams) == 1

    # the replay numbers must not change when the other traffic is removed
    a, _ = prepare_replay(read_rtp_streams(_read(p))[next(k for k in read_rtp_streams(_read(p)) if k[4] == 0x1111)])
    b, _ = prepare_replay(next(iter(streams.values())))
    assert len(a) == len(b)
    assert abs(sum(x.arrival for x in a) - sum(x.arrival for x in b)) < 1e-3
    assert b"\x11" * 6 not in trimmed[:200]        # hardware addresses were blanked
