"""
FastAPI Main Server Application for Real-Time VoIP Call Quality Analyzer
"""
import asyncio
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.simulation.simulator import VoIPSimulator
from backend.websocket_manager import websocket_manager

app = FastAPI(
    title="Real-Time VoIP Call Quality Analyzer",
    description="Computer Networks Review 2 Project Simulation & QoS Metric Analysis Engine",
    version="1.0.0"
)

# Enable CORS for React frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global VoIP Simulator Instance
simulator = VoIPSimulator()

class ImpairmentConfigRequest(BaseModel):
    delay_ms: Optional[float] = Field(None, ge=0.0, le=500.0, description="Base delay in ms (0-500)")
    jitter_ms: Optional[float] = Field(None, ge=0.0, le=100.0, description="Jitter variation in ms (0-100)")
    packet_loss_pct: Optional[float] = Field(None, ge=0.0, le=30.0, description="Packet loss percentage (0-30)")

@app.on_event("startup")
def startup_event():
    """Starts the VoIP simulation by default upon server launch."""
    simulator.start()

@app.on_event("shutdown")
def shutdown_event():
    """Stops the simulator and cleans up resources on shutdown."""
    simulator.stop()

@app.get("/")
def get_root():
    """Root endpoint verifying API availability."""
    return {
        "project": "Real-Time VoIP Call Quality Analyzer",
        "status": "Online",
        "simulation_running": simulator.is_running
    }

@app.get("/status")
def get_status():
    """Returns simulator running state."""
    return {
        "is_running": simulator.is_running,
        "config": simulator.get_config()
    }

@app.post("/simulation/start")
def start_simulation():
    """Starts the VoIP UDP stream simulation."""
    success = simulator.start()
    return {"status": "started" if success else "already_running"}

@app.post("/simulation/stop")
def stop_simulation():
    """Stops the VoIP UDP stream simulation."""
    success = simulator.stop()
    return {"status": "stopped" if success else "already_stopped"}

@app.post("/simulation/reset")
def reset_simulation():
    """Resets packet counters and metric histories."""
    simulator.reset()
    return {"status": "reset_complete"}

@app.get("/metrics")
def get_metrics():
    """Returns snapshot of current call quality metrics."""
    return simulator.get_current_metrics()

@app.get("/config")
def get_config():
    """Returns active network impairment parameters."""
    return simulator.get_config()

@app.post("/config")
def update_config(req: ImpairmentConfigRequest):
    """Updates network impairment settings dynamically."""
    simulator.update_config(req.delay_ms, req.jitter_ms, req.packet_loss_pct)
    return {
        "message": "Config updated successfully",
        "current_config": simulator.get_config()
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket stream transmitting live telemetry metrics to the dashboard."""
    await websocket_manager.connect(websocket)
    try:
        while True:
            metrics = simulator.get_current_metrics()
            await websocket.send_json(metrics)
            await asyncio.sleep(0.25)  # Stream update every 250ms
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception:
        websocket_manager.disconnect(websocket)
