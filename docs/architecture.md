# VoIP Call Quality Analyzer — Architecture & System Design

## 1. High-Level Architecture Overview

The system is designed as a modular, real-time packet generation, network impairment injection, socket communication, metric calculation, and visualization stack.

```text
┌───────────────────────────────────────────────────────────────────┐
│                          React Dashboard                          │
│                                                                   │
│  [Control Panel]        [Metric Cards]         [Live Recharts]    │
│  - Delay Slider         - Latency (ms)         - Latency Graph    │
│  - Jitter Slider        - Jitter (ms)          - Jitter Graph     │
│  - Loss % Slider        - Packet Loss (%)      - Loss Area Chart  │
│  - Demo Buttons         - MOS & Rating Gauge                      │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
                       WebSocket / HTTP REST API
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│                          FastAPI Backend                          │
│                                                                   │
│  - REST Endpoints (/config, /simulation/start, /simulation/stop)  │
│  - WebSocket Telemetry Streamer (/ws)                             │
│  - VoIP Simulator Controller                                      │
└─────────────────────────────────┬─────────────────────────────────┘
                                  │
                                  ▼
┌───────────────────────────────────────────────────────────────────┐
│                      VoIP Simulation Engine                       │
│                                                                   │
│  ┌───────────────────────┐           ┌─────────────────────────┐  │
│  │ Packet Generator      │ ────────> │ Impairment Engine       │  │
│  │ - 20ms Frame Pacing   │           │ - Base Delay (0-500ms)  │  │
│  │ - Sequence Counter    │           │ - Gaussian Jitter       │  │
│  │ - RTP Timestamp       │           │ - Probabilistic Drop    │  │
│  └───────────────────────┘           └────────────┬────────────┘  │
└───────────────────────────────────────────────────┼───────────────┘
                                                    │
                                               UDP Socket
                                                    │
                                                    ▼
┌───────────────────────────────────────────────────────────────────┐
│                       Metrics Engine Layer                        │
│                                                                   │
│  - UDP Receiver (High-precision receive timestamp)                │
│  - Latency Calculator (Receive Time - Send Time)                  │
│  - RFC 3550 Interarrival Jitter Engine (Exponential Smoothing)   │
│  - Sequence Gap Packet Loss Detector                              │
│  - ITU-T G.107 E-Model MOS Estimator (R-Factor Conversion)        │
└───────────────────────────────────────────────────────────────────┘
```

## 2. Component Specifications

### 2.1 Packet Generator (`backend/simulation/packet_generator.py`)
Generates synthetic RTP-like VoIP voice packets every 20ms (representing standard 50 Hz G.711 PCM codec audio frames).
- **Sequence Number**: 16-bit unsigned integer counter (1 to 65535 with wraparound).
- **RTP Timestamp**: Increments by 160 per frame (8000 Hz audio sampling rate).
- **Send Time**: High-precision Unix epoch timestamp (`time.time()`).
- **Payload Size**: 160 bytes.

### 2.2 Impairment Engine (`backend/simulation/impairment.py`)
Infects packet streams with user-configured physical network anomalies:
1. **Packet Loss**: Probabilistic drop evaluated via `random.uniform(0.0, 100.0) < loss_pct`.
2. **Propagation & Queueing Delay**: Applies base delay $D_{base} = \text{delay\_ms} / 1000$.
3. **Jitter Variation**: Normal Gaussian distribution offset bounded by $\pm \text{jitter\_ms}$.

### 2.3 UDP Socket Layer (`backend/simulation/udp_sender.py`, `udp_receiver.py`)
- Standard Python socket library over `127.0.0.1` (localhost).
- Port: Configurable (default `5005`).

### 2.4 Metrics Calculation Engine (`backend/metrics/`)
- **Latency**: $L = R_i - S_i$ (ms). Tracks current, rolling average, min, max.
- **RFC 3550 Jitter**: Smoothed interarrival difference $J(i) = J(i-1) + \frac{|D(i-1, i)| - J(i-1)}{16}$.
- **Packet Loss**: Tracks sequence number gaps: $P_{loss} = \frac{\text{Lost}}{\text{Expected}} \times 100$.
- **ITU-T G.107 MOS**: R-factor computation ($R = R_0 - I_d - I_{e,eff}$) mapped to 1.0–5.0 MOS scale.

## 3. Data Flow Diagram (DFD)

### Level 0 DFD
```text
[User] ──(Impairment Sliders)──> [VoIP Analyzer System] ──(Live Graphs & MOS)──> [User]
```

### Level 1 DFD
```text
              [1.0 Dashboard UI]
                │          ▲
      (Config)  │          │ (WebSocket Stream)
                ▼          │
       [2.0 API Controller / Simulator]
                │
                ├───> [3.0 Packet Generator] ───> [4.0 Impairment Engine]
                │                                         │
                │                                     (UDP Socket)
                │                                         │
                │                                         ▼
                └───────────────────────────────> [5.0 UDP Receiver & Metric Engine]
                                                          │
                                                (Calculated Telemetry)
                                                          │
                                                          ▼
                                              [6.0 MOS Estimator & WS Manager]
```
