"""
Reader for packet captures (.pcap and .pcapng) that pulls RTP audio streams out of them.

It needs no third-party libraries. It understands the file formats that Wireshark and
tcpdump write, walks through the link / IP / UDP headers of every packet, recognises RTP,
groups the packets into streams (one stream per SSRC) and prepares them for replay.

Why this exists: the live simulator makes its own packets. This module lets the analyzer
read packets that were recorded from a REAL call instead, so jitter, loss and MOS come from
real network behaviour.
"""
import socket
import struct
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple


class CaptureError(ValueError):
    """Raised when a file is not a readable capture, or has no RTP audio in it."""


# --------------------------------------------------------------------------------------
# 1. Capture file formats
# --------------------------------------------------------------------------------------

# Classic pcap starts with a 4 byte "magic number" that also tells us the byte order and
# whether timestamps are in microseconds or nanoseconds.
_PCAP_MAGICS = {
    b"\xd4\xc3\xb2\xa1": ("<", 1e-6),
    b"\xa1\xb2\xc3\xd4": (">", 1e-6),
    b"\x4d\x3c\xb2\xa1": ("<", 1e-9),
    b"\xa1\xb2\x3c\x4d": (">", 1e-9),
}
_PCAPNG_SECTION_HEADER = b"\x0a\x0d\x0d\x0a"


def _iter_pcap(data: bytes) -> Iterator[Tuple[float, int, bytes]]:
    """Classic pcap: a 24 byte file header, then (16 byte record header + packet bytes) repeated."""
    endian, unit = _PCAP_MAGICS[data[:4]]
    if len(data) < 24:
        raise CaptureError("The capture file is too short to be valid.")
    linktype = struct.unpack_from(endian + "I", data, 20)[0] & 0x0FFFFFFF
    record = struct.Struct(endian + "IIII")
    pos, size = 24, len(data)
    while pos + 16 <= size:
        ts_sec, ts_frac, caplen, _orig = record.unpack_from(data, pos)
        pos += 16
        if pos + caplen > size:
            break   # the file was cut off in the middle of a packet, keep what we have
        yield ts_sec + ts_frac * unit, linktype, data[pos:pos + caplen]
        pos += caplen


def _iter_pcapng(data: bytes) -> Iterator[Tuple[float, int, bytes]]:
    """pcapng (the default format of current Wireshark): a list of typed blocks."""
    pos, size = 0, len(data)
    endian = "<"
    interfaces: List[Tuple[int, float]] = []   # one (linktype, seconds per timestamp tick) per interface
    while pos + 12 <= size:
        if data[pos:pos + 4] == _PCAPNG_SECTION_HEADER:
            # A new section starts here. Its byte-order magic tells us how to read numbers.
            magic = data[pos + 8:pos + 12]
            if magic == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif magic == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            else:
                raise CaptureError("The pcapng file has an unreadable section header.")
            interfaces = []
        block_type, block_len = struct.unpack_from(endian + "II", data, pos)
        if block_len < 12 or pos + block_len > size:
            break
        body = data[pos + 8:pos + block_len - 4]

        if block_type == 1:   # Interface Description Block: link type and timestamp resolution
            linktype = struct.unpack_from(endian + "H", body, 0)[0]
            unit = 1e-6   # default is microseconds
            off = 8
            while off + 4 <= len(body):
                code, olen = struct.unpack_from(endian + "HH", body, off)
                off += 4
                if code == 0:
                    break
                if code == 9 and olen >= 1:   # if_tsresol option
                    v = body[off]
                    unit = 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
                off += (olen + 3) & ~3
            interfaces.append((linktype, unit))

        elif block_type == 6 and len(body) >= 20:   # Enhanced Packet Block: one captured packet
            iface, ts_hi, ts_lo, caplen, _orig = struct.unpack_from(endian + "IIIII", body, 0)
            linktype, unit = interfaces[iface] if iface < len(interfaces) else (1, 1e-6)
            yield ((ts_hi << 32) | ts_lo) * unit, linktype, body[20:20 + caplen]

        pos += block_len


def iter_frames(data: bytes) -> Iterator[Tuple[float, int, bytes]]:
    """Yields (arrival time in seconds, link type, raw frame bytes) for every packet in the file."""
    head = data[:4]
    if head[:2] == b"\x1f\x8b":
        raise CaptureError("This file is gzip-compressed. Unzip it first, then load the .pcap or .pcapng inside.")
    if head == _PCAPNG_SECTION_HEADER:
        return _iter_pcapng(data)
    if head in _PCAP_MAGICS:
        return _iter_pcap(data)
    raise CaptureError("This is not a .pcap or .pcapng capture file.")


# --------------------------------------------------------------------------------------
# 2. Link layer, IP and UDP
# --------------------------------------------------------------------------------------

_IPV4, _IPV6 = 0x0800, 0x86DD
_VLAN_TYPES = (0x8100, 0x88A8, 0x9100)


def _ip_from_frame(frame: bytes, linktype: int) -> Optional[bytes]:
    """Strips the link-layer header and returns the IP packet inside, or None if there is none."""
    if linktype == 1:                                   # Ethernet
        if len(frame) < 14:
            return None
        off = 14
        ethertype = int.from_bytes(frame[12:14], "big")
        while ethertype in _VLAN_TYPES and len(frame) >= off + 4:   # skip VLAN tags
            ethertype = int.from_bytes(frame[off + 2:off + 4], "big")
            off += 4
        return frame[off:] if ethertype in (_IPV4, _IPV6) else None
    if linktype in (0, 108):                            # BSD loopback (macOS lo0)
        return frame[4:]
    if linktype == 113:                                 # Linux "cooked" capture
        if len(frame) < 16 or int.from_bytes(frame[14:16], "big") not in (_IPV4, _IPV6):
            return None
        return frame[16:]
    if linktype == 276:                                 # Linux "cooked" capture v2
        if len(frame) < 20 or int.from_bytes(frame[0:2], "big") not in (_IPV4, _IPV6):
            return None
        return frame[20:]
    if linktype in (12, 14, 101, 228, 229):             # raw IP, no link header
        return frame
    return None


def _udp_from_ip(ip: bytes) -> Optional[Tuple[str, str, int, int, bytes]]:
    """Returns (src ip, dst ip, src port, dst port, UDP payload) or None if it is not UDP."""
    if not ip:
        return None
    version = ip[0] >> 4
    if version == 4:
        if len(ip) < 28:
            return None
        ihl = (ip[0] & 0x0F) * 4
        if ihl < 20 or len(ip) < ihl + 8 or ip[9] != 17:
            return None
        flags_frag = int.from_bytes(ip[6:8], "big")
        if (flags_frag & 0x1FFF) or (flags_frag & 0x2000):
            return None   # fragmented packets are skipped (voice packets are tiny)
        total = int.from_bytes(ip[2:4], "big")
        end = min(len(ip), total) if total >= ihl + 8 else len(ip)
        udp = ip[ihl:end]
        src = socket.inet_ntop(socket.AF_INET, ip[12:16])
        dst = socket.inet_ntop(socket.AF_INET, ip[16:20])
    elif version == 6:
        if len(ip) < 48:
            return None
        next_header, off = ip[6], 40
        payload_len = int.from_bytes(ip[4:6], "big")
        end = min(len(ip), 40 + payload_len) if payload_len else len(ip)
        while next_header in (0, 43, 60):   # skip hop-by-hop / routing / destination options
            if off + 8 > len(ip):
                return None
            next_header, off = ip[off], off + (ip[off + 1] + 1) * 8
        if next_header != 17:
            return None
        udp = ip[off:end]
        src = socket.inet_ntop(socket.AF_INET6, ip[8:24])
        dst = socket.inet_ntop(socket.AF_INET6, ip[24:40])
    else:
        return None
    if len(udp) < 8:
        return None
    sport, dport, ulen = struct.unpack_from(">HHH", udp, 0)
    payload = udp[8:ulen] if 8 <= ulen <= len(udp) else udp[8:]
    return src, dst, sport, dport, payload


# --------------------------------------------------------------------------------------
# 3. RTP
# --------------------------------------------------------------------------------------

@dataclass
class RtpPacket:
    arrival: float          # capture time in seconds
    seq: int                # 16 bit sequence number
    timestamp: int          # 32 bit RTP timestamp (in sample-clock ticks)
    payload_type: int
    marker: bool
    payload_len: int        # audio bytes, header and padding excluded


def parse_rtp(payload: bytes) -> Optional[Tuple[int, int, int, int, bool, int]]:
    """
    Checks whether a UDP payload looks like an RTP packet.
    Returns (seq, timestamp, ssrc, payload_type, marker, payload_len) or None.
    The fixed RTP header is 12 bytes: version/flags, marker+type, sequence number,
    timestamp and SSRC (a random ID for the stream).
    """
    if len(payload) < 12:
        return None
    b0, b1 = payload[0], payload[1]
    if (b0 >> 6) != 2:                 # RTP version must be 2 (this also rejects STUN and DTLS)
        return None
    if 192 <= b1 <= 223:               # RTCP control packets share the port, they are not audio
        return None
    csrc_count = b0 & 0x0F
    header_len = 12 + 4 * csrc_count
    if b0 & 0x10:                      # header extension present
        if len(payload) < header_len + 4:
            return None
        header_len += 4 + 4 * int.from_bytes(payload[header_len + 2:header_len + 4], "big")
    pad = payload[-1] if (b0 & 0x20) and len(payload) > 0 else 0
    payload_len = len(payload) - header_len - pad
    if payload_len < 0:
        return None
    seq, ts, ssrc = struct.unpack_from(">HII", payload, 2)
    return seq, ts, ssrc, b1 & 0x7F, bool(b1 & 0x80), payload_len


# Audio clock rate for the fixed RTP payload types (RFC 3551). Newer codecs such as Opus use
# a dynamic type, so for those the rate is estimated from the stream itself.
_STATIC_CLOCK_RATES = {
    0: 8000, 3: 8000, 4: 8000, 5: 8000, 6: 16000, 7: 8000, 8: 8000, 9: 8000,
    10: 44100, 11: 44100, 12: 8000, 13: 8000, 15: 8000, 16: 11025, 17: 22050, 18: 8000,
}
_COMMON_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 90000)
_AUDIO_RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)

StreamKey = Tuple[str, int, str, int, int]   # src ip, src port, dst ip, dst port, ssrc


@dataclass
class RtpStream:
    key: StreamKey
    packets: List[RtpPacket] = field(default_factory=list)

    @property
    def ssrc(self) -> int:
        return self.key[4]

    def main_payload_type(self) -> int:
        return Counter(p.payload_type for p in self.packets).most_common(1)[0][0]

    def clock_rate(self) -> int:
        """RTP clock rate in Hz: from the payload type if it is a fixed one, else estimated."""
        pt = self.main_payload_type()
        if pt in _STATIC_CLOCK_RATES:
            return _STATIC_CLOCK_RATES[pt]
        first, last = self.packets[0], self.packets[-1]
        span = last.arrival - first.arrival
        ticks = (last.timestamp - first.timestamp) & 0xFFFFFFFF
        if span < 1.0 or ticks == 0 or ticks > 0x7FFFFFFF:
            return 48000
        estimate = ticks / span
        nearest = min(_COMMON_RATES, key=lambda r: abs(r - estimate))
        return nearest if abs(nearest - estimate) / nearest < 0.1 else int(round(estimate))

    def summary(self) -> dict:
        pk = self.packets
        duration = max(0.0, pk[-1].arrival - pk[0].arrival) if pk else 0.0
        rate = self.clock_rate() if pk else 0
        pps = (len(pk) - 1) / duration if duration > 0 else 0.0
        return {
            "ssrc": f"0x{self.ssrc:08x}",
            "ssrc_int": self.ssrc,
            "from": f"{self.key[0]}:{self.key[1]}",
            "to": f"{self.key[2]}:{self.key[3]}",
            "packets": len(pk),
            "duration_s": round(duration, 2),
            "payload_types": dict(Counter(p.payload_type for p in pk)),
            "clock_rate": rate,
            "packets_per_second": round(pps, 1),
            "looks_like_audio": rate in _AUDIO_RATES and 10 <= pps <= 120,
        }


def read_rtp_streams(data: bytes) -> Dict[StreamKey, RtpStream]:
    """Reads a whole capture and returns every RTP stream found in it, keyed by stream."""
    streams: Dict[StreamKey, RtpStream] = {}
    for arrival, linktype, frame in iter_frames(data):
        ip = _ip_from_frame(frame, linktype)
        if ip is None:
            continue
        udp = _udp_from_ip(ip)
        if udp is None:
            continue
        src, dst, sport, dport, payload = udp
        rtp = parse_rtp(payload)
        if rtp is None:
            continue
        seq, ts, ssrc, pt, marker, plen = rtp
        key = (src, sport, dst, dport, ssrc)
        stream = streams.get(key)
        if stream is None:
            stream = streams[key] = RtpStream(key)
        stream.packets.append(RtpPacket(arrival, seq, ts, pt, marker, plen))
    # Random UDP traffic can look a little like RTP for a packet or two, so tiny streams are dropped
    return {k: s for k, s in streams.items() if len(s.packets) >= 10}


def choose_default_stream(streams: Dict[StreamKey, RtpStream]) -> Optional[RtpStream]:
    """Picks the stream most likely to be the voice call: audio-like timing, then the most packets."""
    if not streams:
        return None
    ranked = sorted(
        streams.values(),
        key=lambda s: (s.summary()["looks_like_audio"], len(s.packets)),
        reverse=True,
    )
    return ranked[0]


# --------------------------------------------------------------------------------------
# 4. Turning a stream into something the analyzer can replay
# --------------------------------------------------------------------------------------

@dataclass
class ReplayPacket:
    arrival: float      # seconds since the first packet arrived
    send_time: float    # sender clock in seconds, see prepare_replay for how it is anchored
    seq: int            # 16 bit sequence number as it was on the wire
    ext_seq: int        # sequence number with wrap-around removed (counts past 65535)
    timestamp: int      # raw RTP timestamp
    payload_len: int
    marker: bool


def prepare_replay(stream: RtpStream, base_delay_ms: float = 40.0,
                   clock_rate: Optional[int] = None) -> Tuple[List[ReplayPacket], dict]:
    """
    Converts a stream into replay packets.

    A capture is taken at one point, so it only knows when each packet ARRIVED. The sender's
    clock is read from the RTP timestamp: timestamp / clock rate = sender time. That is exactly
    how RFC 3550 measures jitter, so jitter and loss are fully real.

    What a single capture cannot know is the true one-way delay, because the sender's clock
    and the capture clock are different clocks. So the fastest packet in the stream is given
    an ASSUMED delay (base_delay_ms), and every other packet gets that plus the extra delay it
    really experienced. The variation is real, the starting point is an assumption.
    """
    rate = int(clock_rate or stream.clock_rate())
    packets = sorted(stream.packets, key=lambda p: p.arrival)   # capture order = arrival order
    if not packets:
        raise CaptureError("The selected stream has no packets.")

    t0 = packets[0].arrival
    seen = set()
    out: List[ReplayPacket] = []
    duplicates = reordered = 0
    max_ext: Optional[int] = None
    max_ts_ext: Optional[int] = None
    ts_first = packets[0].timestamp

    for p in packets:
        # Unwrap the 16 bit sequence number so 65535 -> 0 is not mistaken for a huge jump back
        if max_ext is None:
            ext = p.seq
            max_ext = ext
        else:
            d = (p.seq - (max_ext & 0xFFFF)) & 0xFFFF
            if d < 0x8000:
                ext = max_ext + d
                max_ext = max(max_ext, ext)
            else:
                ext = max_ext - (0x10000 - d)
                reordered += 1
        if ext in seen:
            duplicates += 1        # a retransmitted copy, count each packet once
            continue
        seen.add(ext)

        # Unwrap the 32 bit RTP timestamp the same way
        if max_ts_ext is None:
            ts_ext = p.timestamp
            max_ts_ext = ts_ext
        else:
            dt = (p.timestamp - (max_ts_ext & 0xFFFFFFFF)) & 0xFFFFFFFF
            if dt < 0x80000000:
                ts_ext = max_ts_ext + dt
                max_ts_ext = max(max_ts_ext, ts_ext)
            else:
                ts_ext = max_ts_ext - (0x100000000 - dt)

        send_rel = (ts_ext - ts_first) / rate
        out.append(ReplayPacket(p.arrival - t0, send_rel, p.seq, ext, p.timestamp, p.payload_len, p.marker))

    # Anchor the sender clock: the fastest packet gets exactly base_delay_ms of transit time
    base = base_delay_ms / 1000.0
    fastest = min(rp.arrival - rp.send_time for rp in out)
    for rp in out:
        rp.send_time = rp.send_time + fastest - base

    first_ext, last_ext = out[0].ext_seq, max(rp.ext_seq for rp in out)
    expected = last_ext - min(rp.ext_seq for rp in out) + 1
    info = {
        "clock_rate": rate,
        "packets_in_capture": len(out),
        "packets_expected": expected,
        "packets_missing_in_capture": max(0, expected - len(out)),
        "duplicates_removed": duplicates,
        "reordered_arrivals": reordered,
        "duration_s": round(out[-1].arrival, 2),
        "assumed_base_delay_ms": base_delay_ms,
        "first_seq": out[0].seq,
        "first_ext_seq": first_ext,
    }
    return out, info
