"""
Parameter sweep for the performance analysis section.

Turns one impairment knob at a time (delay, jitter, loss) while the other two
stay at the "good network" baseline, runs the live UDP simulation for each
setting, and records what the metric engine measured.

Run from the project root:
    python tests/run_sweep.py

Writes docs/sweep/sweep_results.json and sweep_results.csv. If matplotlib is
installed it also writes one PNG graph per sweep.
"""
import csv
import json
import os
import sys
import time

# Lets this script import the backend package when run as "python tests/run_sweep.py"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.simulation.simulator import VoIPSimulator  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "sweep")
RUN_SECONDS = 8.0      # about 400 packets per setting
DRAIN_SECONDS = 0.7    # lets delayed packets arrive before reading final numbers
BASE = {"delay_ms": 20.0, "jitter_ms": 2.0, "packet_loss_pct": 0.0}

# The values tried for each knob, in steps from the minimum to the maximum the app allows
SWEEPS = {
    "delay_ms": [0, 50, 100, 150, 200, 250, 300, 350, 400, 450, 500],
    "jitter_ms": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    "packet_loss_pct": [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30],
}


# Runs one simulation with the given settings and returns what was measured.
# Every run gets its own UDP port so a previous run's leftovers cannot interfere.
def run_point(cfg, port):
    sim = VoIPSimulator(target_port=port)
    sim.update_config(**cfg)
    sim.start()
    time.sleep(RUN_SECONDS)
    sim.stop_sender()                # stop sending, but keep listening...
    time.sleep(DRAIN_SECONDS)        # ...so packets still travelling can arrive before we read the result
    m = sim.get_current_metrics()
    sim.stop()
    return {
        "configured_delay_ms": cfg["delay_ms"],
        "configured_jitter_ms": cfg["jitter_ms"],
        "configured_loss_pct": cfg["packet_loss_pct"],
        "measured_latency_ms": m["latency_avg"],
        "measured_jitter_ms": m["jitter"],
        "measured_loss_pct": m["packet_loss"],
        "packets_sent": m["packets_sent"],
        "packets_received": m["packets_received"],
        "r_factor": m["r_factor"],
        "mos": m["mos"],
        "quality": m["quality"],
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    results = {}
    port = 5100   # first port used; each run adds 1
    for knob, values in SWEEPS.items():
        results[knob] = []
        for v in values:
            # Start from the healthy baseline and change only the knob being swept
            cfg = dict(BASE)
            cfg[knob] = float(v)
            row = run_point(cfg, port)
            port += 1
            results[knob].append(row)
            print(f"{knob}={v:>5}  latency={row['measured_latency_ms']:7.2f} ms  "
                  f"jitter={row['measured_jitter_ms']:6.2f} ms  "
                  f"loss={row['measured_loss_pct']:5.2f} %  MOS={row['mos']:.2f}", flush=True)

    with open(os.path.join(OUT_DIR, "sweep_results.json"), "w") as f:
        json.dump({"baseline": BASE, "run_seconds": RUN_SECONDS, "results": results}, f, indent=2)

    with open(os.path.join(OUT_DIR, "sweep_results.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sweep", "configured_delay_ms", "configured_jitter_ms", "configured_loss_pct",
                    "measured_latency_ms", "measured_jitter_ms", "measured_loss_pct",
                    "packets_sent", "packets_received", "r_factor", "mos", "quality"])
        for knob, rows in results.items():
            for r in rows:
                w.writerow([knob, r["configured_delay_ms"], r["configured_jitter_ms"],
                            r["configured_loss_pct"], r["measured_latency_ms"],
                            r["measured_jitter_ms"], r["measured_loss_pct"], r["packets_sent"],
                            r["packets_received"], r["r_factor"], r["mos"], r["quality"]])

    # Graphs are optional: if matplotlib is not installed we still keep the data files
    try:
        make_graphs(results)
    except ImportError:
        print("matplotlib not installed, skipped graphs (results saved as JSON and CSV).")


def make_graphs(results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    titles = {
        "delay_ms": ("Configured delay (ms)", "configured_delay_ms", "MOS vs delay"),
        "jitter_ms": ("Configured jitter (ms)", "configured_jitter_ms", "MOS vs jitter"),
        "packet_loss_pct": ("Configured packet loss (%)", "configured_loss_pct", "MOS vs packet loss"),
    }
    # Coloured bands behind the line show which rating (Excellent...Bad) each MOS value falls in
    bands = [(4.3, 4.5, "Excellent"), (4.0, 4.3, "Good"), (3.6, 4.0, "Fair"),
             (3.1, 3.6, "Poor"), (1.0, 3.1, "Bad")]
    shades = ["#d8f0dc", "#e6f4d7", "#fbf3cf", "#fbe3c8", "#f8d4d4"]

    for knob, rows in results.items():
        xlabel, key, title = titles[knob]
        xs = [r[key] for r in rows]
        ys = [r["mos"] for r in rows]
        fig, ax = plt.subplots(figsize=(7, 4.2))
        for (lo, hi, _), c in zip(bands, shades):
            ax.axhspan(lo, hi, color=c, lw=0)
        ax.plot(xs, ys, marker="o", color="#1f4e8c", lw=2)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Estimated MOS")
        ax.set_ylim(1.0, 4.5)
        ax.set_title(title + " (other two settings at baseline)")
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT_DIR, f"mos_vs_{knob}.png"), dpi=150)
        plt.close(fig)

    # measured vs configured for the three knobs. A dashed "ideal" line shows where the points
    # would sit if the measurement matched the setting exactly, so you can see how close they are.
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    pairs = [("delay_ms", "configured_delay_ms", "measured_latency_ms", "Delay (ms)"),
             ("jitter_ms", "configured_jitter_ms", "measured_jitter_ms", "Jitter (ms)"),
             ("packet_loss_pct", "configured_loss_pct", "measured_loss_pct", "Packet loss (%)")]
    for ax, (knob, ck, mk, label) in zip(axes, pairs):
        xs = [r[ck] for r in results[knob]]
        ys = [r[mk] for r in results[knob]]
        ax.plot(xs, xs, "--", color="#999", label="ideal (measured = configured)")
        ax.plot(xs, ys, marker="o", color="#1f4e8c", label="measured")
        ax.set_xlabel("Configured " + label)
        ax.set_ylabel("Measured " + label)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "measured_vs_configured.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
