"""
Empirical results collector for the five standard demo scenarios
Runs live VoIP UDP simulation for each scenario and records actual empirical measurements.
"""
import time
import json
from backend.simulation.simulator import VoIPSimulator

def run_scenarios():
    print("=" * 95)
    print("         REAL-TIME VOIP CALL QUALITY ANALYZER — FINAL EMPIRICAL TEST RESULTS")
    print("=" * 95)

    # (name, delay ms, jitter ms, loss %) - the same five presets as the dashboard buttons
    scenarios = [
        ("Good Network", 20.0, 2.0, 0.0),
        ("High Latency", 200.0, 5.0, 0.0),
        ("High Jitter", 50.0, 60.0, 0.0),
        ("Packet Loss", 50.0, 10.0, 10.0),
        ("Poor Network", 250.0, 80.0, 15.0)
    ]

    results = []

    for name, delay, jitter, loss in scenarios:
        # A fresh simulator per scenario, on its own port (5012), so runs cannot affect each other
        # and it does not clash with the live server on 5005
        simulator = VoIPSimulator(target_port=5012)
        simulator.update_config(delay_ms=delay, jitter_ms=jitter, packet_loss_pct=loss)
        simulator.start()

        # Allow simulation to transmit ~150 packets (3 seconds)
        time.sleep(3.0)

        # Stop packet generation and allow 500ms for in-flight delayed packets to arrive
        simulator.stop_sender()
        time.sleep(0.5)

        metrics = simulator.get_current_metrics()
        simulator.stop()

        # Keep both what we asked for and what was actually measured, side by side
        res_entry = {
            "scenario": name,
            "configured_delay_ms": delay,
            "measured_latency_ms": metrics["latency_avg"],
            "configured_jitter_ms": jitter,
            "measured_jitter_ms": metrics["jitter"],
            "configured_loss_pct": loss,
            "measured_loss_pct": metrics["packet_loss"],
            "packets_sent": metrics["packets_sent"],
            "packets_received": metrics["packets_received"],
            "packets_lost": metrics["packets_lost"],
            "estimated_mos": metrics["mos"],
            "quality_rating": metrics["quality"]
        }
        results.append(res_entry)

        print(f"\nScenario: {name}")
        print(f"  Configured: Delay={delay} ms | Jitter={jitter} ms | Loss={loss}%")
        print(f"  Measured:   Avg Latency={metrics['latency_avg']:.2f} ms | RFC3550 Jitter={metrics['jitter']:.2f} ms | Loss={metrics['packet_loss']:.2f}%")
        print(f"  Counters:   Sent={metrics['packets_sent']} | Received={metrics['packets_received']} | Lost={metrics['packets_lost']}")
        print(f"  Quality:    Estimated MOS={metrics['mos']:.2f} | Rating={metrics['quality']} (R-Factor: {metrics['r_factor']:.2f})")

    # Save to JSON file (this is where the README results table comes from)
    with open("tests/demo_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 95)
    print("Results collected successfully and saved to tests/demo_results.json!")
    return results

if __name__ == "__main__":
    run_scenarios()
