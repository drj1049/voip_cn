# Real-Time VoIP Call Quality Analyzer

A VoIP network simulator and live quality dashboard. It sends synthetic RTP-style voice packets over UDP, applies controlled delay, jitter and packet loss, measures what arrives, and scores the call with the ITU-T G.107 E-model (MOS). Built with Python (FastAPI, UDP sockets) and React (Vite, Recharts).

## What it does

- Sends 20 ms voice packets (50 per second, 160-byte G.711-style payload) over UDP on 127.0.0.1.
- Impairment engine: delay 0 to 500 ms, jitter 0 to 100 ms, packet loss 0 to 30 percent. Loss can be random or bursty (two-state Gilbert-Elliott model).
- Optional jitter buffer (off, fixed or adaptive) that discards packets arriving too late.
- Metrics: latency, RFC 3550 interarrival jitter, sequence-gap packet loss (rolling window while live, whole-run totals once stopped), burst ratio, late-packet percentage.
- Quality score: R-factor and MOS from a simplified ITU-T G.107 E-model, with a rating from Excellent to Bad.
- Live dashboard updated over WebSocket every 250 ms, with quick scenarios and an Advanced section for loss pattern and jitter buffer.

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

For frontend development, run `npm run dev` inside `frontend/` and open http://localhost:3000. It talks to the backend on port 8000.

## Tests and experiments

```bash
python -m pytest -v tests          # 21 tests
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
  main.py                  FastAPI app, REST, WebSocket, serves the dashboard
  config.py                UDP address and defaults
  websocket_manager.py     Telemetry broadcast
  simulation/              packet_generator, impairment, udp_sender, udp_receiver, simulator
  metrics/                 latency, jitter, packet_loss, jitter_buffer, mos
frontend/src/components/   Dashboard, ControlPanel, MetricCard, MosGauge, charts
tests/                     unit and integration tests, scenario collector, sweep and experiment scripts
docs/                      architecture, methodology, test cases, sweep graphs
```

## Limitations

- Traffic is synthetic. There is no real audio capture or playback.
- Everything runs on one machine over the loopback interface.
- The E-model here is simplified and has no packet loss concealment, so loss is penalised harshly.
- The adaptive jitter buffer factor was tuned empirically, not derived from a standard.
