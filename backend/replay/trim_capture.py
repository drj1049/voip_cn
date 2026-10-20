"""
Shrinks a capture down to ONE RTP stream, so a long Wireshark recording (which also holds every
other thing your computer sent over the network) becomes a small file that holds only the call.

Usage (run from the project folder):
    python -m backend.replay.trim_capture recording.pcapng voice_only.pcap
    python -m backend.replay.trim_capture recording.pcapng voice_only.pcap --ssrc 0x00001a0a

By default the voice stream is chosen automatically, and the hardware (MAC) addresses are
blanked. The output is a classic .pcap file, which the replay reads like any other capture.
"""
import argparse
import struct
import sys
from typing import List, Optional, Tuple

from backend.replay.pcap_reader import (
    CaptureError, _ip_from_frame, _udp_from_ip, choose_default_stream, iter_frames, parse_rtp, read_rtp_streams,
)


def trim_capture(data: bytes, ssrc: Optional[int] = None, keep_macs: bool = False) -> Tuple[bytes, dict]:
    """Returns (bytes of a new .pcap holding only the chosen stream, a description of what was kept)."""
    streams = read_rtp_streams(data)
    if not streams:
        raise CaptureError("No RTP audio was found in this capture.")
    if ssrc is not None:
        matches = [s for s in streams.values() if s.ssrc == ssrc]
        if not matches:
            raise CaptureError(f"No stream with SSRC {ssrc} in this capture.")
        stream = max(matches, key=lambda s: len(s.packets))
    else:
        stream = choose_default_stream(streams)
    wanted_key = stream.key

    kept: List[Tuple[float, bytes]] = []
    linktype: Optional[int] = None
    for arrival, lt, frame in iter_frames(data):
        ip = _ip_from_frame(frame, lt)
        udp = _udp_from_ip(ip) if ip else None
        if udp is None:
            continue
        src, dst, sport, dport, payload = udp
        rtp = parse_rtp(payload)
        if rtp is None or (src, sport, dst, dport, rtp[2]) != wanted_key:
            continue
        if linktype is None:
            linktype = lt
        if lt != linktype:
            continue    # a classic pcap file has a single link type
        if lt == 1 and not keep_macs and len(frame) >= 14:
            frame = b"\x00" * 12 + frame[12:]     # blank both hardware addresses
        kept.append((arrival, frame))

    out = bytearray(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 262144, linktype or 1))
    for arrival, frame in kept:
        sec = int(arrival)
        usec = int(round((arrival - sec) * 1_000_000))
        if usec >= 1_000_000:
            sec, usec = sec + 1, 0
        out += struct.pack("<IIII", sec, usec, len(frame), len(frame)) + frame
    return bytes(out), {"ssrc": f"0x{stream.ssrc:08x}", "packets_kept": len(kept), "bytes": len(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Keep only one RTP stream from a capture file.")
    ap.add_argument("input")
    ap.add_argument("output", help="the new .pcap file to write")
    ap.add_argument("--ssrc", help="which stream to keep, e.g. 0x00001a0a (default: the voice stream)")
    ap.add_argument("--keep-macs", action="store_true", help="do not blank the hardware addresses")
    args = ap.parse_args(argv)
    with open(args.input, "rb") as f:
        data = f.read()
    try:
        out, info = trim_capture(data, int(args.ssrc, 0) if args.ssrc else None, args.keep_macs)
    except CaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    with open(args.output, "wb") as f:
        f.write(out)
    print(f"Kept stream {info['ssrc']}: {info['packets_kept']} packets, {info['bytes'] / 1024:.0f} KB -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
