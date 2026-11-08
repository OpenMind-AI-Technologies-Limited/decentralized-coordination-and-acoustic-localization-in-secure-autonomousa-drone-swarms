"""Quality gates for *sound source* TDOA estimates with known sensor positions.

These checks cannot make drone self-localization or clock synchronization true.
They prevent obvious invalid 2D source solutions and report limitations.
"""
from __future__ import annotations

import math
from typing import Mapping, Optional, Sequence

import numpy as np


def validate_acoustic_array(
    signals: Mapping[int, Sequence[float]],
    sensor_positions: Mapping[int, Sequence[float]],
    sample_rate_hz: float,
    clock_uncertainty_s: Optional[float] = None,
) -> dict:
    ids = sorted(set(signals) & set(sensor_positions))
    if len(ids) < 3:
        return {"valid": False, "reason": "insufficient_sensors", "sensor_ids": ids}
    try:
        rate = float(sample_rate_hz)
        if not math.isfinite(rate) or not 4000.0 <= rate <= 384000.0:
            return {"valid": False, "reason": "invalid_sampling_rate", "sensor_ids": ids}
        points = np.asarray([sensor_positions[k] for k in ids], dtype=float)
        if points.shape != (len(ids), 2) or not np.all(np.isfinite(points)):
            return {"valid": False, "reason": "invalid_sensor_geometry", "sensor_ids": ids}
        centered = points - np.mean(points, axis=0)
        singular = np.linalg.svd(centered, compute_uv=False)
        if singular.size != 2 or singular[-1] < 0.25 or singular[0] / singular[-1] > 100:
            return {"valid": False, "reason": "degenerate_sensor_geometry", "sensor_ids": ids}
        frames = [np.asarray(signals[k], dtype=float) for k in ids]
        if any(frame.ndim != 1 or frame.size < 64 or not np.all(np.isfinite(frame)) for frame in frames):
            return {"valid": False, "reason": "invalid_signal", "sensor_ids": ids}
        if len({frame.size for frame in frames}) != 1:
            return {"valid": False, "reason": "unaligned_signal_windows", "sensor_ids": ids}
        if any(float(np.std(frame)) < 1e-9 for frame in frames):
            return {"valid": False, "reason": "silent_sensor_signal", "sensor_ids": ids}
        if clock_uncertainty_s is not None:
            uncertainty = float(clock_uncertainty_s)
            if not math.isfinite(uncertainty) or uncertainty < 0:
                return {"valid": False, "reason": "invalid_sync_uncertainty", "sensor_ids": ids}
            if uncertainty > 1.0 / rate:
                return {"valid": False, "reason": "clock_sync_insufficient", "sensor_ids": ids}
        return {
            "valid": True, "sensor_ids": ids,
            "geometry_condition": float(singular[0] / singular[-1]),
            "clock_sync_verified": clock_uncertainty_s is not None,
            "sample_count": int(frames[0].size),
        }
    except (ValueError, TypeError, FloatingPointError, OverflowError):
        return {"valid": False, "reason": "invalid_acoustic_input", "sensor_ids": ids}


def validate_tdoa_physics(positions: Mapping[int, Sequence[float]],
                          delays: Mapping[int, float],
                          speed_mps: float = 343.0,
                          tolerance_samples: int = 2,
                          sample_rate_hz: float = 48000) -> bool:
    ids = sorted(set(positions) & set(delays))
    if len(ids) < 3 or speed_mps <= 0 or sample_rate_hz <= 0:
        return False
    allowance = max(0, tolerance_samples) / sample_rate_hz
    for i in ids:
        for j in ids:
            if i >= j:
                continue
            delta = abs(float(delays[i]) - float(delays[j]))
            separation = math.dist(tuple(positions[i]), tuple(positions[j]))
            if not math.isfinite(delta) or delta > separation / speed_mps + allowance + 1e-9:
                return False
    return True
