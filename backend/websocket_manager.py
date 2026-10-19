"""
WebSocket Manager for Broadcasting Real-Time Telemetry to Dashboard
"""
import asyncio
from typing import List
from fastapi import WebSocket

class ConnectionManager:
    """
    Manages active WebSocket connections and handles broadcasting telemetry payloads.
    """

    def __init__(self):
        # Every browser tab that has the dashboard open shows up here as one connection
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accepts incoming WebSocket connection and tracks active socket."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Removes closed WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        """Sends JSON metrics snapshot to all connected dashboard clients."""
        # Not used right now: main.py gives each connection its own sending loop instead.
        # Left here as the simple "send to everyone" option.
        # list(...) makes a copy, because disconnect() below changes the list while we loop
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                # A dead connection (tab closed) just gets dropped, it should not stop the others
                self.disconnect(connection)

# One shared manager for the whole app
websocket_manager = ConnectionManager()
