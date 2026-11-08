"""GPS-free *synthetic* beacon receiver XY observability and failure tests."""
import math
import unittest

import numpy as np

from beacon_localization import estimate_receiver_xy
from acoustic_tracking import SPEED_OF_SOUND_MPS


BEACONS = {1: (0., 0.), 2: (40., 0.), 3: (0., 40.), 4: (40., 40.)}
SCHEDULE = {1: 0., 2: .1, 3: .21, 4: .37}


def arrivals(points=BEACONS, location=(18., 11.), schedule=SCHEDULE, jitter=0., seed=23):
    rng = np.random.default_rng(seed)
    return {
        i: schedule[i] + 0.05 + math.dist(position, location) / SPEED_OF_SOUND_MPS
           + float(rng.normal(0., jitter))
        for i, position in points.items()
    }


class BeaconLocalizationTests(unittest.TestCase):
    def test_known_beacon_trilateration_does_not_need_gps(self):
        truth = (18., 11.)
        result = estimate_receiver_xy(BEACONS, SCHEDULE, arrivals(location=truth), 0.00001)
        self.assertTrue(result["localized"], result)
        self.assertFalse(result["gps_input_used"])
        self.assertEqual(result["estimate_type"], "beacon_receiver_xy")
        pos = result["receiver_position"]
        self.assertLess(math.dist(truth, (pos["x"], pos["y"])), 0.3)

    def test_known_schedule_relative_offsets_are_corrected(self):
        result = estimate_receiver_xy(BEACONS, SCHEDULE, arrivals(jitter=0.00001), 0.00003)
        self.assertTrue(result["localized"], result)
        p = result["receiver_position"]
        self.assertLess(math.dist((18, 11), (p["x"], p["y"])), 1.0)

    def test_three_beacons_and_collinear_array_rejected(self):
        p = {i: BEACONS[i] for i in (1, 2, 3)}
        t = {i: SCHEDULE[i] for i in p}
        self.assertEqual(
            estimate_receiver_xy(p, t, arrivals(points=p, schedule=t), 0.00001)["reason"],
            "insufficient_known_beacons")
        line = {1: (0, 0), 2: (10, 0), 3: (20, 0), 4: (30, 0)}
        self.assertEqual(
            estimate_receiver_xy(line, SCHEDULE, arrivals(points=line), 0.00001)["reason"],
            "degenerate_beacon_geometry")

    def test_bad_time_sync_and_impossible_propagation_rejected(self):
        self.assertEqual(
            estimate_receiver_xy(BEACONS, SCHEDULE, arrivals(), 0.02)["reason"],
            "transmission_clock_uncertainty")
        broken = arrivals()
        broken[2] += 0.5
        self.assertEqual(
            estimate_receiver_xy(BEACONS, SCHEDULE, broken, 0.00001)["reason"],
            "physically_impossible_tdoa")

    def test_receiver_estimate_is_only_an_observation_not_navigation(self):
        result = estimate_receiver_xy(BEACONS, SCHEDULE, arrivals(), 0.00001)
        self.assertTrue(result["localized"])
        self.assertFalse(result["hardware_verified"])
        self.assertFalse(result["confidence_is_calibrated"])


if __name__ == "__main__":
    unittest.main()
