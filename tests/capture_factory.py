"""
Helpers that build small SYNTHETIC capture files for testing the capture reader.

These files are made up by code (a pretend call with known jitter and loss), NOT recorded from
a real call. They exist so the reader and the replay can be checked against numbers we know.
"""
import random
import socket
import struct
from typing import List, Tuple


def rtp_packet(seq, ts, ssrc, pt=0, payload_len=160, marker=False):
    header = struct.pack(">BBHII", 0x80, (pt & 0x7F) | (0x80 if marker else 0), seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc)
    return header + b"\x00" * payload_len


def udp_in_ipv4(payload, sport, dport, src="10.0.0.1", dst="10.0.0.2"):
    udp = struct.pack(">HHHH", sport, dport, 8 + len(payload), 0) + payload
    return struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0,
                       socket.inet_aton(src), socket.inet_aton(dst)) + udp


def ethernet(ip_packet):
    return b"\x00" * 6 + b"\x11" * 6 + b"\x08\x00" + ip_packet


def make_call(packets=500, pps=50, clock=8000, base_delay=0.040, jitter_sigma=0.010,
              loss=0.0, start_seq=1000, start_ts=123456, seed=1, ssrc=0xABCD1234, pt=0,
              duplicate_every=0):
    """
    Builds a pretend call. Returns (frames, truth).
    frames: list of (arrival_time, raw ip packet) sorted by arrival time.
    truth: what really happened, so a test can compare, with keys
           transits and sends (seconds, for every received packet in arrival order),
           lost (count), received (count).
    """
    rng = random.Random(seed)
    step_ticks = clock // pps
    items = []
    lost = 0
    for i in range(packets):
        sent = i / pps
        if rng.random() < loss:
            lost += 1
            continue
        transit = max(0.001, base_delay + rng.gauss(0.0, jitter_sigma))
        seq = (start_seq + i) & 0xFFFF
        ts = (start_ts + i * step_ticks) & 0xFFFFFFFF
        ip = udp_in_ipv4(rtp_packet(seq, ts, ssrc, pt), 5004, 5006)
        items.append((1_700_000_000.0 + sent + transit, ip, transit, sent))
        if duplicate_every and i % duplicate_every == 0:
            items.append((1_700_000_000.0 + sent + transit + 0.001, ip, transit + 0.001, sent))
    items.sort(key=lambda x: x[0])
    frames = [(t, ip) for t, ip, _, _ in items]
    truth = {"transits": [tr for _, _, tr, _ in items], "sends": [sd for _, _, _, sd in items],
             "lost": lost, "received": len(items)}
    return frames, truth


def noise_frames(start_time=1_700_000_000.0) -> List[Tuple[float, bytes]]:
    """Traffic that is NOT RTP audio and must be ignored: DNS, STUN, RTCP."""
    dns = udp_in_ipv4(b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"\x03www\x07example\x03com\x00\x00\x01\x00\x01", 53000, 53)
    stun = udp_in_ipv4(b"\x00\x01\x00\x00\x21\x12\xa4\x42" + b"\x00" * 12, 5004, 3478)
    rtcp = udp_in_ipv4(struct.pack(">BBHI", 0x80, 200, 6, 0xABCD1234) + b"\x00" * 20, 5005, 5007)
    return [(start_time + 0.5, dns), (start_time + 0.6, stun), (start_time + 0.7, rtcp)]


# ---- file writers ---------------------------------------------------------------------

def write_pcap(path, frames, linktype=1, nano=False, big_endian=False):
    """Classic pcap. linktype 1 = Ethernet, 101 = raw IP, 0 = BSD loopback (macOS lo0)."""
    e = ">" if big_endian else "<"
    magic = 0xA1B23C4D if nano else 0xA1B2C3D4
    out = bytearray(struct.pack(e + "IHHiIII", magic, 2, 4, 0, 0, 65535, linktype))
    unit = 1_000_000_000 if nano else 1_000_000
    for t, ip in frames:
        if linktype == 1:
            raw = ethernet(ip)
        elif linktype == 0:
            raw = struct.pack("<I", 2) + ip
        else:
            raw = ip
        sec = int(t)
        frac = int(round((t - sec) * unit))
        out += struct.pack(e + "IIII", sec, frac, len(raw), len(raw)) + raw
    with open(path, "wb") as f:
        f.write(out)


def _block(kind, body, e="<"):
    pad = (-len(body)) % 4
    total = 12 + len(body) + pad
    return struct.pack(e + "II", kind, total) + body + b"\x00" * pad + struct.pack(e + "I", total)


def write_pcapng(path, frames, tsresol=6, big_endian=False):
    """pcapng with one Ethernet interface. tsresol is the decimal exponent (6 = microseconds)."""
    e = ">" if big_endian else "<"
    out = bytearray()
    out += _block(0x0A0D0D0A, struct.pack(e + "IHHq", 0x1A2B3C4D, 1, 0, -1), e)
    opt = struct.pack(e + "HH", 9, 1) + bytes([tsresol]) + b"\x00\x00\x00" + struct.pack(e + "HH", 0, 0)
    out += _block(1, struct.pack(e + "HHI", 1, 0, 65535) + opt, e)
    scale = 10 ** tsresol
    for t, ip in frames:
        raw = ethernet(ip)
        ticks = int(round(t * scale))
        body = struct.pack(e + "IIIII", 0, ticks >> 32, ticks & 0xFFFFFFFF, len(raw), len(raw)) + raw
        out += _block(6, body, e)
    with open(path, "wb") as f:
        f.write(out)
