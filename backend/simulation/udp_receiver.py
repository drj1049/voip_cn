"""
UDP Socket Receiver Layer for Localhost VoIP Packet Reception
"""
import socket
import json
import time
from typing import Dict, Any, Optional

class UDPReceiver:
    """
    Listens on a local UDP socket port, receives packets, and captures precise receive timestamp.
    """

    def __init__(self, bind_ip: str, bind_port: int, timeout_sec: float = 0.1):
        self.bind_ip: str = bind_ip
        self.bind_port: int = bind_port
        self.sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Enable address reuse and set timeout so non-blocking loops can check exit flags
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.bind_ip, self.bind_port))
        self.sock.settimeout(timeout_sec)

    def receive_packet(self) -> Optional[Dict[str, Any]]:
        """
        Attempts to read a single packet from the socket buffer.
        Attaches high-precision receive timestamp.
        Returns packet dict or None if timeout occurs.
        """
        try:
            data, addr = self.sock.recvfrom(2048)
            receive_time = time.time()
            packet_dict = json.loads(data.decode("utf-8"))
            packet_dict["receive_time"] = receive_time
            return packet_dict
        except socket.timeout:
            return None
        except Exception:
            return None

    def close(self):
        """Closes the receiver UDP socket."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
