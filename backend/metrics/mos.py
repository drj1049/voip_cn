"""
MOS (Mean Opinion Score) Estimation Engine based on ITU-T G.107 E-model Standard
"""
from typing import Dict, Any

class MOSEstimator:
    """
    Computes Estimated MOS (1.0 to 5.0) using ITU-T G.107 E-Model methodology.
    Uses measured Latency, Jitter, and Packet Loss as real-time inputs.
    """

    @staticmethod
    def calculate_r_factor(latency_ms: float, jitter_ms: float, packet_loss_pct: float, burst_ratio: float = 1.0) -> float:
        """
        Calculates Transmission Rating Factor R (0 - 100).
        Formula: R = R0 - Id - Ie_eff
        """
        # Start from the best score a clean phone line can get, then subtract penalties:
        # one for delay (Id) and one for lost packets (Ie_eff).
        R0 = 93.2  # Base signal-to-noise rating factor

        # 1. Delay Impairment (Id)
        # Jitter is not its own input in the E-model, so it is folded into the delay: a call
        # with jittery packets needs a bigger buffer, and the buffer adds delay.
        # The +10 is a small allowance for encoding and processing time.
        # Effective one-way delay including jitter buffer overhead
        effective_delay = latency_ms + (2.0 * jitter_ms) + 10.0

        # Delay barely hurts up to about 177 ms. Past that point people start talking over
        # each other, so the penalty grows faster (the extra 0.11 term).
        if effective_delay < 177.0:
            Id = 0.024 * effective_delay
        else:
            Id = 0.024 * effective_delay + 0.11 * (effective_delay - 177.0)

        # 2. Equipment Impairment (Ie_eff) due to Packet Loss
        # Standard G.711 codec parameters: Ie = 0, Bpl = 4.3
        # Ie = how bad the codec itself sounds (0 for G.711, it is not compressed).
        # Bpl = how well the codec copes with lost packets (4.3 is the G.711 value without
        # any loss concealment, which is why loss is punished so hard here).
        Ie = 0.0
        Bpl = 4.3
        P_loss = max(0.0, float(packet_loss_pct))   # never let a negative number through

        # BurstR (G.107) is 1 for random loss and above 1 when losses come in
        # bursts, which lowers the quality score for the same average loss.
        burst_r = max(1.0, float(burst_ratio))
        Ie_eff = Ie + (95.0 - Ie) * (P_loss / (P_loss / burst_r + Bpl))

        # 3. Overall R-Factor
        R = R0 - Id - Ie_eff
        return max(0.0, min(100.0, R))   # R is defined on a 0 to 100 scale

    @classmethod
    def calculate_mos(cls, latency_ms: float, jitter_ms: float, packet_loss_pct: float, burst_ratio: float = 1.0) -> float:
        """
        Converts R-factor into Estimated MOS (1.0 to 4.5/5.0).
        Standard ITU-T G.107 conversion polynomial.
        """
        R = cls.calculate_r_factor(latency_ms, jitter_ms, packet_loss_pct, burst_ratio)

        # This polynomial is the standard conversion from R (0-100) to MOS (1-4.5).
        # The ends are handled separately so we never go outside the scale.
        if R <= 0:
            mos = 1.0
        elif R >= 100:
            mos = 4.5
        else:
            mos = 1.0 + (0.035 * R) + (R * (R - 60.0) * (100.0 - R) * 0.000007)

        return round(max(1.0, min(4.5, mos)), 2)

    @classmethod
    def classify_quality(cls, mos: float) -> str:
        """
        Classifies MOS score into qualitative call quality rating.
        """
        # Rough meaning of each band: Excellent = nobody complains, Good = fine,
        # Fair = some people notice problems, Poor = annoying, Bad = hard to use
        if mos >= 4.3:
            return "EXCELLENT"
        elif mos >= 4.0:
            return "GOOD"
        elif mos >= 3.6:
            return "FAIR"
        elif mos >= 3.1:
            return "POOR"
        else:
            return "BAD"

    @classmethod
    def get_metrics(cls, latency_ms: float, jitter_ms: float, packet_loss_pct: float, burst_ratio: float = 1.0) -> Dict[str, Any]:
        """Returns snapshot dictionary of MOS estimation."""
        r_factor = cls.calculate_r_factor(latency_ms, jitter_ms, packet_loss_pct, burst_ratio)
        mos = cls.calculate_mos(latency_ms, jitter_ms, packet_loss_pct, burst_ratio)
        quality = cls.classify_quality(mos)

        return {
            "r_factor": round(r_factor, 2),
            "mos": mos,
            "quality": quality
        }
