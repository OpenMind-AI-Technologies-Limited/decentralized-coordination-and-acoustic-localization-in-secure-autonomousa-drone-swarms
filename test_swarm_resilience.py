"""End-to-end resilient swarm laboratory: certified audit, TDOA, safety."""
import math
import time
import unittest

import numpy as np

from acoustic_tracking import SPEED_OF_SOUND_MPS
from drone import FlightMode
from mesh_simulation import DroneMeshSimulation
from test_mesh_simulation import make_drones


def make_acoustic_signals(points, source=(7., 8.), rate=48000.):
    distances = {i: math.dist(position, source) for i, position in points.items()}
    first = min(distances.values())
    frames = {}
    for i, distance in distances.items():
        frame = np.zeros(8192)
        frame[256 + round((distance - first) / SPEED_OF_SOUND_MPS * rate)] = 1.
        frames[i] = frame
    return frames


class ResilientSwarmIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.drones = make_drones()
        self.sim = DroneMeshSimulation(self.drones)
        self.sim.start()
        for drone in self.drones.values():
            drone.current_position.z = 10.
            drone.is_armed = True
            drone.flight_mode = FlightMode.HOVER
        self.assertEqual(self.sim.wait_for_leader(9.), 1)

    def tearDown(self):
        self.sim.stop()
        for drone in self.drones.values():
            if drone.running:
                drone.stop()

    def test_authenticated_formation_has_quorum_signed_audit_evidence(self):
        self.sim.command_formation("v", (0., 0., 10.), (1., 0.), 12.)
        self.assertTrue(all(log.height == 1 for log in self.sim.audit_ledgers.values()))
        tips = {log.tip for log in self.sim.audit_ledgers.values()}
        self.assertEqual(len(tips), 1)
        self.assertEqual(self.sim.audit_ledgers[1].commits[0]["proposal"]["event"]["kind"],
                         "formation_intent")

    def test_leader_recovery_and_audit_catchup(self):
        result = self.sim.audit_event({"kind": "sensor_health", "valid": True})
        self.assertEqual(result["approvals"], 4)
        self.sim.stop_node(1)
        self.assertEqual(self.sim.wait_for_leader(9.), 2)
        result = self.sim.audit_event({"kind": "recoverable_mission"})
        self.assertEqual(result["approvals"], 3)
        self.assertEqual(self.sim.audit_ledgers[1].height, 1)
        self.assertEqual(self.sim.reconcile_audit(1), 1)
        self.assertTrue(self.sim.audit_ledgers[1].consistent_with(self.sim.audit_ledgers[2]))

    def test_acoustic_sound_source_detection_is_audited_but_does_not_auto_fly(self):
        points = {i: (d.current_position.x, d.current_position.y) for i, d in self.drones.items()}
        signals = make_acoustic_signals(points)
        result = self.sim.localize_acoustic(signals, 48000., clock_uncertainty_s=0.00001)
        self.assertTrue(result["detected"], result)
        self.assertEqual(result["estimate_type"], "sound_source_xy")
        self.assertFalse(result["self_localization_supported"])
        self.assertEqual(result["audit"]["quorum"], 3)
        self.assertEqual(self.sim.audit_ledgers[2].height, 1)
        self.assertTrue(all(d.flight_mode is FlightMode.HOVER for d in self.drones.values()))

    def test_measured_peer_rtt_is_real_signed_udp_round_trip(self):
        latency_ms = self.sim.measure_peer_rtt(2, timeout_s=2.0)
        self.assertGreaterEqual(latency_ms, 0.0)
        self.assertLess(latency_ms, 2000.0)
        self.assertAlmostEqual(
            self.sim.nodes[1].measured_peer_rtt_ms[2], latency_ms)

    def test_high_observed_latency_blocks_certified_motion(self):
        self.sim.set_observed_latency_ms(500.)
        self.sim._dispatch(self.drones[1], {"kind": "goto", "target_xyz": [12., 0., 10.]})
        latest = self.sim.events[-1]
        self.assertFalse(latest["accepted"])
        self.assertEqual(latest["reason"], "latency_limit_exceeded")

    def test_obstacle_risk_blocks_simulation_motion(self):
        self.sim.add_simulated_obstacle((7., 0., 10.), 4.)
        self.sim._dispatch(self.drones[1], {"kind": "goto", "target_xyz": [13., 0., 10.]})
        latest = self.sim.events[-1]
        self.assertFalse(latest["accepted"])
        self.assertEqual(latest["reason"], "projected_obstacle_collision")


if __name__ == "__main__":
    unittest.main()
