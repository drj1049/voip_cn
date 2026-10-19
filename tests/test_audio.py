"""
Tests for audio mode (clip -> packets -> simulated network -> damaged clip)
"""
import io
import random
import wave

import numpy as np

from backend.audio.processor import (
    FRAME_SAMPLES, SAMPLE_RATE, decode_wav, encode_wav, make_demo_clip,
    process_audio, PLAYED, LOST, LATE,
)


def _wav_bytes(samples, rate=SAMPLE_RATE, channels=1, width=2):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def test_wav_roundtrip():
    clip = make_demo_clip(2.0)
    assert np.array_equal(decode_wav(encode_wav(clip)), clip)


def test_decode_resamples_and_mixes_to_mono_8k():
    t = np.arange(44100) / 44100.0
    tone = (np.sin(2 * np.pi * 440 * t) * 10000).astype("<i2")
    stereo = np.column_stack([tone, tone]).reshape(-1)
    out = decode_wav(_wav_bytes(stereo, rate=44100, channels=2))
    assert abs(len(out) - SAMPLE_RATE) <= 2          # 1 second at 8 kHz


def test_decode_rejects_bad_input():
    for bad in (b"not a wav file", b""):
        try:
            decode_wav(bad)
            assert False, "expected ValueError"
        except ValueError:
            pass
    long_clip = np.zeros(SAMPLE_RATE * 31, dtype="<i2")
    try:
        decode_wav(_wav_bytes(long_clip))
        assert False, "expected ValueError for a clip over 30 seconds"
    except ValueError:
        pass


def test_clean_network_leaves_audio_untouched():
    random.seed(1)
    clip = make_demo_clip(4.0)
    r = process_audio(clip, delay_ms=20, jitter_ms=0, packet_loss_pct=0)
    assert set(r["frames"]) == {PLAYED}
    assert np.array_equal(decode_wav(r["damaged_wav"]), clip)
    assert r["metrics"]["mos"] >= 4.3
    assert r["metrics"]["packets_lost"] == 0


def test_loss_becomes_silence_in_the_right_places():
    random.seed(2)
    clip = make_demo_clip(8.0)
    r = process_audio(clip, delay_ms=20, jitter_ms=0, packet_loss_pct=20)
    damaged = decode_wav(r["damaged_wav"])
    assert len(damaged) == len(clip)
    lost = [i for i, s in enumerate(r["frames"]) if s == LOST]
    assert 0.08 < len(lost) / len(r["frames"]) < 0.35
    for i in lost:
        assert not damaged[i * FRAME_SAMPLES:(i + 1) * FRAME_SAMPLES].any()
    kept = [i for i, s in enumerate(r["frames"]) if s == PLAYED]
    for i in kept[:20]:
        a, b = i * FRAME_SAMPLES, (i + 1) * FRAME_SAMPLES
        assert np.array_equal(damaged[a:b], clip[a:b])
    assert r["metrics"]["packets_lost"] == len(lost)


def test_worse_network_gives_lower_mos():
    clip = make_demo_clip(8.0)
    scores = []
    for loss in (0, 3, 10):
        random.seed(3)
        scores.append(process_audio(clip, delay_ms=40, jitter_ms=5, packet_loss_pct=loss)["metrics"]["mos"])
    assert scores[0] > scores[1] > scores[2]


def test_jitter_is_only_audible_with_a_buffer():
    clip = make_demo_clip(8.0)
    random.seed(4)
    with_buffer = process_audio(clip, delay_ms=50, jitter_ms=80, packet_loss_pct=0,
                                buffer_mode="fixed", buffer_ms=40)
    random.seed(4)
    no_buffer = process_audio(clip, delay_ms=50, jitter_ms=80, packet_loss_pct=0, buffer_mode="off")
    assert with_buffer["frames"].count(LATE) > 0
    assert no_buffer["frames"].count(LATE) == 0
    assert with_buffer["metrics"]["packets_late"] == with_buffer["frames"].count(LATE)


def test_burst_mode_runs():
    random.seed(5)
    r = process_audio(make_demo_clip(8.0), packet_loss_pct=10, loss_mode="burst", burst_length=6)
    assert r["frames"].count(LOST) > 0
    assert len(r["frames"]) == r["metrics"]["packets_sent"]
