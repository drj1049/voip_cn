"""
Centralized Configuration for Real-Time VoIP Call Quality Analyzer
"""
import os

class Config:
    # Where the fake call travels. 127.0.0.1 is "this same computer", so the sender and
    # receiver both live inside this one program and no real network is touched.
    # Both can be overridden with environment variables if you ever need to.
    UDP_IP: str = os.getenv("UDP_IP", "127.0.0.1")
    UDP_PORT: int = int(os.getenv("UDP_PORT", "5005"))

    # VoIP Stream Parameters (G.711 standard simulation)
    # Real phones send one small packet every 20 ms, so 1 second of call = 50 packets.
    PACKET_INTERVAL_SEC: float = 0.02  # 20ms frame size -> 50 packets/sec
    PAYLOAD_SIZE_BYTES: int = 160      # 160 bytes for 20ms G.711 speech

    # What the network looks like when the app first starts (a healthy connection).
    # The sliders on the dashboard change these while the app is running.
    # Default Impairment Settings
    DEFAULT_DELAY_MS: float = 20.0     # Base propagation/queuing delay (ms)
    DEFAULT_JITTER_MS: float = 2.0     # Delay variation standard magnitude (ms)
    DEFAULT_PACKET_LOSS_PCT: float = 0.0 # Packet loss percentage (0 - 30%)

    # MOS score ranges and what they are called. Note: mos.py does its own classification
    # with the same cut-offs, this table is kept as a readable reference of the bands.
    # MOS Threshold Categories (ITU-T G.107 reference ranges)
    MOS_CATEGORIES = {
        "EXCELLENT": (4.3, 5.0),
        "GOOD": (4.0, 4.3),
        "FAIR": (3.6, 4.0),
        "POOR": (3.1, 3.6),
        "BAD": (1.0, 3.1)
    }

config = Config()
