# Real-Time VoIP Call Quality Analyzer
## Technical Documentation — Review 2: Design & Implementation

---

## 1. SYSTEM ARCHITECTURE

### 1.1 High-Level Architecture Overview
The system is implemented as a modular, full-stack real-time network simulation, socket communication, metric analysis, and telemetry streaming platform. It operates entirely on local hardware (`127.0.0.1`) without external cloud dependencies or third-party packet generation drivers.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             React Dashboard UI                              │
│                                                                             │
│  [Control Panel]          [KPI Cards]              [Live Recharts]          │
│  - Delay (0-500ms)        - Latency (ms)           - Latency Graph          │
│  - Jitter (0-100ms)       - Jitter (ms)            - Jitter Graph           │
│  - Loss (0-30%)           - Loss (%)               - Packet Loss Area       │
│  - Demo Presets           - Estimated MOS          - MOS Gauge              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                         WebSocket / HTTP REST API
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FastAPI Backend Server                           │
│                                                                             │
│  - REST Endpoints (/config, /simulation/start, /simulation/stop, /metrics)  │
│  - WebSocket Telemetry Manager (/ws @ 250ms broadcast rate)                 │
│  - VoIP Simulator Controller                                                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        VoIP Simulation Engine Layer                         │
│                                                                             │
│  ┌────────────────────────┐             ┌────────────────────────────────┐  │
│  │ Packet Generator       │ ──────────> │ Network Impairment Engine      │  │
│  │ - 50 Hz / 20ms Frame   │             │ - Delay Injection              │  │
│  │ - Sequence Number      │             │ - Gaussian Jitter Offset       │  │
│  │ - RTP Timestamp        │             │ - Probabilistic Drop           │  │
│  └────────────────────────┘             └───────────────┬────────────────┘  │
└─────────────────────────────────────────────────────────┼───────────────────┘
                                                          │
                                                    UDP Socket
                                                          │
                                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Metrics Engine Layer & Receiver                      │
│                                                                             │
│  - UDP Socket Receiver (High-precision arrival timestamping)                │
│  - Latency Calculator (Receive Time - Send Time)                            │
│  - RFC 3550 Interarrival Jitter Engine (Exponential smoothing)             │
│  - RFC 3550 Reordering-Compensated Packet Loss Detector                    │
│  - ITU-T G.107 Estimated E-Model MOS Engine                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

1. **Packet Generator (`backend/simulation/packet_generator.py`)**: Generates synthetic RTP-like voice packet headers at standard G.711 frame pacing (20ms / 50 Hz).
2. **Impairment Injector (`backend/simulation/impairment.py`)**: Applies user-configured network impairments (base delay, random Gaussian jitter variation, and probabilistic packet dropping).
3. **UDP Communication Layer (`backend/simulation/udp_sender.py`, `udp_receiver.py`)**: Handles local socket binding and non-blocking packet transmission across `127.0.0.1:5005`.
4. **Receiver (`backend/simulation/udp_receiver.py`)**: Listens on the UDP socket, reads incoming datagram payloads, and attaches a high-resolution arrival timestamp.
5. **Metric Engine (`backend/metrics/`)**: Calculates one-way latency, RFC 3550 interarrival jitter, sequence-gap packet loss percentage, and ITU-T G.107 Estimated MOS.
6. **FastAPI & WebSocket Server (`backend/main.py`, `websocket_manager.py`)**: Exposes REST control endpoints and broadcasts real-time metrics over WebSocket to connected dashboard clients every 250ms.
7. **React Dashboard (`frontend/src/components/Dashboard.jsx`)**: Renders interactive impairment controls, visual MOS gauge, KPI cards, and live time-series graphs.

### 1.3 End-to-End Data Flow

```text
[User Action on UI Sliders/Presets]
            │
            ▼ (HTTP POST /config)
[FastAPI Backend Server]
            │
            ▼ (update_config)
[Network Impairment Engine]
            │
[Packet Generator (50 Hz)] ──(Raw Packet)──> [Impairment Engine]
                                                    │
                                           (Delayed/Dropped Packet)
                                                    │
                                                    ▼
                                           [UDP Sender Socket]
                                                    │
                                              (127.0.0.1:5005)
                                                    │
                                                    ▼
                                          [UDP Receiver Socket]
                                                    │
                                           (Attach Receive Time)
                                                    │
                                                    ▼
                                           [QoS Metric Engines]
                                                    │
                                      (Latency, Jitter, Loss, MOS)
                                                    │
                                                    ▼
                                        [WebSocket Manager (/ws)]
                                                    │
                                             (250ms Telemetry)
                                                    │
                                                    ▼
                                    [React Dashboard Charts & Gauge]
```

---

## 2. DETAILED DESIGN

### 2.1 Packet Generator (`backend/simulation/packet_generator.py`)
- **Input**: Internal timer trigger (every 20ms).
- **Processing**: Increments a 16-bit sequence number (1–65535 with wraparound) and an 8kHz RTP timestamp (increments by 160 units per frame). Captures high-precision generation timestamp `time.time()`.
- **Output**: Dictionary payload `{"sequence_number": int, "timestamp": int, "send_time": float, "payload_size": 160}`.
- **Purpose**: Simulates standard G.711 PCM voice frame generation.

### 2.2 UDP Sender (`backend/simulation/udp_sender.py`)
- **Input**: Packet payload dictionary from the Impairment Engine.
- **Processing**: Serializes packet dictionary to UTF-8 JSON bytes and transmits over `socket.AF_INET, socket.SOCK_DGRAM`.
- **Output**: UDP datagram sent to `127.0.0.1:5005`.
- **Purpose**: Encapsulates physical UDP socket layer output.

### 2.3 UDP Receiver (`backend/simulation/udp_receiver.py`)
- **Input**: Incoming UDP datagram on `127.0.0.1:5005`.
- **Processing**: Reads socket buffer with non-blocking timeout ($0.1\text{s}$), deserializes JSON, and attaches `receive_time = time.time()`.
- **Output**: Decoded packet dictionary with `receive_time`.
- **Purpose**: Ingests packets from socket layer and records arrival time.

### 2.4 Impairment Engine (`backend/simulation/impairment.py`)
- **Input**: Raw packet dictionary, active config parameters (`delay_ms`, `jitter_ms`, `packet_loss_pct`).
- **Processing**:
  1. Probabilistic Drop: Evaluates `random.uniform(0.0, 100.0) < packet_loss_pct`. If true, returns `None` (packet dropped).
  2. Delay & Jitter: Computes $D_{total} = \max(0, D_{base} + \text{Gaussian}(0, J_{jitter}/2))$.
- **Output**: Modified packet dictionary with `simulated_delay_sec` or `None` if dropped.
- **Purpose**: Introduces physical network anomalies into the packet stream.

### 2.5 Packet Sequence Tracking & Loss Measurement (`backend/metrics/packet_loss.py`)
- **Input**: Received packet sequence numbers and `record_sent()` notifications.
- **Processing**: Maintains `max_seq_received` and tracks forward sequence gaps ($Seq_i - Seq_{max} - 1$). Out-of-order packets ($Seq_i \le Seq_{max}$) decrement the gap counter to compensate for jitter-induced reordering. Combines gap detection with sent-vs-received counts to capture trailing drops.
- **Output**: `packets_sent`, `packets_received`, `packets_lost`, `loss_percentage`.
- **Purpose**: Calculates precise packet loss percentage under reordering.

### 2.6 Latency Measurement (`backend/metrics/latency.py`)
- **Input**: Packet `send_time` and `receive_time`.
- **Processing**: Computes $L = (R_i - S_i) \times 1000\text{ ms}$. Maintains rolling history buffer of 50 packets to compute current, average, min, and max latency.
- **Output**: Latency metrics dictionary (`current_ms`, `avg_ms`, `min_ms`, `max_ms`).
- **Purpose**: Measures one-way propagation delay.

### 2.7 RFC 3550 Jitter Measurement (`backend/metrics/jitter.py`)
- **Input**: Packet `send_time` and `receive_time`.
- **Processing**: Computes interarrival transit difference $D(i-1, i) = (R_i - S_i) - (R_{i-1} - S_{i-1})$ and updates exponentially smoothed jitter $J = J + (|D| - J)/16$.
- **Output**: Estimated interarrival jitter in milliseconds.
- **Purpose**: Standard RFC 3550 statistical delay variation measurement.

### 2.8 Estimated MOS Calculation (`backend/metrics/mos.py`)
- **Input**: Measured `latency_avg`, `jitter_ms`, `packet_loss_pct`.
- **Processing**: Computes $R_0 = 93.2$, effective delay $d_{eff} = d_{lat} + 2 J + 10\text{ms}$, delay impairment $I_d$, equipment loss impairment $I_{e,eff}$, Transmission Rating Factor $R$, and polynomial conversion to MOS ($1.0–4.5$).
- **Output**: Estimated MOS score, R-Factor, and Quality Rating category.
- **Purpose**: ITU-T G.107 Estimated E-Model voice quality assessment.

### 2.9 FastAPI Backend (`backend/main.py`)
- **Input**: REST HTTP requests from UI client or external tools.
- **Processing**: Handles routing (`/config`, `/simulation/start`, `/simulation/stop`, `/simulation/reset`, `/metrics`), coordinates simulator lifecycle, enforces CORS headers.
- **Output**: JSON REST responses.
- **Purpose**: Backend server controller API.

### 2.10 WebSocket Communication (`backend/websocket_manager.py`)
- **Input**: Active WebSocket connection requests at `/ws`.
- **Processing**: Manages client connection registry and broadcasts live metrics JSON snapshots every 250ms.
- **Output**: WebSocket JSON telemetry stream.
- **Purpose**: Low-latency live metric streaming channel.

### 2.11 React Dashboard (`frontend/src/components/Dashboard.jsx`)
- **Input**: WebSocket telemetry messages, user slider/button interactions.
- **Processing**: Maintains rolling chart history buffer (45 points), updates UI components, dispatches HTTP POST requests to REST API.
- **Output**: Rendered UI components, live Recharts graphs, MOS gauge.
- **Purpose**: User interface and visualization dashboard.

---

## 3. METHODOLOGY / ALGORITHMS

### 3.1 RTP-like Packet Generation
Synthetic voice frames are generated at 20ms intervals ($50\text{ Hz}$ pacing). Each frame contains:
- `sequence_number`: 16-bit unsigned incrementing counter ($1 \to 65535$).
- `timestamp`: 8kHz RTP media sampling timestamp (increments by 160 per frame).
- `send_time`: Monotonic Unix timestamp (`time.time()`).
- `payload_size`: Fixed 160 bytes (G.711 PCM simulation).

### 3.2 Network Impairment Injection
Impairment parameters are dynamically updated via the dashboard:
- **Delay ($0\text{--}500\text{ ms}$)**: Base propagation delay applied to packet delivery.
- **Jitter ($0\text{--}100\text{ ms}$)**: Normal Gaussian distribution offset $J_{offset} = \text{Gaussian}(0, J_{jitter}/2)$. Total delay $D = \max(0, D_{base} + J_{offset})$. Delayed packets are dispatched asynchronously via background threads to preserve 50Hz frame pacing.
- **Packet Loss ($0\text{--}30\%$)**: Probabilistic packet dropping evaluated via uniform random roll: if $\text{Roll}(0, 100) < P_{loss}$, the packet is dropped (`return None`).

### 3.3 UDP Communication
- Sender creates a `SOCK_DGRAM` socket.
- Packets are JSON-serialized into UTF-8 byte streams and sent to `127.0.0.1:5005`.
- Receiver binds to `127.0.0.1:5005` with a non-blocking timeout ($0.1\text{s}$) and attaches arrival timestamp $R_i$.

### 3.4 Latency Calculation
One-way latency $L_i$ for packet $i$ is calculated as:
$$L_i = (R_i - S_i) \times 1000 \quad [\text{ms}]$$
Rolling average latency $\bar{L}$ is computed over the last 50 received packets:
$$\bar{L} = \frac{1}{N} \sum_{k=1}^{N} L_k$$

### 3.5 Packet Loss Detection & Reordering Handling
Packet loss is detected using sequence number tracking. To handle UDP out-of-order arrivals caused by high jitter:
1. `max_seq_received` tracks the highest sequence number seen.
2. For an arriving packet $Seq_i$:
   - If $Seq_i > max\_seq$:
     $$\text{Gap} = Seq_i - max\_seq - 1$$
     If $\text{Gap} > 0$, add $\text{Gap}$ to `sequence_gap_lost`. Update $max\_seq = Seq_i$.
   - If $Seq_i \le max\_seq$ (reordered / late packet):
     If `sequence_gap_lost > 0`, decrement `sequence_gap_lost -= 1` because the late packet was previously assumed missing.
3. Total lost packets $P_{lost} = \max(\text{sequence\_gap\_lost}, \text{packets\_sent} - \text{packets\_received})$.
4. Loss percentage:
   $$P_{loss\_pct} = \frac{P_{lost}}{\max(P_{sent}, P_{received} + P_{lost})} \times 100\%$$

### 3.6 RFC 3550 Interarrival Jitter Formula
Implements standard **RFC 3550 Section 6.4.1**:

$$D(i-1, i) = (R_i - S_i) - (R_{i-1} - S_{i-1})$$

$$J(i) = J(i-1) + \frac{|D(i-1, i)| - J(i-1)}{16}$$

- $S_i, S_{i-1}$: Send timestamps of packets $i$ and $i-1$.
- $R_i, R_{i-1}$: Arrival timestamps of packets $i$ and $i-1$.
- $D(i-1, i)$: Difference in packet transit times.
- $J(i)$: Exponentially smoothed interarrival jitter estimate (converted to ms).

### 3.7 Estimated MOS (ITU-T G.107 E-Model Approach)
> [!NOTE]
> This system implements an **Estimated / Simplified ITU-T G.107 E-Model**. It models key network impairment factors ($I_d$ and $I_{e,eff}$) for real-time telemetry. Unmodeled factors such as sidetone masking ($I_{st}$), listener echo ($I_{le}$), or advantage factor ($A$) are omitted.

#### Mathematical Derivation:
1. **Base Signal Rating $R_0$**: $93.2$
2. **Effective Delay $d_{eff}$**:
   $$d_{eff} = \bar{L}_{latency} + 2 \cdot J_{jitter} + 10 \quad [\text{ms}]$$
3. **Delay Impairment Factor $I_d$**:
   $$I_d = \begin{cases} 0.024 \cdot d_{eff}, & d_{eff} < 177\text{ ms} \\ 0.024 \cdot d_{eff} + 0.11 \cdot (d_{eff} - 177), & d_{eff} \ge 177\text{ ms} \end{cases}$$
4. **Equipment Impairment Factor $I_{e,eff}$** (G.711 PCM codec, robustness factor $B_{pl} = 4.3$):
   $$I_{e,eff} = (95 - I_e) \cdot \frac{P_{loss\_pct}}{P_{loss\_pct} + B_{pl}}$$
5. **Transmission Rating Factor $R$**:
   $$R = \max(0, \min(100, R_0 - I_d - I_{e,eff}))$$
6. **Estimated MOS Score Conversion**:
   $$MOS = \begin{cases} 
   1.0, & R \le 0 \\
   1.0 + 0.035 R + R(R - 60)(100 - R) \cdot 7 \cdot 10^{-6}, & 0 < R < 100 \\
   4.5, & R \ge 100 
   \end{cases}$$

---

## 4. DATABASE / UML / DFD

### 4.1 Database Statement
A traditional relational or NoSQL database is **NOT APPLICABLE** to this project. The system is designed for real-time network stream simulation, socket processing, and live telemetry monitoring. Metrics are calculated dynamically in-memory and streamed via WebSockets without persistent storage requirements.

### 4.2 UML Diagrams

#### Component Diagram
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          UML Component Diagram                              │
│                                                                             │
│  ┌───────────────────────────┐             ┌─────────────────────────────┐  │
│  │   React Dashboard (UI)    │ <─────────> │   FastAPI Backend Server    │  │
│  │   - Dashboard.jsx         │  WebSocket  │   - main.py                     │  │
│  │   - ControlPanel.jsx      │  / REST     │   - websocket_manager.py        │  │
│  └───────────────────────────┘             └──────────────┬──────────────┘  │
│                                                           │                 │
│                                                           ▼                 │
│  ┌───────────────────────────┐             ┌─────────────────────────────┐  │
│  │   QoS Metrics Engine      │ <────────── │   VoIP Simulation Controller│  │
│  │   - latency.py            │  Processed  │   - simulator.py                │  │
│  │   - jitter.py (RFC 3550)  │  Metrics    │   - packet_generator.py         │  │
│  │   - packet_loss.py        │             │   - impairment.py               │  │
│  │   - mos.py (G.107 Est)    │             └──────────────┬──────────────┘  │
│  └──────────────▲────────────┘                            │                 │
│                 │                                         ▼                 │
│                 │                          ┌─────────────────────────────┐  │
│                 └───────────────────────── │   UDP Socket Layer          │  │
│                      Packet Telemetry      │   - udp_sender.py               │  │
│                                            │   - udp_receiver.py             │  │
│                                            └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Sequence Diagram
```text
User            React UI         FastAPI API       Simulator      UDP Socket       Metric Engine
 │                 │                  │                │              │                  │
 │─(Change Slider)─>│                  │                │              │                  │
 │                 │──(POST /config)─>│                │              │                  │
 │                 │                  │─(update_config)>│              │                  │
 │                 │                  │                │              │                  │
 │─(Click Start)──>│                  │                │              │                  │
 │                 │──(POST /start)──>│                │              │                  │
 │                 │                  │──(start())────>│              │                  │
 │                 │                  │                │──(Send UDP)─>│                  │
 │                 │                  │                │              │──(Receive UDP)──>│
 │                 │                  │                │              │                  │─(add_packet)─>│
 │                 │                  │                │<─────────────(Get Metrics)──────│
 │                 │<──(WS Telemetry)─│                │              │                  │
 │─(View Graphs)───│                  │                │              │                  │
```

#### Activity Diagram
```text
       ( Start Simulation )
                │
                ▼
      [ Initialize UDP Sockets ]
                │
                ▼
     ┌─> [ Generate Synthetic RTP Packet (20ms) ]
     │          │
     │          ▼
     │   [ Process Impairment Engine ]
     │          │
     │          ├─> (Roll < Loss %) ──> [ Drop Packet ]
     │          │
     │          └─> (Apply Delay + Jitter) ──> [ Transmit via UDP Sender ]
     │                                                     │
     │                                                     ▼
     │                                          [ UDP Receiver Socket ]
     │                                                     │
     │                                                     ▼
     │                                          [ Record Receive Time ]
     │                                                     │
     │                                                     ▼
     │                                          [ Update QoS Metrics ]
     │                                          - Latency = Receive - Send
     │                                          - RFC 3550 Jitter
     │                                          - Sequence Loss %
     │                                          - Estimated MOS
     │                                                     │
     │                                                     ▼
     │                                          [ Broadcast via WebSocket ]
     │                                                     │
     └─────────────────────────────────────────────────────┘
```

### 4.3 Data Flow Diagrams (DFD)

#### Level 0 DFD (Context Diagram)
```text
┌──────────┐      Impairment Settings & Controls      ┌─────────────────────────┐
│          │ ───────────────────────────────────────> │                         │
│   User   │                                          │  VoIP Call Quality      │
│          │ <─────────────────────────────────────── │  Analyzer System        │
└──────────┘      Live Metrics, Charts & MOS Gauge    └─────────────────────────┘
```

#### Level 1 DFD
```text
                 ┌────────────────────────────────┐
                 │    1.0 React Dashboard UI      │
                 └───────┬────────────────▲───────┘
                         │                │
       (Config / Control)│                │(WebSocket JSON Telemetry)
                         ▼                │
                 ┌────────────────────────────────┐
                 │ 2.0 FastAPI Server Controller  │
                 └───────┬────────────────────────┘
                         │
                         ▼
                 ┌────────────────────────────────┐
                 │   3.0 VoIP Simulator Engine    │
                 └───────┬────────────────────────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
   ┌──────────────────┐    ┌──────────────────┐
   │ 3.1 Packet Gen   │    │ 3.2 Impairment   │
   └──────────────────┘    └─────────┬────────┘
                                     │
                                (UDP Datagram)
                                     │
                                     ▼
                           ┌──────────────────┐
                           │ 4.0 UDP Receiver │
                           └─────────┬────────┘
                                     │
                             (Packet Payload)
                                     │
                                     ▼
                           ┌──────────────────┐
                           │ 5.0 Metric Engine│
                           │ (Latency, Jitter,│
                           │  Loss, MOS)      │
                           └──────────────────┘
```

---

## 5. MODULE DEVELOPMENT

| Module Name | Purpose | Main Files / Technologies | Status |
| :--- | :--- | :--- | :---: |
| **Packet Generator** | Generates synthetic RTP-like voice frames with 16-bit sequence numbers and 8kHz RTP timestamps | [packet_generator.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/simulation/packet_generator.py) (Python) | **COMPLETED** |
| **Network Impairment Injector** | Applies base delay, Gaussian jitter variation, and probabilistic packet dropping | [impairment.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/simulation/impairment.py) (Python, NumPy/Random) | **COMPLETED** |
| **UDP Sender Layer** | Transmits JSON packet payloads over local UDP sockets | [udp_sender.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/simulation/udp_sender.py) (Python Sockets) | **COMPLETED** |
| **UDP Receiver Layer** | Binds to local UDP port and records high-precision packet arrival timestamps | [udp_receiver.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/simulation/udp_receiver.py) (Python Sockets) | **COMPLETED** |
| **Latency Measurement** | Computes one-way delay and rolling average/min/max statistics | [latency.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/metrics/latency.py) (Python) | **COMPLETED** |
| **RFC 3550 Jitter** | Calculates exponentially smoothed RFC 3550 interarrival jitter | [jitter.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/metrics/jitter.py) (Python) | **COMPLETED** |
| **Packet Loss Measurement** | Tracks sequence number gaps and compensates for out-of-order UDP arrival | [packet_loss.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/metrics/packet_loss.py) (Python) | **COMPLETED** |
| **Estimated MOS Engine** | Computes ITU-T G.107 Estimated E-Model R-Factor and MOS score | [mos.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/metrics/mos.py) (Python) | **COMPLETED** |
| **FastAPI Backend API** | REST API endpoints for simulation controls, metrics, and impairment configuration | [main.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/main.py) (FastAPI, Uvicorn) | **COMPLETED** |
| **WebSocket Streaming** | Broadcasts live metrics telemetry to dashboard clients every 250ms | [websocket_manager.py](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/backend/websocket_manager.py) (WebSockets) | **COMPLETED** |
| **React Dashboard UI** | Modern dark-themed dashboard with controls, metric cards, MOS arc gauge, and Recharts | [Dashboard.jsx](file:///C:/Users/jeeva/.gemini/antigravity/scratch/voip-quality-analyzer/frontend/src/components/Dashboard.jsx) (React, Recharts, Vite) | **COMPLETED** |

---

## 6. WORKING PROTOTYPE

### 6.1 Description of the Running Prototype
The prototype runs as a dual-server web architecture:
- **Backend API & Simulator**: Running via FastAPI and Uvicorn at `http://127.0.0.1:8000`.
- **Frontend Dashboard**: Running via Vite and React at **`http://localhost:3000`**.

#### Key UI Components:
1. **Header & Status Badge**: Displays project title and live status badge (`● Simulation Running` or `● Simulation Stopped`).
2. **Control Panel**:
   - **Delay Slider**: $0\text{--}500\text{ ms}$
   - **Jitter Slider**: $0\text{--}100\text{ ms}$
   - **Packet Loss Slider**: $0\text{--}30\%$
   - **Action Buttons**: `START SIMULATION`, `STOP SIMULATION`, `RESET`
   - **Review 2 Preset Buttons**: Instant scenario buttons for Scenario 1 through Scenario 5.
3. **Visual MOS Arc Gauge**: SVG semi-circular meter rendering real-time MOS score ($1.00\text{--}4.50$), quality rating badge (**EXCELLENT**, **GOOD**, **FAIR**, **POOR**, **BAD**), and ITU-T G.107 R-Factor ($0\text{--}100$).
4. **KPI Summary Cards**: Four prominent cards displaying Latency (ms), RFC 3550 Jitter (ms), Packet Loss (%), and Estimated MOS.
5. **Live Time-Series Charts**: Recharts streaming graphs for Latency, RFC 3550 Jitter, and Packet Loss updating dynamically over WebSocket.

### 6.2 Visual Evidence & Screenshot Locations
The live application interface can be observed directly by launching `http://localhost:3000` while the backend server is active.

```text
[Screenshot 1 Placeholder: React Telemetry Dashboard - Good Network Scenario]
Path: docs/screenshots/dashboard_good_network.png
Caption: Figure 6.1 - React Dashboard displaying Good Network scenario (MOS: 4.39, Latency: 20.56ms, Jitter: 1.01ms).

[Screenshot 2 Placeholder: React Telemetry Dashboard - High Latency Scenario]
Path: docs/screenshots/dashboard_high_latency.png
Caption: Figure 6.2 - React Dashboard displaying High Latency scenario (Delay slider at 200ms, Latency: 200.60ms, MOS: 4.16).

[Screenshot 3 Placeholder: React Telemetry Dashboard - Packet Loss Scenario]
Path: docs/screenshots/dashboard_packet_loss.png
Caption: Figure 6.3 - React Dashboard displaying Packet Loss scenario (Loss slider at 10%, MOS: 1.85 BAD rating).

[Screenshot 4 Placeholder: Terminal Execution - 9/9 Automated Pytest Suite]
Path: docs/screenshots/terminal_pytest_passed.png
Caption: Figure 6.4 - Terminal window showing 9/9 automated pytest test cases passing cleanly in 0.56s.
```

---

## 7. IMPLEMENTATION PROGRESS

### 7.1 Review 1 Baseline
- Problem definition and scope identification.
- System requirement specifications.
- High-level block architecture proposal.
- Tech stack selection (Python FastAPI, React, UDP Sockets).

### 7.2 Review 2 Implementation Completed
- [x] Synthetic RTP-like packet generator implemented (50 Hz frame rate).
- [x] Localhost UDP sender and receiver socket layers implemented.
- [x] Network impairment engine implemented (Delay, Jitter, Packet Loss).
- [x] One-way latency calculator implemented.
- [x] Standard RFC 3550 interarrival jitter algorithm implemented.
- [x] Sequence-gap packet loss detector with out-of-order reordering compensation implemented.
- [x] ITU-T G.107 Estimated E-Model MOS calculator implemented.
- [x] FastAPI REST API controller implemented.
- [x] Low-latency WebSocket telemetry streaming manager implemented (250ms rate).
- [x] React dashboard with Recharts live streaming graphs and SVG MOS gauge implemented.
- [x] 9/9 automated pytest unit/integration test suite created and passed.
- [x] Five Review 2 demonstration scenarios validated empirically.

---

## 8. TEST CASES

### 8.1 Automated Unit & Integration Tests (9/9 Passed)

| Test ID | Test Name | Description / Condition | Expected Result | Actual Result | Status |
| :---: | :--- | :--- | :--- | :--- | :---: |
| **UT01** | `test_latency_calculation` | Feed send time $100.0\text{s}$ and receive time $100.05\text{s}$ ($50\text{ms}$) | Calculated latency $= 50.0\text{ ms}$ | $50.0\text{ ms}$ calculated | **PASSED** |
| **UT02** | `test_latency_reset` | Call `reset()` on LatencyCalculator | Metrics reset to $0.0\text{ ms}$ | Current & Avg $= 0.0\text{ ms}$ | **PASSED** |
| **UT03** | `test_rfc3550_jitter` | Feed two packets with transit times $0.02\text{s}$ and $0.03\text{s}$ ($D=0.01\text{s}$) | Jitter $= \frac{0.01}{16} = 0.625\text{ ms}$ | $0.625\text{ ms}$ calculated | **PASSED** |
| **UT04** | `test_jitter_reset` | Call `reset()` on RFC3550JitterCalculator | Jitter resets to $0.0\text{ ms}$ | Jitter $= 0.0\text{ ms}$ | **PASSED** |
| **UT05** | `test_mos_perfect_conditions` | Inputs: Latency $= 10\text{ms}$, Jitter $= 0\text{ms}$, Loss $= 0\%$ | MOS $\ge 4.3$ (EXCELLENT) | $\text{MOS} = 4.39$ (EXCELLENT) | **PASSED** |
| **UT06** | `test_mos_poor_conditions` | Inputs: Latency $= 250\text{ms}$, Jitter $= 80\text{ms}$, Loss $= 15\%$ | MOS $< 3.1$ (BAD) | $\text{MOS} = 1.00$ (BAD) | **PASSED** |
| **UT07** | `test_mos_classification_scale` | Verify qualitative scale boundaries ($4.4, 4.1, 3.8, 3.3, 2.5$) | Correct scale categories | Matches EXCELLENT to BAD scale | **PASSED** |
| **UT08** | `test_packet_loss_detection` | Feed sequence numbers 101, 102, 103, 105 (104 missing) | Detected 1 lost packet ($20\%$) | $1$ lost packet ($20.0\%$) | **PASSED** |
| **IT01** | `test_simulator_lifecycle` | Execute `start()`, sleep 0.5s, verify packet flow, execute `stop()` | Simulator transitions RUNNING $\to$ STOPPED, packets $>0$ | Clean start, transmission, & stop | **PASSED** |

---

## 9. INITIAL RESULTS

The following empirical results were captured live by executing `tests/collect_demo_results.py` over UDP socket channels:

| Scenario | Configured Delay | Measured Latency | Configured Jitter | Measured RFC 3550 Jitter | Configured Loss | Actual Packet Loss % | Packets Sent | Packets Received | Packets Lost | Estimated MOS | Call Quality Rating |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Good Network** | 20.0 ms | **20.56 ms** | 2.0 ms | **1.01 ms** | 0.0% | **0.00%** | 146 | 146 | 0 | **4.39** | **EXCELLENT** |
| **2. High Latency** | 200.0 ms | **200.60 ms** | 5.0 ms | **2.23 ms** | 0.0% | **0.00%** | 147 | 147 | 0 | **4.16** | **GOOD** |
| **3. High Jitter** | 50.0 ms | **48.08 ms** | 60.0 ms | **32.57 ms** | 0.0% | **0.00%** | 146 | 146 | 0 | **4.34** | **EXCELLENT** |
| **4. Packet Loss** | 50.0 ms | **50.65 ms** | 10.0 ms | **5.61 ms** | 10.0% | **6.16%** | 146 | 137 | 9 | **1.85** | **BAD** |
| **5. Poor Network** | 250.0 ms | **255.10 ms** | 80.0 ms | **49.51 ms** | 15.0% | **15.07%** | 146 | 124 | 22 | **1.00** | **BAD** |

### 9.1 Cause-and-Effect Relationship Analysis

1. **Network Impairment $\to$ Packet Behavior**:
   - Setting **Delay** to $200\text{ms}$ increases packet arrival transit time from $20.56\text{ms}$ to $200.60\text{ms}$.
   - Setting **Jitter** to $60\text{ms}$ creates interarrival timing variation, measured at $32.57\text{ms}$ by the RFC 3550 exponentially smoothed calculator.
   - Setting **Packet Loss** to $10\text{--}15\%$ drops datagrams prior to UDP socket transmission, resulting in sequence gaps ($9$ lost out of $146$ sent in Scenario 4; $22$ lost out of $146$ sent in Scenario 5).

2. **Packet Behavior $\to$ QoS Metrics $\to$ MOS $\to$ Quality Rating**:
   - **Good Network**: Low delay ($20\text{ms}$), negligible jitter ($1.01\text{ms}$), and $0\%$ loss yields an R-Factor of $92.42$ and Estimated MOS of **4.39 (EXCELLENT)**.
   - **High Latency**: Increasing delay to $200\text{ms}$ introduces delay impairment $I_d$, lowering R-Factor to $83.85$ and MOS to **4.16 (GOOD)**.
   - **Packet Loss**: Packet loss is the most severe impairment in VoIP telephony. A $6.16\text{--}15.07\%$ loss rate causes equipment loss impairment $I_{e,eff}$ to surge, collapsing R-Factor below $36.0$ and Estimated MOS to **1.85 / 1.00 (BAD)**.

---

## REVIEW 2 READINESS SUMMARY

The prototype implementation is **FULLY COMPLETED AND VERIFIED FOR REVIEW 2 DEMONSTRATION**.

- **UDP Network Simulation**: Software-based packet generator and impairment injector running live over `127.0.0.1:5005`.
- **Standardized Telemetry Algorithms**: Verified RFC 3550 Interarrival Jitter and Estimated ITU-T G.107 E-Model MOS score calculations.
- **Full-Stack Architecture**: FastAPI REST API, WebSocket 250ms telemetry streaming, and React Recharts dashboard.
- **Automated Verification**: **9 out of 9 unit and integration tests passed**.
- **Empirical Validation**: All 5 demonstration scenarios verified with actual running socket data.
