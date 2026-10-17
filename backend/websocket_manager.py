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
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

websocket_manager = ConnectionManager()
