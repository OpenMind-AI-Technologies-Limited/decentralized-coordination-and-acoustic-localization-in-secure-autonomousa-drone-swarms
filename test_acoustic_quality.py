"""Acoustic validation: source accuracy, impossible delays, clock and signal defects."""
import math
import unittest

import numpy as np

from acoustic_quality import validate_acoustic_array, validate_tdoa_physics
from acoustic_tracking import AcousticTrackingSystem, CrossCorrelationEngine, SPEED_OF_SOUND_MPS


def impulses(points, source, rate=48000., noise=0.0, seed=19):
    dists = {i: math.dist(p, source) for i, p in points.items()}
    nearest = min(dists.values())
    rnd = np.random.default_rng(seed)
    out = {}
    for i, dist in dists.items():
        frame = np.zeros(4096, dtype=float)
        index = 256 + round(((dist - nearest) / SPEED_OF_SOUND_MPS) * rate)
        frame[int(index)] = 1.0
        if noise:
            frame += rnd.normal(0., noise, size=frame.size)
        out[i] = frame
    return out


class AcousticQualityTests(unittest.TestCase):
    def setUp(self):
        self.points = {1: (0., 0.), 2: (40., 0.), 3: (0., 35.), 4: (35., 35.)}
        self.source = (18., 11.)
        self.tracker = AcousticTrackingSystem()

    def result(self, signals=None, points=None, **kwargs):
        return self.tracker.localize(
            signals=signals if signals is not None else impulses(self.points, self.source),
            sensor_positions=points if points is not None else self.points,
            sample_rate_hz=kwargs.pop("sample_rate_hz", 48000.),
            total_round_trip_ms=kwargs.pop("total_round_trip_ms", 60.),
            acoustic_latency_limit_ms=kwargs.pop("acoustic_latency_limit_ms", 280.),
            **kwargs
        )

    def test_source_error_is_independent_of_tdoa_residual_rmse(self):
        x = self.result(clock_uncertainty_s=0.00001)
        self.assertTrue(x["detected"])
        self.assertEqual(x["estimate_type"], "sound_source_xy")
        self.assertFalse(x["self_localization_supported"])
        self.assertTrue(x["clock_sync_verified"])
        self.assertAlmostEqual(x["rmse"], x["tdoa_residual_rmse_m"])
        point = x["source_position"]
        self.assertLess(math.dist((point["x"], point["y"]), self.source), 3.0)

    def test_noisy_impulse_has_bounded_delays(self):
        x = self.result(signals=impulses(self.points, self.source, noise=0.025))
        self.assertTrue(x["detected"], x)
        self.assertTrue(validate_tdoa_physics(self.points,
            {int(k): v for k, v in x["delays"].items()}, sample_rate_hz=48000.))

    def test_collinear_sensor_geometry_rejected(self):
        points = {1: (0., 0.), 2: (10., 0.), 3: (20., 0.)}
        x = self.result(signals=impulses(points, (6., 4.)), points=points)
        self.assertFalse(x["detected"])
        self.assertEqual(x["reason"], "degenerate_sensor_geometry")

    def test_nonfinite_and_silent_signal_rejected(self):
        base = impulses(self.points, self.source)
        bad = dict(base)
        bad[2] = bad[2].copy()
        bad[2][10] = np.nan
        self.assertEqual(self.result(signals=bad)["reason"], "invalid_signal")
        bad[2] = np.zeros(4096)
        self.assertEqual(self.result(signals=bad)["reason"], "silent_sensor_signal")

    def test_invalid_sampling_and_unsynchronized_clock_rejected(self):
        self.assertEqual(self.result(sample_rate_hz=0.)["reason"], "invalid_sampling_rate")
        self.assertEqual(self.result(clock_uncertainty_s=0.02)["reason"], "clock_sync_insufficient")

    def test_impossible_inter_sensor_tdoa_rejected(self):
        self.assertFalse(validate_tdoa_physics(
            self.points, {1: 0., 2: 0.5, 3: 0.0, 4: 0.0}, sample_rate_hz=48000.))

    def test_delay_sign_and_physical_bound(self):
        base = np.zeros(2048); late = np.zeros(2048)
        base[150] = 1.
        late[157] = 1.
        correlation = CrossCorrelationEngine()
        self.assertAlmostEqual(
            correlation.estimate_delay_seconds(base, late, 48000., 0.01),
            7./48000., delta=0.5/48000.)

    def test_latency_local_fallback_is_not_gps_denied_self_localization(self):
        x = self.result(total_round_trip_ms=450.)
        self.assertTrue(x["local_only"])
        self.assertFalse(x["self_localization_supported"])
        self.assertEqual(len(x["used_sensor_ids"]), 3)


if __name__ == "__main__":
    unittest.main()
