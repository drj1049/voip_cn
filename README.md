# Real-Time VoIP Call Quality Analyzer

**Computer Networks Project — Review 2: Design & Implementation**

A controlled, real-time VoIP network simulation and QoS telemetry system built with **Python (FastAPI + UDP Sockets)** and **React (Vite + Recharts)**. The system generates synthetic RTP-like voice traffic, introduces configurable physical network impairments (delay, jitter, packet loss), measures network metrics, calculates Estimated Mean Opinion Score (MOS) using the ITU-T G.107 E-model, and displays everything on a live dashboard.

---

## 1. System Architecture

```text
               ┌────────────────────────────────────────┐
               │          React Dashboard UI            │
               │                                        │
               │  Delay / Jitter / Packet Loss Sliders  │
               │  Latency & Jitter Line Charts          │
               │  Packet Loss Area Chart & Statistics   │
               │  Visual MOS Gauge & Quality Rating     │
               └───────────────────┬────────────────────┘
                                   │
                           WebSocket / HTTP REST
                                   │
                                   ▼
               ┌────────────────────────────────────────┐
               │            FastAPI Backend             │
               │                                        │
               │  - Rest Endpoints & WebSocket Manager  │
               │  - Simulation Controller               │
               └───────────────────┬────────────────────┘
                                   │
                                   ▼
               ┌────────────────────────────────────────┐
               │          VoIP Simulation Engine         │
               │                                        │
               │  Packet Generator ──> Impairment Engine │
               └───────────────────┬────────────────────┘
                                   │
                              UDP Sockets
                                   │
                                   ▼
               ┌────────────────────────────────────────┐
               │             Metric Engine              │
               │                                        │
               │  - Latency Calculation                 │
               │  - RFC 3550 Interarrival Jitter         │
               │  - Sequence-gap Packet Loss            │
               │  - ITU-T G.107 E-Model MOS Estimator    │
               └────────────────────────────────────────┘
```

---

## 2. Key Features

- **Synthetic RTP-like Stream Generation**: Generates 20ms voice frames (50 packets/sec) with sequence numbers, timestamps, and 160-byte payload.
- **Dynamic Impairment Engine**:
  - Delay: 0 – 500 ms
  - Jitter: 0 – 100 ms (Gaussian distribution offset)
  - Packet Loss: 0 – 30% (Probabilistic drop)
- **Standardized Networking Algorithms**:
  - **RFC 3550 Interarrival Jitter**: Exponentially smoothed interarrival timing deviation.
  - **ITU-T G.107 E-Model MOS Estimation**: Computes R-factor ($R = R_0 - I_d - I_{e,eff}$) and maps it to a 1.0 – 5.0 MOS score and qualitative rating (EXCELLENT, GOOD, FAIR, POOR, BAD).
- **Live React Telemetry Dashboard**: Real-time Recharts graphs updating over WebSocket every 250ms.
- **Review 2 Predefined Demo Presets**: Quick scenario buttons for live viva demonstration.

---

## 3. Technology Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, Python UDP Sockets, NumPy, Pytest.
- **Frontend**: React 18, Vite, Recharts, Lucide-React.

---

## 4. Project Directory Structure

```text
voip-quality-analyzer/
├── backend/
│   ├── main.py                    # FastAPI server & WebSocket endpoints
│   ├── config.py                  # UDP IP/port & default parameters
│   ├── websocket_manager.py       # WebSocket telemetry manager
│   ├── simulation/
│   │   ├── packet_generator.py    # RTP-like synthetic packet generator
│   │   ├── impairment.py          # Delay, jitter, & loss impairment engine
│   │   ├── udp_sender.py          # Localhost UDP sender socket
│   │   ├── udp_receiver.py        # Localhost UDP receiver socket
│   │   └── simulator.py           # Simulation controller & thread manager
│   └── metrics/
│       ├── latency.py             # Latency calculation engine
│       ├── jitter.py              # RFC 3550 interarrival jitter calculation
│       ├── packet_loss.py         # Sequence gap packet loss detector
│       └── mos.py                 # ITU-T G.107 E-model MOS estimator
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx      # Main layout & WebSocket client
│   │   │   ├── ControlPanel.jsx   # Sliders & demo scenario buttons
│   │   │   ├── MetricCard.jsx     # KPI summary cards
│   │   │   ├── LatencyChart.jsx   # Recharts latency line graph
│   │   │   ├── JitterChart.jsx    # Recharts jitter line graph
│   │   │   ├── PacketLossCard.jsx # Packet statistics & loss chart
│   │   │   └── MosGauge.jsx       # SVG arc meter & MOS rating gauge
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── main.jsx
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── tests/
│   ├── test_latency.py
│   ├── test_jitter.py
│   ├── test_packet_loss.py
│   ├── test_mos.py
│   ├── test_simulation.py
│   └── collect_demo_results.py    # Empirical scenario results collector
├── docs/
│   ├── architecture.md            # Architecture specs & DFDs
│   ├── methodology.md             # Mathematical formulas & algorithms
│   ├── test_cases.md              # Test case matrix & empirical results
│   └── implementation_progress.md # Module development status table
├── README.md
└── requirements.txt
```

---

## 5. How to Run the Project

### Prerequisite Setup
Ensure Python 3.10+ and Node.js v18+ are available.

### Step 1: Start the Backend Server
```bash
# From the project root (voip-quality-analyzer):
python -m uvicorn backend.main:app --port 8000 --reload
```
The FastAPI backend will start at `http://localhost:8000`.

### Step 2: Start the React Frontend Dashboard
```bash
# Navigate to frontend directory:
cd frontend

# Install dependencies (if not already installed):
npm install

# Start Vite development server:
npm run dev
```
Open `http://localhost:3000` in your web browser.

---

## 6. How to Run Automated Tests & Empirical Collector

To execute the unit and integration test suite:
```bash
# Run pytest from project root
python -m pytest -v tests
```

To collect empirical results from live simulation:
```bash
python tests/collect_demo_results.py
```

---

## 7. Review 2 Demo Scenarios & Empirical Results

| Scenario | Configured Delay | Configured Jitter | Configured Loss | Measured Latency | Measured RFC 3550 Jitter | Measured Loss % | R-Factor | Estimated MOS | Call Quality Rating |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Good Network** | 20.0 ms | 2.0 ms | 0.0% | 20.29 ms | 0.84 ms | 0.00% | 92.43 | **4.39** | **EXCELLENT** |
| **2. High Latency** | 200.0 ms | 5.0 ms | 0.0% | 201.51 ms | 0.47 ms | 0.00% | 84.20 | **4.17** | **GOOD** |
| **3. High Jitter** | 50.0 ms | 60.0 ms | 0.0% | 55.33 ms | 22.51 ms | 0.00% | 90.55 | **4.35** | **EXCELLENT** |
| **4. Packet Loss** | 50.0 ms | 10.0 ms | 10.0% | 50.96 ms | 3.41 ms | 15.79% | 16.91 | **1.17** | **BAD** |
| **5. Poor Network** | 250.0 ms | 80.0 ms | 15.0% | 246.66 ms | 9.20 ms | 16.67% | 0.29 | **1.00** | **BAD** |

---

## 8. Review 2 Viva Demonstration Guide

When presenting to the faculty reviewer:
1. **Show Architecture Diagram & DFD**: Open `docs/architecture.md`.
2. **Explain Algorithms**: Open `backend/metrics/jitter.py` (RFC 3550 formula) and `backend/metrics/mos.py` (ITU-T G.107 formula).
3. **Live Demonstration**:
   - Move the **Delay slider** to 200ms -> observe Latency graph increase and MOS drop to ~4.1.
   - Move the **Jitter slider** to 60ms -> observe Jitter graph fluctuate.
   - Move the **Packet Loss slider** to 10-15% -> observe Packets Lost counter increase, Loss area chart rise, and MOS gauge drop into red **BAD** territory.
   - Click the 5 predefined **Review 2 Demo Scenario buttons** on the control panel to demonstrate instant telemetry updates!
