"""Simulation-only GPS-independent receiver XY from known synchronized beacons.

This differs fundamentally from localizing an unknown sound source using
known drone sensor coordinates. Here multiple known BEACONS transmit known
timestamped signals; one receiver (the simulated drone) measures arrivals.

The transmit schedule, identities, and anchor XY reference frame MUST already
be known and authenticated. This is not autonomous GPS-denied navigation, a
field-validated clock synchronizer, or hardware microphone calibration.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import least_squares

from acoustic_tracking import SPEED_OF_SOUND_MPS


def estimate_receiver_xy(
    beacon_positions: Mapping[int, Sequence[float]],
    transmit_times_s: Mapping[int, float],
    arrival_times_s: Mapping[int, float],
    relative_schedule_uncertainty_s: float,
    speed_mps: float = SPEED_OF_SOUND_MPS,
) -> dict:
    def reject(reason):
        return {"localized": False, "reason": reason,
                "estimate_type": "beacon_receiver_xy",
                "gps_input_used": False, "hardware_verified": False}

    ids = sorted(set(beacon_positions) & set(transmit_times_s) & set(arrival_times_s))
    if len(ids) < 4:
        return reject("insufficient_known_beacons")
    try:
        uncertainty = float(relative_schedule_uncertainty_s)
        speed = float(speed_mps)
        if (not math.isfinite(uncertainty) or uncertainty < 0
                or uncertainty > 0.001 or not math.isfinite(speed) or speed <= 0):
            return reject("transmission_clock_uncertainty")
        points = np.asarray([beacon_positions[i] for i in ids], dtype=float)
        arrivals = np.asarray([arrival_times_s[i] for i in ids], dtype=float)
        transmissions = np.asarray([transmit_times_s[i] for i in ids], dtype=float)
        if (points.shape != (len(ids), 2) or not np.all(np.isfinite(points))
                or not np.all(np.isfinite(arrivals)) or
                not np.all(np.isfinite(transmissions))):
            return reject("invalid_beacon_observations")
        centered = points - points.mean(axis=0)
        singular = np.linalg.svd(centered, compute_uv=False)
        if singular[-1] < 0.25 or singular[0] / singular[-1] > 100:
            return reject("degenerate_beacon_geometry")
        # Transmit schedule correction turns arrival differences into
        # propagation-time differences. Common receiver-clock bias cancels.
        travel = arrivals - transmissions
        differences = travel - travel[0]
        for i in range(len(ids)):
            for j in range(i):
                if (abs(float(travel[i] - travel[j])) * speed >
                        math.dist(points[i], points[j]) + 2 * speed * uncertainty + 1e-6):
                    return reject("physically_impossible_tdoa")

        def residual(x):
            dist = np.linalg.norm(points - x.reshape(1, 2), axis=1)
            return (dist[1:] - dist[0]) - speed * differences[1:]

        center = points.mean(axis=0)
        guesses = [center] + [point for point in points]
        fits = []
        for start in guesses:
            result = least_squares(residual, start, loss="soft_l1", f_scale=1.0,
                                   method="trf", max_nfev=200)
            if result.success and np.all(np.isfinite(result.x)):
                rmse = math.sqrt(float(np.mean(result.fun ** 2)))
                fits.append((rmse, math.dist(result.x, center), result))
        if not fits:
            return reject("solver_failed")
        rmse, _, best = min(fits, key=lambda item: (item[0], item[1]))
        jac_singular = np.linalg.svd(best.jac, compute_uv=False)
        if jac_singular.size < 2 or jac_singular[-1] < 1e-3:
            return reject("insufficient_receiver_observability")
        if rmse > max(2.0, 2.0 * speed * uncertainty):
            return reject("high_tdoa_residual")
        return {
            "localized": True,
            "estimate_type": "beacon_receiver_xy",
            "receiver_position": {"x": float(best.x[0]), "y": float(best.x[1])},
            "tdoa_residual_rmse_m": float(rmse),
            "reference_frame": "known_synchronized_beacon_xy",
            "known_beacon_ids": ids,
            "gps_input_used": False, "hardware_verified": False,
            "clock_uncertainty_s": uncertainty,
            "confidence_is_calibrated": False,
        }
    except (ValueError, TypeError, OverflowError, FloatingPointError):
        return reject("invalid_beacon_observations")
