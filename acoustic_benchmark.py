"""Deterministic, reproducible SYNTHETIC sound-source localization benchmark.

Never label this as GPS-denied drone self-localization, hardware-in-the-loop
results, synchronized microphone experiments, or real-world accuracy.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, median

import numpy as np

from acoustic_tracking import AcousticTrackingSystem, SPEED_OF_SOUND_MPS


SENSORS = {
    1: (0.0, 0.0), 2: (40.0, 0.0),
    3: (0.0, 35.0), 4: (40.0, 35.0),
}


def generate_impulses(positions, source, sample_rate, rng, noise_std=0.0,
                      window=8192):
    distances = {i: math.dist(p, source) for i, p in positions.items()}
    first = min(distances.values())
    result = {}
    for i, distance in distances.items():
        frame = np.zeros(window)
        arrival = 256 + int(round(((distance - first) / SPEED_OF_SOUND_MPS) * sample_rate))
        if arrival >= window:
            raise ValueError("Source/sensor baseline exceeds synthetic sample window")
        frame[arrival] = 1.0
        if noise_std:
            frame += rng.normal(0, noise_std, size=window)
        result[i] = frame
    return result


def benchmark(trials=8, seed=26, noise_levels=(0.0, 0.02, 0.05)):
    if not 1 <= trials <= 1000:
        raise ValueError("trials must be 1..1000")
    rng = np.random.default_rng(seed)
    tracker = AcousticTrackingSystem()
    rows = []
    for noise in noise_levels:
        if not 0 <= float(noise) <= 1:
            raise ValueError("Invalid synthetic noise range")
        for j in range(trials):
            # Deterministic moving-source sweep through the known sensor frame.
            ratio = (j + 0.5) / trials
            truth = (8.0 + 22.0 * ratio, 7.0 + 17.0 * ratio)
            signals = generate_impulses(SENSORS, truth, 48000., rng, noise_std=float(noise))
            result = tracker.localize(
                signals, SENSORS, 48000., total_round_trip_ms=50.,
                acoustic_latency_limit_ms=280.,
                clock_uncertainty_s=1.0 / 48000.,
            )
            estimated = result.get("source_position")
            position_error = (math.dist(truth, (estimated["x"], estimated["y"]))
                              if estimated else None)
            rows.append({
                "seed": seed,
                "trial": j,
                "noise_std": float(noise),
                "truth_x_m": truth[0], "truth_y_m": truth[1],
                "detected": bool(result.get("detected")),
                "reason": result.get("reason", ""),
                "est_x_m": estimated["x"] if estimated else "",
                "est_y_m": estimated["y"] if estimated else "",
                "position_error_m": position_error if position_error is not None else "",
                "tdoa_residual_rmse_m": result.get("tdoa_residual_rmse_m", ""),
                "confidence_heuristic": result.get("confidence", 0.0),
                "source_only": True,
                "sensor_clock_simulated": True,
            })
    summaries = {}
    for noise in noise_levels:
        group = [r for r in rows if r["noise_std"] == float(noise)]
        errors = [r["position_error_m"] for r in group if r["detected"]]
        summaries[str(float(noise))] = {
            "trials": len(group),
            "detected_count": len(errors),
            "detection_fraction": len(errors) / len(group),
            "mean_position_error_m": mean(errors) if errors else None,
            "median_position_error_m": median(errors) if errors else None,
        }
    return rows, {
        "method": "synthetic_impulse_tdoa_known_sensor_2d",
        "seed": seed, "rate_hz": 48000., "source_is_drone_position": False,
        "hardware_verified": False,
        "clock_synchronization_is_simulated": True,
        "reference_frame": "known_sensor_xy_m",
        "noise": summaries,
    }


def write_results(rows, summary, directory):
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "synthetic_acoustic_trials.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    json_path = output / "synthetic_acoustic_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    return csv_path, json_path


def main():
    parser = argparse.ArgumentParser(description="Reproducible synthetic acoustic source benchmark")
    parser.add_argument("--trials", type=int, default=8)
    parser.add_argument("--seed", type=int, default=26)
    parser.add_argument("--out", default="experiment_outputs/acoustic")
    args = parser.parse_args()
    rows, result = benchmark(args.trials, args.seed)
    files = write_results(rows, result, args.out)
    print(json.dumps({"files": list(map(str, files)), "summary": result}, indent=2))


if __name__ == "__main__":
    main()
