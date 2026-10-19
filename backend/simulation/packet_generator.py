"""
RTP-like Packet Generator for Synthetic VoIP Voice Stream Simulation
"""
import time
from typing import Dict, Any

class PacketGenerator:
    """
    Generates synthetic RTP-like voice packet headers and metadata.
    Simulates a standard 8kHz G.711 PCM codec stream (160 bytes / 20ms).
    """

    def __init__(self, initial_sequence: int = 1):
        # The sequence number is just a counter (1, 2, 3...). The receiver uses it to spot
        # gaps, and a gap means a packet was lost.
        self.sequence_number: int = initial_sequence
        # RTP timestamp increments by 160 samples every 20ms (8000 Hz sample rate)
        self.rtp_timestamp: int = 0
        # 20 ms of 8000 samples/sec audio is 160 samples, and G.711 uses 1 byte per sample.
        # The packet only carries this number, there is no real sound inside.
        self.payload_size: int = 160

    def generate_packet(self) -> Dict[str, Any]:
        """
        Creates a new RTP-like packet payload dictionary.
        """
        # send_time is when the packet left. The receiver compares it with the arrival time
        # to work out how long the trip took (latency) and how uneven it was (jitter).
        current_time = time.time()
        packet = {
            "sequence_number": self.sequence_number,
            "timestamp": self.rtp_timestamp,
            "send_time": current_time,
            "payload_size": self.payload_size
        }

        # Get ready for the next packet. The % 65536 is because a real RTP sequence number
        # only has 16 bits, so after 65535 it wraps back to 0.
        self.sequence_number = (self.sequence_number + 1) % 65536  # 16-bit sequence roll
        self.rtp_timestamp = (self.rtp_timestamp + 160) % (2**32)

        return packet

    def reset(self, initial_sequence: int = 1):
        """Resets sequence counter and RTP timestamp."""
        self.sequence_number = initial_sequence
        self.rtp_timestamp = 0
