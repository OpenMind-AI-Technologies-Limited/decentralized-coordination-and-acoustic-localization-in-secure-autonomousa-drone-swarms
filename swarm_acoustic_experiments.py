"""Synthetic acoustic source and GPS-disabled known-beacon receiver experiments.

Four externally positioned and synchronized beacons form a *known reference
frame*. This does not prove autonomous GPS-denied UAV self-localization.
"""
from __future__ import annotations

import math
import random

from acoustic_benchmark import benchmark
from acoustic_tracking import SPEED_OF_SOUND_MPS
from beacon_localization import estimate_receiver_xy


BEACONS = {
    1: (-25.0, -25.0), 2: (25.0, -25.0),
    3: (-25.0, 25.0), 4: (25.0, 25.0),
}


def beacon_trial(seed: int, jitter_us: float = 100.0,
                 reference_available: bool = True) -> dict:
    """One GNSS-free *simulated* receiver observation; never updates navigation."""
    if not 0 <= jitter_us <= 1000:
        raise ValueError("Synthetic timing jitter must be in 0..1000 us")
    rng = random.Random(seed)
    true_position = (rng.uniform(-15, 15), rng.uniform(-15, 15))
    schedule = {i: 10.0 + i*0.025 for i in BEACONS}
    arrival = {
        i: schedule[i] + 0.2 + math.dist(point, true_position) / SPEED_OF_SOUND_MPS
           + rng.gauss(0.0, jitter_us * 1e-6)
        for i, point in BEACONS.items()
    }
    result = estimate_receiver_xy(
        BEACONS if reference_available else {},
        schedule if reference_available else {},
        arrival if reference_available else {},
        relative_schedule_uncertainty_s=min(0.001, 4 * jitter_us * 1e-6),
    )
    point = result.get("receiver_position")
    error = (math.dist(true_position, (point["x"], point["y"]))
             if result.get("localized") and point else None)
    return {
        "family": "beacon_receiver", "nodes": 4, "seed": int(seed),
        "scenario": ("known_beacons_jitter_" + str(int(jitter_us)) + "us"
                     if reference_available else "no_beacon_reference"),
        "localized": bool(result.get("localized")),
        # Missing estimates remain None. Never impute errors as 0 or infinity.
        "position_error_m": error,
        "tdoa_fit_residual_m": result.get("tdoa_residual_rmse_m"),
        "known_reference_available": reference_available,
    }


def source_trials(trials: int, seed: int, noises=(0.0, 0.02, 0.05)) -> list[dict]:
    """Use the existing GCC-PHAT source-localization algorithm unchanged."""
    rows, _ = benchmark(trials=trials, seed=seed, noise_levels=noises)
    converted = []
    for row in rows:
        converted.append({
            "family": "acoustic_source", "nodes": 4,
            "scenario": "impulse_noise_" + str(row["noise_std"]),
            "seed": int(seed), "trial": int(row["trial"]),
            "detected": bool(row["detected"]),
            "position_error_m": (
                float(row["position_error_m"]) if row["detected"] else None
            ),
            "tdoa_fit_residual_m": (
                float(row["tdoa_residual_rmse_m"])
                if row["tdoa_residual_rmse_m"] != "" else None
            ),
        })
    return converted
