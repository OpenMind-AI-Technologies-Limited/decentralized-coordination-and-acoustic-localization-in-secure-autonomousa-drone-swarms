#########################################################################
#                                                                       #
#   SECURE DRONE SWARM SYSTEM - CORE MODULE                             #
#                                                                       #
#   Developer : Md Shahanur Islam Shagor                                #
#   Role      : Project Architect & Lead Developer                      #
#   Version   : 1.0.2                                                   #
#   Status    : Production Ready                                        #
#                                                                       #
#   "Protecting the skies with decentralized intelligence."             #
#                                                                       #
#########################################################################
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import correlate

from acoustic_quality import validate_acoustic_array, validate_tdoa_physics


SPEED_OF_SOUND_MPS = 343.0


@dataclass
class AudioSensor:
    drone_id: int
    position_xy: Tuple[float, float]


class CrossCorrelationEngine:
    """Delay estimation with GCC-PHAT backed by scipy correlation."""

    def estimate_delay_seconds(self, sig_i: np.ndarray, sig_j: np.ndarray,
                               sample_rate_hz: float,
                               max_delay_s: Optional[float] = None) -> float:
        sig_i = np.asarray(sig_i, dtype=np.float64)
        sig_j = np.asarray(sig_j, dtype=np.float64)
        if sig_i.size == 0 or sig_j.size == 0 or sample_rate_hz <= 0:
            return 0.0

        if not np.all(np.isfinite(sig_i)) or not np.all(np.isfinite(sig_j)):
            raise ValueError("Nonfinite acoustic samples")
        if max_delay_s is None:
            max_samples = min(sig_i.size, sig_j.size) - 1
        else:
            if not math.isfinite(max_delay_s) or max_delay_s <= 0:
                raise ValueError("Invalid physical delay bound")
            max_samples = max(1, min(min(sig_i.size, sig_j.size) - 1,
                                     int(math.ceil(max_delay_s * sample_rate_hz))))
        # Correct sign: positive lag means j arrived later than i.
        # Compare peak locations only inside the physically plausible interval.
        n = sig_i.size + sig_j.size
        cross = np.fft.rfft(sig_j, n=n) * np.conjugate(np.fft.rfft(sig_i, n=n))
        cross /= (np.abs(cross) + 1e-12)
        gcc = np.fft.irfft(cross, n=n)
        window = np.concatenate((gcc[-max_samples:], gcc[:max_samples + 1]))
        gcc_lag = int(np.argmax(np.abs(window))) - max_samples

        direct = correlate(sig_j, sig_i, mode="full", method="fft")
        center = sig_i.size - 1
        bounded = direct[center - max_samples:center + max_samples + 1]
        direct_lag = int(np.argmax(np.abs(bounded))) - max_samples
        # Do NOT compare unnormalized direct and PHAT peak amplitudes;
        # they have different scales. Prefer direct correlation for sparse
        # high-contrast impulse arrivals, PHAT otherwise.
        contrast = float(np.max(np.abs(bounded))) / (float(np.mean(np.abs(bounded))) + 1e-12)
        lag = direct_lag if contrast > 12.0 else gcc_lag
        return float(lag) / float(sample_rate_hz)


class TDOAEstimator:
    def __init__(self, correlation_engine: Optional[CrossCorrelationEngine] = None):
        self.correlation_engine = correlation_engine or CrossCorrelationEngine()

    def estimate_delays(
        self,
        signals: Dict[int, np.ndarray],
        sample_rate_hz: float,
        reference_id: Optional[int] = None,
        sensor_positions: Optional[Dict[int, Tuple[float, float]]] = None,
    ) -> Dict[int, float]:
        if not signals:
            return {}
        ids = sorted(signals.keys())
        ref_id = int(reference_id) if reference_id is not None else ids[0]
        ref_signal = signals.get(ref_id)
        if ref_signal is None:
            return {}
        delays = {ref_id: 0.0}
        for drone_id in ids:
            if drone_id == ref_id:
                continue
            max_delay = None
            if sensor_positions is not None and ref_id in sensor_positions and drone_id in sensor_positions:
                baseline_m = math.dist(sensor_positions[ref_id], sensor_positions[drone_id])
                max_delay = baseline_m / SPEED_OF_SOUND_MPS + 2.0 / sample_rate_hz
            delay = self.correlation_engine.estimate_delay_seconds(
                ref_signal, signals[drone_id], sample_rate_hz, max_delay_s=max_delay)
            delays[drone_id] = delay
        return delays


class AcousticFusionEngine:
    """Estimate source location in 2D from pairwise TDOA constraints."""

    def estimate_source_xy(
        self,
        sensor_positions: Dict[int, Tuple[float, float]],
        delays_by_sensor: Dict[int, float],
    ) -> Tuple[Optional[Tuple[float, float]], float, float]:
        if len(sensor_positions) < 3 or len(delays_by_sensor) < 3:
            return None, 0.0, float("inf")

        ids = sorted(set(sensor_positions.keys()) & set(delays_by_sensor.keys()))
        if len(ids) < 3:
            return None, 0.0, float("inf")
        ref = ids[0]
        x0 = np.mean([sensor_positions[i][0] for i in ids])
        y0 = np.mean([sensor_positions[i][1] for i in ids])

        def residuals(state: np.ndarray) -> np.ndarray:
            xs, ys = float(state[0]), float(state[1])
            xi, yi = sensor_positions[ref]
            dist_i = math.hypot(xs - xi, ys - yi)
            res = []
            for j in ids[1:]:
                xj, yj = sensor_positions[j]
                dist_j = math.hypot(xs - xj, ys - yj)
                lhs = dist_j - dist_i
                rhs = SPEED_OF_SOUND_MPS * float(delays_by_sensor[j] - delays_by_sensor[ref])
                res.append(lhs - rhs)
            return np.asarray(res, dtype=np.float64)

        try:
            starts = [np.asarray([x0, y0], dtype=np.float64)]
            for i in ids:
                sx, sy = sensor_positions[i]
                starts.append(np.asarray([sx, sy], dtype=np.float64))
                starts.append(np.asarray([sx + 10.0, sy + 10.0], dtype=np.float64))
                starts.append(np.asarray([sx - 10.0, sy - 10.0], dtype=np.float64))

            best = None
            best_rmse = float("inf")
            for start in starts:
                fit = least_squares(residuals, start, method="trf", loss="soft_l1")
                if not fit.success:
                    continue
                rmse = math.sqrt(float(np.mean(np.square(fit.fun)))) if fit.fun.size else 0.0
                if rmse < best_rmse:
                    best = fit
                    best_rmse = rmse

            if best is None:
                return None, 0.0, float("inf")

            xy = (float(best.x[0]), float(best.x[1]))
            rmse = float(best_rmse)
            confidence = 1.0 / (1.0 + rmse / 6.0)
            confidence = max(0.0, min(1.0, confidence))
            return xy, confidence, rmse
        except Exception:
            return None, 0.0, float("inf")


class AcousticTrackingSystem:
    def __init__(self):
        self.tdoa_estimator = TDOAEstimator()
        self.fusion_engine = AcousticFusionEngine()
        self.logger = logging.getLogger("AcousticTracking")

    def localize(
        self,
        signals: Dict[int, np.ndarray],
        sensor_positions: Dict[int, Tuple[float, float]],
        sample_rate_hz: float,
        total_round_trip_ms: float,
        acoustic_latency_limit_ms: float,
        clock_uncertainty_s: Optional[float] = None,
    ) -> dict:
        ids = sorted(set(signals.keys()) & set(sensor_positions.keys()))
        if len(ids) < 3:
            return {
                "detected": False,
                "reason": "insufficient_sensors",
                "confidence": 0.0,
                "local_only": False,
            }

        quality = validate_acoustic_array(
            {i: signals[i] for i in ids},
            {i: sensor_positions[i] for i in ids},
            sample_rate_hz, clock_uncertainty_s=clock_uncertainty_s,
        )
        if not quality["valid"]:
            return {"detected": False, "reason": quality["reason"],
                    "confidence": 0.0, "local_only": False,
                    "estimate_type": "sound_source_xy"}
        if (not math.isfinite(float(total_round_trip_ms)) or
                not math.isfinite(float(acoustic_latency_limit_ms)) or
                acoustic_latency_limit_ms <= 0):
            return {"detected": False, "reason": "invalid_latency",
                    "confidence": 0.0, "local_only": False,
                    "estimate_type": "sound_source_xy"}
        local_only = float(total_round_trip_ms) > float(acoustic_latency_limit_ms)
        if local_only:
            ids = ids[:3]
            self.logger.warning(
                "Acoustic localization latency exceeded %.1fms; using local-only estimate",
                acoustic_latency_limit_ms,
            )

        used_signals = {i: signals[i] for i in ids}
        used_positions = {i: sensor_positions[i] for i in ids}
        delays = self.tdoa_estimator.estimate_delays(
            used_signals, sample_rate_hz=sample_rate_hz, sensor_positions=used_positions)
        if not validate_tdoa_physics(used_positions, delays, sample_rate_hz=sample_rate_hz):
            return {"detected": False, "reason": "physically_impossible_delays",
                    "confidence": 0.0, "local_only": local_only,
                    "estimate_type": "sound_source_xy"}
        source_xy, confidence, rmse = self.fusion_engine.estimate_source_xy(used_positions, delays)

        if source_xy is None:
            return {
                "detected": False,
                "reason": "solver_failed",
                "confidence": 0.0,
                "local_only": local_only,
            }

        return {
            "detected": True,
            "source_position": {"x": source_xy[0], "y": source_xy[1]},
            "confidence": float(confidence),
            "rmse": float(rmse),
            "delays": {str(k): float(v) for k, v in delays.items()},
            "local_only": local_only,
            "used_sensor_ids": ids,
            "estimate_type": "sound_source_xy",
            "self_localization_supported": False,
            "tdoa_residual_rmse_m": float(rmse),
            "clock_sync_verified": quality["clock_sync_verified"],
            "geometry_condition": quality["geometry_condition"],
        }
