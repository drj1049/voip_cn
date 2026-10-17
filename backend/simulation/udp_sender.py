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
        self.sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_packet(self, packet: Dict[str, Any]):
        """
        Serializes packet dictionary to UTF-8 JSON bytes and transmits over UDP.
        """
        payload_bytes = json.dumps(packet).encode("utf-8")
        self.sock.sendto(payload_bytes, (self.target_ip, self.target_port))

    def close(self):
        """Closes the underlying UDP socket."""
        if self.sock:
            self.sock.close()
