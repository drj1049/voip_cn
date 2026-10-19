"""
UDP Socket Sender Layer for Localhost VoIP Packet Transmission
"""
import socket
import json
from typing import Dict, Any

class UDPSender:
    """
    Encapsulates a standard UDP socket to transmit JSON-serialized synthetic voice packets.
    """

    def __init__(self, target_ip: str, target_port: int):
        self.target_ip: str = target_ip
        self.target_port: int = target_port
        # SOCK_DGRAM = UDP. There is no connection or handshake, we just fire packets
        # at an address and hope they arrive, which is exactly how live voice works.
        self.sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_packet(self, packet: Dict[str, Any]):
        """
        Serializes packet dictionary to UTF-8 JSON bytes and transmits over UDP.
        """
        # Packets are plain Python dicts, so we turn them into JSON text and then bytes
        # to send them over the socket. (A real RTP packet is a binary header instead.)
        payload_bytes = json.dumps(packet).encode("utf-8")
        self.sock.sendto(payload_bytes, (self.target_ip, self.target_port))

    def close(self):
        """Closes the underlying UDP socket."""
        if self.sock:
            self.sock.close()
