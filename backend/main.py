"""
FastAPI Main Server Application for Real-Time VoIP Call Quality Analyzer
"""
import asyncio
import base64
import os
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.audio.processor import decode_wav, make_demo_clip, process_audio
from backend.simulation.simulator import VoIPSimulator
from backend.websocket_manager import websocket_manager

app = FastAPI(
    title="Real-Time VoIP Call Quality Analyzer",
    description="Network impairment simulation and live VoIP call quality (QoS and MOS) analysis",
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

# Built React dashboard (created by "npm run build" inside frontend/).
# When it exists, the backend serves it too, so one command runs everything.
FRONTEND_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"
)

# Global VoIP Simulator Instance
simulator = VoIPSimulator()

class ImpairmentConfigRequest(BaseModel):
    delay_ms: Optional[float] = Field(None, ge=0.0, le=500.0, description="Base delay in ms (0-500)")
    jitter_ms: Optional[float] = Field(None, ge=0.0, le=100.0, description="Jitter variation in ms (0-100)")
    packet_loss_pct: Optional[float] = Field(None, ge=0.0, le=30.0, description="Packet loss percentage (0-30)")
    loss_mode: Optional[str] = Field(None, description="Loss pattern: random or burst")
    burst_length: Optional[float] = Field(None, ge=1.0, le=20.0, description="Average burst length in packets (1-20)")
    buffer_mode: Optional[str] = Field(None, description="Jitter buffer: off, fixed or adaptive")
    buffer_ms: Optional[float] = Field(None, ge=0.0, le=300.0, description="Fixed jitter buffer depth in ms (0-300)")

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
    """Serves the dashboard if it has been built, otherwise reports API status."""
    index_file = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
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
    simulator.update_config(
        delay_ms=req.delay_ms,
        jitter_ms=req.jitter_ms,
        packet_loss_pct=req.packet_loss_pct,
        loss_mode=req.loss_mode,
        burst_length=req.burst_length,
        buffer_mode=req.buffer_mode,
        buffer_ms=req.buffer_ms,
    )
    return {
        "message": "Config updated successfully",
        "current_config": simulator.get_config()
    }

MAX_AUDIO_UPLOAD_BYTES = 2 * 1024 * 1024   # a 30 second 8 kHz clip is under 0.5 MB

@app.post("/audio/process")
async def process_audio_clip(
    request: Request,
    use_demo: bool = Query(False, description="Use the built-in demo clip instead of an upload"),
    delay_ms: float = Query(20.0, ge=0.0, le=500.0),
    jitter_ms: float = Query(2.0, ge=0.0, le=100.0),
    packet_loss_pct: float = Query(0.0, ge=0.0, le=30.0),
    loss_mode: str = Query("random"),
    burst_length: float = Query(5.0, ge=1.0, le=20.0),
    buffer_mode: str = Query("fixed"),
    buffer_ms: float = Query(40.0, ge=0.0, le=300.0),
):
    """
    Audio mode. The request body is a WAV file (or empty with use_demo=true).
    The clip is cut into 20 ms packets, sent through the simulated network with
    the given settings, and rebuilt. Returns the metrics plus the original and
    damaged audio as base64 WAV so the dashboard can play both.
    """
    if loss_mode not in ("random", "burst"):
        raise HTTPException(status_code=400, detail="loss_mode must be random or burst")
    if buffer_mode not in ("off", "fixed", "adaptive"):
        raise HTTPException(status_code=400, detail="buffer_mode must be off, fixed or adaptive")

    if use_demo:
        samples = make_demo_clip()
    else:
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="No audio received")
        if len(body) > MAX_AUDIO_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Audio file is too large (2 MB maximum)")
        try:
            samples = decode_wav(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    result = await run_in_threadpool(
        process_audio, samples,
        delay_ms=delay_ms, jitter_ms=jitter_ms, packet_loss_pct=packet_loss_pct,
        loss_mode=loss_mode, burst_length=burst_length,
        buffer_mode=buffer_mode, buffer_ms=buffer_ms,
    )
    result["original_wav"] = base64.b64encode(result["original_wav"]).decode("ascii")
    result["damaged_wav"] = base64.b64encode(result["damaged_wav"]).decode("ascii")
    return result

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


# Static files for the built dashboard (JS and CSS bundles)
if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")
