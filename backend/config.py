"""
Centralized Configuration for Real-Time VoIP Call Quality Analyzer
"""
import os

class Config:
    # Sockets Configuration
    UDP_IP: str = os.getenv("UDP_IP", "127.0.0.1")
    UDP_PORT: int = int(os.getenv("UDP_PORT", "5005"))

    # VoIP Stream Parameters (G.711 standard simulation)
    PACKET_INTERVAL_SEC: float = 0.02  # 20ms frame size -> 50 packets/sec
    PAYLOAD_SIZE_BYTES: int = 160      # 160 bytes for 20ms G.711 speech

    # Default Impairment Settings
    DEFAULT_DELAY_MS: float = 20.0     # Base propagation/queuing delay (ms)
    DEFAULT_JITTER_MS: float = 2.0     # Delay variation standard magnitude (ms)
    DEFAULT_PACKET_LOSS_PCT: float = 0.0 # Packet loss percentage (0 - 30%)

    # MOS Threshold Categories (ITU-T G.107 reference ranges)
    MOS_CATEGORIES = {
        "EXCELLENT": (4.3, 5.0),
        "GOOD": (4.0, 4.3),
        "FAIR": (3.6, 4.0),
        "POOR": (3.1, 3.6),
        "BAD": (1.0, 3.1)
    }

config = Config()
