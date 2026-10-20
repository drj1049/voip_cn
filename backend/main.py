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
from backend.replay.pcap_reader import CaptureError
from backend.replay.replayer import (
    ReplaySimulator, capture_dir, capture_path, list_captures, safe_capture_name, summarize_capture,
)
from backend.websocket_manager import websocket_manager

app = FastAPI(
    title="Real-Time VoIP Call Quality Analyzer",
    description="Network impairment simulation and live VoIP call quality (QoS and MOS) analysis",
    version="1.0.0"
)

# Enable CORS for React frontend interaction
# (CORS lets the dashboard on port 3000 talk to this server on port 8000 during development.
# "*" means any origin is allowed, which is fine for a project like this one.)
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
# There is only one simulation for the whole app, so everyone who opens the dashboard
# (including on Render) sees and controls the same call.
simulator = VoIPSimulator()

# Second source of packets: a recorded real call. Only one source is active at a time,
# and every endpoint below (metrics, config, start, stop, WebSocket) talks to the active one.
replayer = ReplaySimulator()
_active = {"source": simulator}

def current_source():
    return _active["source"]

# What the dashboard sends when a slider moves. Every field is optional, so the dashboard
# can send only what changed. The ge/le limits make the API reject silly values with an error.
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
    """Starts the VoIP simulation by default upon server launch.
    The call is already running by the time you open the dashboard."""
    simulator.start()

@app.on_event("shutdown")
def shutdown_event():
    """Stops the simulator and cleans up resources on shutdown."""
    simulator.stop()
    replayer.stop()

@app.get("/")
def get_root():
    """Serves the dashboard if it has been built, otherwise reports API status."""
    # If "npm run build" has been run, show the dashboard; otherwise show a small status message
    index_file = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    return {
        "project": "Real-Time VoIP Call Quality Analyzer",
        "status": "Online",
        "simulation_running": current_source().is_running
    }

@app.get("/status")
def get_status():
    """Returns simulator running state.
    Render also calls this to check that the app is alive (see healthCheckPath in render.yaml)."""
    return {
        "is_running": current_source().is_running,
        "mode": "replay" if current_source() is replayer else "simulation",
        "config": current_source().get_config()
    }

@app.post("/simulation/start")
def start_simulation():
    """Starts the VoIP UDP stream simulation (and switches back from replay mode if needed)."""
    if current_source() is replayer:
        replayer.stop()
        _active["source"] = simulator
    success = simulator.start()
    return {"status": "started" if success else "already_running"}

@app.post("/simulation/stop")
def stop_simulation():
    """Stops the VoIP UDP stream simulation."""
    success = current_source().stop()
    return {"status": "stopped" if success else "already_stopped"}

@app.post("/simulation/reset")
def reset_simulation():
    """Resets packet counters and metric histories."""
    current_source().reset()
    return {"status": "reset_complete"}

@app.get("/metrics")
def get_metrics():
    """Returns snapshot of current call quality metrics."""
    return current_source().get_current_metrics()

@app.get("/config")
def get_config():
    """Returns active network impairment parameters."""
    return current_source().get_config()

@app.post("/config")
def update_config(req: ImpairmentConfigRequest):
    """Updates network impairment settings dynamically."""
    current_source().update_config(
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
        "current_config": current_source().get_config()
    }

# Audio mode. The dashboard shrinks every clip to 8 kHz mono before uploading, so even a
# 30 second clip is well under 0.5 MB. The 2 MB cap just stops someone sending something huge.
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
    # Check the text options by hand (a clear 400 error beats a confusing crash later)
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

    # The processing is plain CPU work, so run it in a worker thread. Otherwise the server
    # would freeze (and the live WebSocket updates would stall) while the clip is processed.
    result = await run_in_threadpool(
        process_audio, samples,
        delay_ms=delay_ms, jitter_ms=jitter_ms, packet_loss_pct=packet_loss_pct,
        loss_mode=loss_mode, burst_length=burst_length,
        buffer_mode=buffer_mode, buffer_ms=buffer_ms,
    )
    # JSON cannot hold raw bytes, so the audio goes back as base64 text. The browser plays
    # it straight from a data: URL.
    result["original_wav"] = base64.b64encode(result["original_wav"]).decode("ascii")
    result["damaged_wav"] = base64.b64encode(result["damaged_wav"]).decode("ascii")
    return result


# ---------------------------------------------------------------------------------------
# Real call replay. Packets recorded from a real call (a Wireshark / tcpdump capture) are
# fed through the same jitter, loss and MOS code, instead of the synthetic packet generator.
# ---------------------------------------------------------------------------------------
MAX_CAPTURE_UPLOAD_BYTES = 40 * 1024 * 1024   # 40 MB. Tip: filter to "rtp" in Wireshark before saving.

def _read_capture_file(name: str) -> bytes:
    try:
        path = capture_path(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Capture file not found")
    with open(path, "rb") as f:
        return f.read()

@app.get("/replay/captures")
def replay_captures():
    """Lists the capture files that can be replayed."""
    return {
        "captures": list_captures(),
        "mode": "replay" if current_source() is replayer else "simulation",
        "loaded": replayer.capture_name,
    }

@app.post("/replay/upload")
async def replay_upload(request: Request, name: str = Query(..., description="File name, ending in .pcap or .pcapng")):
    """The request body is the capture file. It is checked, saved, and its RTP streams are listed."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="No file received")
    if len(body) > MAX_CAPTURE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Capture is too large (40 MB maximum). Filter to RTP in Wireshark and save again.")
    try:
        safe = safe_capture_name(name)
        summary = await run_in_threadpool(summarize_capture, body)
    except (ValueError, CaptureError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    os.makedirs(capture_dir(), exist_ok=True)
    with open(capture_path(safe), "wb") as f:
        f.write(body)
    return {"name": safe, **summary}

@app.get("/replay/streams")
async def replay_streams(capture: str = Query(...)):
    """Lists the RTP streams found inside a capture file."""
    data = _read_capture_file(capture)
    try:
        summary = await run_in_threadpool(summarize_capture, data)
    except CaptureError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"name": capture, **summary}

@app.post("/replay/start")
async def replay_start(
    capture: str = Query(...),
    ssrc: Optional[int] = Query(None, description="Which RTP stream to replay (default: the voice stream)"),
    base_delay_ms: float = Query(40.0, ge=0.0, le=500.0, description="Assumed one-way delay of the fastest packet"),
    speed: float = Query(1.0, ge=0.25, le=100.0, description="1 = real time"),
):
    """Loads a capture and starts replaying it. The live simulator is stopped while replay is active."""
    data = _read_capture_file(capture)
    simulator.stop()
    replayer.stop()
    try:
        info = await run_in_threadpool(replayer.load_capture, capture, data, ssrc, base_delay_ms, speed)
    except CaptureError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    _active["source"] = replayer
    replayer.start()
    return {"status": "replaying", "stream": info, "config": replayer.get_config()}

@app.post("/replay/restart")
def replay_restart():
    """Plays the loaded capture again from the beginning."""
    if not replayer.packets:
        raise HTTPException(status_code=409, detail="No capture is loaded yet")
    simulator.stop()
    replayer.stop()
    _active["source"] = replayer
    replayer.start()
    return {"status": "replaying", "config": replayer.get_config()}

@app.post("/replay/stop")
def replay_stop():
    success = replayer.stop()
    return {"status": "stopped" if success else "already_stopped"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket stream transmitting live telemetry metrics to the dashboard."""
    await websocket_manager.connect(websocket)
    try:
        # Push the current numbers to this browser four times a second until it disconnects
        while True:
            metrics = current_source().get_current_metrics()
            await websocket.send_json(metrics)
            await asyncio.sleep(0.25)  # Stream update every 250ms
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception:
        websocket_manager.disconnect(websocket)


# Static files for the built dashboard (JS and CSS bundles).
# Only mounted when "npm run build" has produced them.
if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")
