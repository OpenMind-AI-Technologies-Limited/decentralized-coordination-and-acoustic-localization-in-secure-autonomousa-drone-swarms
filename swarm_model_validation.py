"""Validated *advisory-only* physical velocity model for simulated drones.

The PhysicalMLTrainer learns control-velocity regression, not collision risk.
No predicted velocity from this module can bypass motion safety rules or
directly drive the actuator/flight-control backend.
"""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np


def model_readiness(trainer, min_holdout_samples: int = 10,
                    max_validation_mse: float = 1.0) -> dict:
    reason = "model_not_available"
    metrics = getattr(trainer, "training_metrics", None) or {}
    weights = getattr(trainer, "weights", None)
    if weights is None or not metrics:
        return {"ready_for_advisory": False, "reason": reason, "advisory_only": True}
    if not isinstance(metrics, Mapping):
        return {"ready_for_advisory": False, "reason": "invalid_metrics", "advisory_only": True}
    try:
        sample_count = int(metrics["samples"])
        val_samples = int(metrics["val_samples"])
        val_mse = float(metrics["val_mse"])
        coefficients = np.asarray(weights, dtype=float)
        if (sample_count < 50 or val_samples < min_holdout_samples
                or not math.isfinite(val_mse) or val_mse < 0
                or val_mse > max_validation_mse
                or coefficients.ndim != 2 or coefficients.shape[1] != 3
                or not np.all(np.isfinite(coefficients))):
            reason = "validation_gate_failed"
            ready = False
        else:
            reason = "holdout_metrics_accepted"
            ready = True
    except (KeyError, ValueError, TypeError, OverflowError):
        reason, ready = "invalid_metrics", False
    return {
        "ready_for_advisory": ready,
        "reason": reason,
        "advisory_only": True,
        "validation_mse": float(metrics.get("val_mse", 0)) if ready else None,
        "holdout_samples": int(metrics.get("val_samples", 0)) if ready else None,
        "model_type": "telemetry_to_velocity_ridge_regression",
        "collision_classifier": False,
    }


def velocity_advisory(trainer, features, max_speed_mps: float = 12.0) -> dict:
    status = model_readiness(trainer)
    if not status["ready_for_advisory"]:
        return status
    if not math.isfinite(max_speed_mps) or max_speed_mps <= 0:
        raise ValueError("Invalid speed limit")
    try:
        if len(features) != 7 or not all(math.isfinite(float(x)) for x in features):
            raise ValueError("Invalid feature vector")
        prediction = np.asarray(trainer.predict([float(x) for x in features]), dtype=float)
        if prediction.shape not in ((3,), (1, 3)) or not np.all(np.isfinite(prediction)):
            raise ValueError("Unsafe predictor output")
        vec = prediction.reshape(3)
        speed = np.linalg.norm(vec)
        if speed > max_speed_mps:
            vec = vec * (max_speed_mps / speed)
        return {**status, "velocity_xyz_mps": [float(x) for x in vec]}
    except (ValueError, TypeError, OverflowError):
        return {**status, "ready_for_advisory": False,
                "reason": "invalid_prediction", "velocity_xyz_mps": None}
