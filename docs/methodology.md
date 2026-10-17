# VoIP Quality Analyzer — Methodology & Core Algorithms

## 1. Mathematical Algorithms

### 1.1 RFC 3550 Interarrival Jitter Calculation
As defined in **RFC 3550 Section 6.4.1**, interarrival jitter $J$ is the estimate of the statistical variance of the RTP data packet interarrival time.

For packet $i$ with send timestamp $S_i$ and arrival timestamp $R_i$, and previous packet $i-1$ with $S_{i-1}$ and $R_{i-1}$:

1. Calculate transit time difference $D(i-1, i)$:
$$D(i-1, i) = (R_i - S_i) - (R_{i-1} - S_{i-1})$$

2. Update exponentially smoothed interarrival jitter $J(i)$:
$$J(i) = J(i-1) + \frac{|D(i-1, i)| - J(i-1)}{16}$$

Where factor $16$ provides continuous noise reduction and exponential smoothing over time.

---

### 1.2 ITU-T G.107 E-Model MOS Estimation Algorithm
The E-Model determines the Transmission Rating Factor $R$ (0 to 100):

$$R = R_0 - I_d - I_{e,eff}$$

#### Parameters & Sub-models:
- **Base Signal Rating $R_0$**: $93.2$
- **Delay Impairment Factor $I_d$**:
  Calculated using effective delay $d_{eff} = d_{latency} + 2 \cdot Jitter + 10$ (in ms):
  $$I_d = \begin{cases} 0.024 \cdot d_{eff}, & \text{if } d_{eff} < 177 \text{ ms} \\ 0.024 \cdot d_{eff} + 0.11 \cdot (d_{eff} - 177), & \text{if } d_{eff} \ge 177 \text{ ms} \end{cases}$$

- **Equipment Impairment Factor $I_{e,eff}$** (Packet Loss):
  For standard G.711 PCM codec ($I_e = 0$, packet loss robustness factor $B_{pl} = 4.3$):
  $$I_{e,eff} = I_e + (95 - I_e) \cdot \frac{P_{loss}}{P_{loss} + B_{pl}}$$

#### MOS Score Polynomial Conversion:
$$MOS = \begin{cases} 
1.0, & R \le 0 \\
1.0 + 0.035 R + R(R - 60)(100 - R) \cdot 7 \cdot 10^{-6}, & 0 < R < 100 \\
4.5, & R \ge 100 
\end{cases}$$

#### Qualitative Rating Scale:
- **4.3 – 5.0**: EXCELLENT
- **4.0 – 4.3**: GOOD
- **3.6 – 4.0**: FAIR
- **3.1 – 3.6**: POOR
- **1.0 – 3.1**: BAD

---

### 1.3 Sequence Gap Packet Loss Detection
Packet loss is computed by tracking 16-bit sequence numbers:

$$\text{Sequence Gap} = (Seq_i - Seq_{i-1} - 1) \pmod{65536}$$

$$\text{Loss Percentage} = \frac{\text{Packets Lost}}{\text{Total Expected}} \times 100\%$$
