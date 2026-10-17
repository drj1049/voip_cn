# Computer Networks — Review 2 Presentation Slides Content

## Slide 1: Title & Team Information
- **Title**: Real-Time VoIP Call Quality Analyzer
- **Domain**: Computer Networks / Telecommunications & QoS Engineering
- **Phase**: Review 2 — Design & Implementation
- **Tech Stack**: Python (FastAPI, UDP Sockets), React (Vite, Recharts), WebSocket

---

## Slide 2: Problem Statement & Project Objectives
- **Problem**: Voice over IP (VoIP) traffic is highly sensitive to underlying physical network impairments (Delay, Jitter, Packet Loss), directly degrading human voice perception (MOS).
- **Objectives**:
  1. Build a controlled VoIP network simulation engine over UDP.
  2. Implement real-time RFC 3550 Interarrival Jitter & ITU-T G.107 E-model MOS estimation.
  3. Create an interactive live dashboard demonstrating cause-and-effect network telemetry.

---

## Slide 3: Proposed Solution Overview
- Controlled UDP socket-based VoIP simulation on localhost.
- Live Network Impairment Engine introducing delay, jitter, and packet loss.
- Standardized QoS calculation engine (Latency, RFC 3550 Jitter, Sequence Gap Loss, ITU-T G.107 MOS).
- Low-latency WebSocket streaming telemetry to React Recharts dashboard.

---

## Slide 4: High-Level Architecture
- **Layer 1**: React Dashboard & Control Panel
- **Layer 2**: FastAPI Server & WebSocket Streamer
- **Layer 3**: VoIP Packet Generator (20ms frames, RTP-like headers) & Impairment Injector
- **Layer 4**: Localhost UDP Socket Communication
- **Layer 5**: Real-Time Metric Calculation Engine

---

## Slide 5: Methodology & Mathematical Foundation
- **RFC 3550 Interarrival Jitter**:
  - $D(i-1, i) = (R_i - S_i) - (R_{i-1} - S_{i-1})$
  - $J(i) = J(i-1) + (|D(i-1, i)| - J(i-1)) / 16$
- **ITU-T G.107 E-Model MOS Estimation**:
  - Transmission Rating: $R = R_0 - I_d - I_{e,eff}$
  - Delay Impairment $I_d$ & Equipment Loss Impairment $I_{e,eff}$
  - Polynomial conversion to Estimated MOS (1.0 to 5.0)

---

## Slide 6: System Modules & Implementation Status
- **Module 1**: Synthetic RTP Packet Generator — **COMPLETED**
- **Module 2**: Impairment Engine (Delay, Jitter, Loss) — **COMPLETED**
- **Module 3 & 4**: UDP Sender & Receiver Layer — **COMPLETED**
- **Module 5 & 6**: Latency, Sequence Loss & RFC 3550 Jitter — **COMPLETED**
- **Module 7**: ITU-T G.107 MOS Engine — **COMPLETED**
- **Module 8 & 9**: FastAPI Server & WebSocket Stream — **COMPLETED**
- **Module 10**: React Dashboard UI & Recharts — **COMPLETED**

---

## Slide 7: Working Prototype Overview
- Live dynamic UI with impairment sliders.
- Visual MOS Arc Meter and qualitative status indicator (EXCELLENT, GOOD, FAIR, POOR, BAD).
- Real-time time-series streaming graphs for Latency, Jitter, and Packet Loss.
- Predefined Review 2 demonstration buttons for instant scenario evaluation.

---

## Slide 8: Review 2 Test Cases & Empirical Measurements

| Scenario | Configured Delay | Configured Jitter | Configured Loss | Measured Latency | Measured Jitter | Measured Loss % | MOS | Quality |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Good Network** | 20 ms | 2 ms | 0% | 20.29 ms | 0.84 ms | 0.00% | **4.39** | **EXCELLENT** |
| **High Latency** | 200 ms | 5 ms | 0% | 201.51 ms | 0.47 ms | 0.00% | **4.17** | **GOOD** |
| **High Jitter** | 50 ms | 60 ms | 0% | 55.33 ms | 22.51 ms | 0.00% | **4.35** | **EXCELLENT** |
| **Packet Loss** | 50 ms | 10 ms | 10% | 50.96 ms | 3.41 ms | 15.79% | **1.17** | **BAD** |
| **Poor Network** | 250 ms | 80 ms | 15% | 246.66 ms | 9.20 ms | 16.67% | **1.00** | **BAD** |

---

## Slide 9: Individual Contribution
- **Student 1**: Backend Packet Generator, UDP Sockets, Impairment Engine, FastAPI Server.
- **Student 2**: Metrics Engine (RFC 3550, ITU-T G.107 MOS), WebSocket Client, React Dashboard.

---

## Slide 10: Limitations & Review 3 Future Work
- **Current Limitations**: Simulated localhost UDP traffic; synthetic payload dictionary.
- **Review 3 Work Plan**:
  1. Live microphone capture & speaker audio playback over G.711 stream.
  2. Multi-node physical network testing across Wi-Fi / LAN interfaces.
  3. Wireshark PCAP validation.
