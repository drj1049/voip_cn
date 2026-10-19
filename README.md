# Real-Time VoIP Call Quality Analyzer

A VoIP network simulator and live quality dashboard. It sends synthetic RTP-style voice packets over UDP, applies controlled delay, jitter and packet loss, measures what arrives, and scores the call with the ITU-T G.107 E-model (MOS). Built with Python (FastAPI, UDP sockets) and React (Vite, Recharts). An audio mode lets you push a real clip through the same network conditions and hear what the receiver would play.

## What it does

- Sends 20 ms voice packets (50 per second, 160-byte G.711-style payload) over UDP on 127.0.0.1.
- Impairment engine: delay 0 to 500 ms, jitter 0 to 100 ms, packet loss 0 to 30 percent. Loss can be random or bursty (two-state Gilbert-Elliott model).
- Optional jitter buffer (off, fixed or adaptive) that discards packets arriving too late.
- Metrics: latency, RFC 3550 interarrival jitter, sequence-gap packet loss (rolling window while live, whole-run totals once stopped), burst ratio, late-packet percentage.
- Quality score: R-factor and MOS from a simplified ITU-T G.107 E-model, with a rating from Excellent to Bad.
- Live dashboard updated over WebSocket every 250 ms, with quick scenarios and an Advanced section for loss pattern and jitter buffer.
- Audio mode: upload a clip (or use the built-in demo melody), apply the current network settings, and play the original next to the damaged version, with a strip showing what happened to every 20 ms packet.

## Architecture

```text
React dashboard  <--- WebSocket / REST --->  FastAPI backend
                                                   |
                                          Simulation controller
                                                   |
        Packet generator -> Impairment engine -> UDP sender ==> UDP receiver
                                                                    |
                          Metrics: latency, jitter, loss, jitter buffer, MOS
```

Audio mode uses the same impairment engine and metric code, but runs offline instead of in real time:

```text
audio clip -> 20 ms frames -> one packet each -> impairment engine -> jitter buffer
           -> frames that made it in time -> damaged audio (silence where packets were lost or late)
```

## Run it

Needs Python 3.10+ and Node.js 18+.

First time only:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

Every time:

```bash
source venv/bin/activate
python -m uvicorn backend.main:app --port 8000
```

Open http://127.0.0.1:8000. The backend serves the built dashboard, so one window is enough.

If you change any frontend code, run `cd frontend && npm run build` again so the backend serves the new version.

For frontend development, run `npm run dev` inside `frontend/` and open http://localhost:3000. It talks to the backend on port 8000.

## Audio mode

Scroll to the Audio mode panel at the bottom of the dashboard.

- Press "Apply network conditions" to use the built-in demo melody, or upload your own file. Any format your browser can play works (mp3, m4a, wav, ogg). It is converted to 8 kHz mono in the browser, and clips over 30 seconds are cut.
- The panel uses the same delay, jitter, loss and Advanced settings as the sliders above. Change them and press the button again.
- Play "Original" and "After the network" to compare. The score and the coloured strip belong to the damaged version: green packets played, red were lost, amber arrived too late for the jitter buffer and were discarded.
- Lost and late packets both become silence. Jitter is only audible when the jitter buffer is on, because the buffer is what discards late packets. The base delay shows up in the score but not in the audio, since the two clips stay lined up for easy comparison.
- Bursty loss at the same average loss sounds clearly worse than random loss, and the score drops to match.

The endpoint behind it is `POST /audio/process`. The body is a WAV file (or empty with `use_demo=true`) and the network settings go in the query string.

## Reading the live gauge

When the jitter buffer is on, it judges every packet against the fastest packet from roughly the last 3 seconds. After you change the delay while the simulation is running, the gauge can look wrong for a few seconds until that window catches up. Pressing Reset clears it straight away.

## Deploy on Render

The repo includes a `Dockerfile` and `render.yaml`. On render.com, choose New > Blueprint, connect the GitHub repo `drj1049/voip_cn`, and deploy. Render builds the dashboard and starts the backend on its own port. The free plan sleeps after about 15 minutes idle, so the first load can take up to a minute. All visitors share one simulation.

## Tests and experiments

```bash
python -m pytest -v tests          # 30 tests
python tests/collect_demo_results.py   # the five standard scenarios
python tests/run_sweep.py          # one-parameter sweeps and graphs
python tests/run_experiments.py    # burst vs random loss, jitter buffer trade-off
```

Sweep and experiment output (CSV, JSON and graphs) goes to `docs/sweep/`.

## Results from the five standard scenarios

Each run lasts about 3 seconds (roughly 140 packets), so measured loss varies from run to run.

| Scenario | Delay / Jitter / Loss set | Latency | RFC 3550 jitter | Measured loss | R-factor | MOS | Rating |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Good network | 20 ms / 2 ms / 0% | 21.09 ms | 1.22 ms | 0.00% | 92.40 | 4.39 | Excellent |
| High latency | 200 ms / 5 ms / 0% | 201.36 ms | 2.75 ms | 0.00% | 83.61 | 4.15 | Good |
| High jitter | 50 ms / 60 ms / 0% | 50.01 ms | 27.01 ms | 0.00% | 90.46 | 4.35 | Excellent |
| Packet loss | 50 ms / 10 ms / 10% | 50.45 ms | 5.91 ms | 12.06% | 21.43 | 1.30 | Bad |
| Poor network | 250 ms / 80 ms / 15% | 254.63 ms | 32.91 ms | 11.89% | 0.00 | 1.00 | Bad |

## Project layout

```text
backend/
  main.py                  FastAPI app, REST, WebSocket, audio endpoint, serves the dashboard
  config.py                UDP address and defaults
  websocket_manager.py     Keeps track of connected dashboards
  simulation/              packet_generator, impairment, udp_sender, udp_receiver, simulator
  metrics/                 latency, jitter, packet_loss, jitter_buffer, mos
  audio/                   processor: clip to packets, through the network, back to audio
frontend/src/components/   Dashboard, ControlPanel, MetricCard, MosGauge, charts, AudioLab
tests/                     unit and integration tests, scenario collector, sweep and experiment scripts
docs/                      architecture, methodology, test cases, sweep graphs
```

## Limitations

- The live simulation uses synthetic packets with no sound inside. Audio mode adds a real clip, but it is still simulated: nothing here is a captured real call, and results have not been compared against real call recordings.
- Audio mode fills missing packets with silence. Real phones hide gaps with loss concealment, so a real bad call sounds smoother than the damaged clip.
- Everything runs on one machine over the loopback interface.
- The E-model here is simplified and has no packet loss concealment, so loss is penalised harshly.
- The adaptive jitter buffer factor was tuned empirically, not derived from a standard.
