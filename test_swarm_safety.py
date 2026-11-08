"""Deterministic safety-gate regressions for inert UAV kinematics."""
import unittest

from drone import Drone, FlightMode, Position
from swarm_safety import SimulatedMotionSafety


class SimulationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.guard = SimulatedMotionSafety()
        self.drone = Drone(1, Position(0, 0, 0))
        self.drone.current_position = Position(0, 0, 10)
        self.drone.battery_level = 90
        self.drone.is_armed = True
        self.drone.flight_mode = FlightMode.HOVER

    def assess(self, target=(20, 0, 10), peers=None, **kwargs):
        return self.guard.assess(self.drone, target, peers or {}, **kwargs)

    def test_clear_trajectory_is_accepted_in_software_simulator(self):
        decision = self.assess()
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.fallback, "none")

    def test_quorum_loss_holds_motion(self):
        decision = self.assess(quorum_available=False)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "quorum_unavailable")

    def test_latency_breach_holds_motion(self):
        result = self.assess(observed_latency_ms=420)
        self.assertFalse(result.allowed)
        self.assertEqual(result.fallback, "hold")

    def test_low_battery_and_motor_damage_refuse_network_motion(self):
        self.drone.battery_level = 8
        self.assertEqual(self.assess().fallback, "local_rth")
        self.drone.battery_level = 90
        self.drone.motors[0].operational = False
        self.assertEqual(self.assess().reason, "vehicle_health_requires_local_fallback")

    def test_neighbor_minimum_separation(self):
        decision = self.assess((10, 0, 10), {2: (12, 0, 10)})
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "target_too_close_to_neighbor")

    def test_heuristic_obstacle_predicts_unsafe_path(self):
        self.guard.add_obstacle((8, 0, 10), 4)
        result = self.assess((20, 0, 10))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "projected_obstacle_collision")

    def test_nonfinite_geometry_rejected(self):
        self.assertFalse(self.assess((float("nan"), 1, 10)).allowed)

    def test_simulator_never_authorizes_real_hardware(self):
        self.drone.use_real_drone = True
        self.assertFalse(self.assess().allowed)


if __name__ == "__main__":
    unittest.main()
