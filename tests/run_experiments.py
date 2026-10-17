"""
Experiments for the two realism features.

A) Random vs bursty loss: same average loss, different pattern.
B) Jitter buffer trade-off: buffer off, fixed depths, and adaptive,
   under two jitter levels.

Run from the project root:
    python tests/run_experiments.py

Writes docs/sweep/experiments.json, experiments.csv and (if matplotlib is
installed) two PNG graphs.
"""
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.simulation.simulator import VoIPSimulator  # noqa: E402

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "sweep")
BUFFER_RUN_SECONDS = 8.0
BURST_RUN_SECONDS = 30.0   # bursts are rare events, so these runs are longer
DRAIN_SECONDS = 0.7
WORKERS = 6                # simulations run side by side, each on its own port


def run_point(port, seconds, **cfg):
    sim = VoIPSimulator(target_port=port)
    sim.update_config(**cfg)
    sim.start()
    time.sleep(seconds)
    sim.stop_sender()
    time.sleep(DRAIN_SECONDS)
    m = sim.get_current_metrics()
    sim.stop()
    return m


def experiment_burst(port):
    jobs = []
    for loss in [2, 4, 6, 8, 10, 15]:
        for mode in ["random", "burst"]:
            jobs.append((port, loss, mode))
            port += 1

    def work(job):
        prt, loss, mode = job
        return job, run_point(prt, BURST_RUN_SECONDS, delay_ms=50.0, jitter_ms=5.0,
                              packet_loss_pct=float(loss), loss_mode=mode,
                              burst_length=5.0, buffer_mode="off")

    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for (prt, loss, mode), m in pool.map(work, jobs):
            rows.append({"experiment": "burst", "loss_mode": mode, "configured_loss_pct": loss,
                         "measured_loss_pct": m["packet_loss"], "burst_ratio": m["burst_ratio"],
                         "mos": m["mos"], "quality": m["quality"],
                         "packets_sent": m["packets_sent"], "packets_lost": m["packets_lost"]})
            print(f"loss={loss:>2}% {mode:6} measured={m['packet_loss']:5.2f}%  "
                  f"burstR={m['burst_ratio']:4.2f}  MOS={m['mos']:.2f}", flush=True)
    return rows, port


def experiment_buffer(port):
    settings = [("off", 0)] + [("fixed", d) for d in (20, 40, 60, 80, 100, 150)] + [("adaptive", 0)]
    jobs = []
    for jitter in (30.0, 60.0):
        for mode, depth in settings:
            jobs.append((port, jitter, mode, depth))
            port += 1

    def work(job):
        prt, jitter, mode, depth = job
        return job, run_point(prt, BUFFER_RUN_SECONDS, delay_ms=50.0, jitter_ms=jitter,
                              packet_loss_pct=0.0, loss_mode="random",
                              buffer_mode=mode, buffer_ms=float(depth))

    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for (prt, jitter, mode, depth), m in pool.map(work, jobs):
            label = "off" if mode == "off" else ("adaptive" if mode == "adaptive" else f"{depth} ms")
            rows.append({"experiment": "buffer", "configured_jitter_ms": jitter, "buffer": label,
                         "buffer_depth_ms": m["buffer_ms"], "late_pct": m["late_pct"],
                         "playout_delay_ms": m["playout_delay"], "effective_loss_pct": m["effective_loss"],
                         "mos": m["mos"], "quality": m["quality"]})
            print(f"jitter={jitter:>4.0f}  buffer={label:9} depth={m['buffer_ms']:6.1f} ms  "
                  f"late={m['late_pct']:5.2f}%  playout={m['playout_delay']:6.1f} ms  MOS={m['mos']:.2f}",
                  flush=True)
    return rows, port


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    port = 5300
    burst_rows, port = experiment_burst(port)
    buffer_rows, port = experiment_buffer(port)

    with open(os.path.join(OUT_DIR, "experiments.json"), "w") as f:
        json.dump({"burst_vs_random": burst_rows, "jitter_buffer": buffer_rows}, f, indent=2)

    with open(os.path.join(OUT_DIR, "experiments.csv"), "w", newline="") as f:
        w = csv.writer(f)
        keys = sorted({k for r in burst_rows + buffer_rows for k in r})
        w.writerow(keys)
        for r in burst_rows + buffer_rows:
            w.writerow([r.get(k, "") for k in keys])

    try:
        make_graphs(burst_rows, buffer_rows)
    except ImportError:
        print("matplotlib not installed, skipped graphs.")


def make_graphs(burst_rows, buffer_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # A) random vs bursty. Bursts are rare events, so the loss that actually
    # happened in each run differs from the setting; plot against measured loss.
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for mode, color in (("random", "#1f4e8c"), ("burst", "#c0392b")):
        pts = sorted((r for r in burst_rows if r["loss_mode"] == mode),
                     key=lambda r: r["measured_loss_pct"])
        ax.plot([r["measured_loss_pct"] for r in pts], [r["mos"] for r in pts],
                marker="o", color=color, lw=2,
                label="Random loss" if mode == "random" else "Bursty loss (avg 5 packets)")
    ax.set_xlabel("Measured packet loss (%)")
    ax.set_ylabel("Estimated MOS")
    ax.set_ylim(1.0, 4.5)
    ax.set_title("Same loss, different pattern: bursts score lower")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "burst_vs_random.png"), dpi=150)
    plt.close(fig)

    # B) jitter buffer trade-off
    labels = []
    for r in buffer_rows:
        if r["buffer"] not in labels:
            labels.append(r["buffer"])
    xs = list(range(len(labels)))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    panels = [("mos", "Estimated MOS"), ("late_pct", "Late packets discarded (%)"),
              ("playout_delay_ms", "Playout delay (ms)")]
    for ax, (key, title) in zip(axes, panels):
        for jitter, color in ((30.0, "#1f4e8c"), (60.0, "#c0392b")):
            pts = {r["buffer"]: r for r in buffer_rows if r["configured_jitter_ms"] == jitter}
            ax.plot(xs, [pts[l][key] for l in labels], marker="o", color=color, lw=2,
                    label=f"jitter setting {int(jitter)} ms")
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=35, fontsize=8)
        ax.set_xlabel("Jitter buffer")
        ax.set_title(title)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "jitter_buffer_tradeoff.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
