"""Integration and safety tests against the existing Drone kinematics engine."""
import math
import time
import tempfile
import unittest

from drone import Drone, FlightMode, Position
from mesh_simulation import DroneMeshSimulation


def make_drones():
    origins = [(0.0, 0.0), (25.0, 0.0), (0.0, 25.0), (-25.0, 0.0)]
    drones = {i: Drone(i, Position(x, y, 0.0)) for i, (x, y) in enumerate(origins, 1)}
    for rank, drone in enumerate(drones.values()):
        drone.wind_enabled = False
        drone.battery_level = 96 - rank * 10
        drone.TAKEOFF_ALTITUDE = 2.0
    return drones


class MeshSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.drones = make_drones()
        self.sim = None

    def tearDown(self):
        if self.sim is not None:
            self.sim.stop()
        for drone in self.drones.values():
            if drone.running:
                drone.stop()

    def test_rejects_physical_drone(self):
        self.drones[3].use_real_drone = True
        with self.assertRaises(PermissionError):
            DroneMeshSimulation(self.drones)

    def test_optional_stored_identities_survive_new_simulator_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            first = DroneMeshSimulation(self.drones, identity_dir=directory)
            initial = {node_id: ident.public_bytes()
                       for node_id, ident in first._identities.items()}
            first.stop()
            second = DroneMeshSimulation(self.drones, identity_dir=directory)
            try:
                restored = {node_id: ident.public_bytes()
                            for node_id, ident in second._identities.items()}
                self.assertEqual(initial, restored)
                self.assertTrue(all(n.vote_journal is not None for n in second.nodes.values()))
            finally:
                second.stop()

    def test_rejects_incomplete_roster(self):
        with self.assertRaises(ValueError):
            DroneMeshSimulation({1: self.drones[1], 2: self.drones[2]})

    def test_remote_command_cannot_arm_or_takeoff(self):
        self.sim = DroneMeshSimulation(self.drones)
        drone = self.drones[1]
        self.sim._dispatch(drone, {"kind": "takeoff"})
        self.sim._dispatch(drone, {"kind": "goto", "target_xyz": [10, 0, 8]})
        self.assertFalse(drone.is_armed)
        self.assertTrue(all(not event["accepted"] for event in self.sim.events))

    def test_target_nan_and_altitude_are_rejected(self):
        self.sim = DroneMeshSimulation(self.drones)
        drone = self.drones[2]
        drone.is_armed = True
        drone.flight_mode = FlightMode.HOVER
        for target in ([math.nan, 0, 20], [0, 0, 101], [0, 0, -2], [1, 2]):
            self.sim._dispatch(drone, {"kind": "goto", "target_xyz": target})
        self.assertEqual(len(self.sim.events), 4)
        self.assertTrue(all(not event["accepted"] for event in self.sim.events))

    def test_simulated_drone_physics_receives_certified_v_formation(self):
        self.sim = DroneMeshSimulation(self.drones)
        self.sim.start()
        # Explicit simulator setup is deliberately not network-driven.
        for drone in self.drones.values():
            drone.is_armed = True
            drone.current_position.z = 10.0
            drone.flight_mode = FlightMode.HOVER
        self.assertEqual(self.sim.wait_for_leader(9), 1)
        self.assertEqual(self.sim.command_formation("v", (0, 0, 10), (1, 0), spacing_m=12), 1)
        until = time.monotonic() + 3
        while time.monotonic() < until and not all(
            any(event["drone_id"] == i and event["accepted"] for event in self.sim.events)
            for i in (2, 3, 4)
        ):
            time.sleep(0.05)
        accepted = {e["drone_id"] for e in self.sim.events if e["accepted"]}
        self.assertTrue({2, 3, 4}.issubset(accepted))
        self.assertTrue(all(e.get("epoch") is not None for e in self.sim.events if e["accepted"]))

    def test_certified_cooperative_task_allocation(self):
        self.sim = DroneMeshSimulation(self.drones)
        self.sim.start()
        for drone in self.drones.values():
            drone.is_armed = True
            drone.current_position.z = 10.0
            drone.flight_mode = FlightMode.HOVER
        self.assertEqual(self.sim.wait_for_leader(9), 1)
        plan = self.sim.command_tasks({
            "inspection-a": (2.0, 2.0, 10.0),
            "inspection-b": (20.0, 2.0, 10.0),
        })
        self.assertEqual(plan["unassigned"], [])
        self.assertEqual(len(plan["assigned"]), 2)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not {
            "inspection-a", "inspection-b"
        }.issubset({event.get("task_id") for event in self.sim.events if event["accepted"]}):
            time.sleep(0.05)
        executed = {event.get("task_id") for event in self.sim.events if event["accepted"]}
        self.assertTrue({"inspection-a", "inspection-b"}.issubset(executed))

    def test_election_fails_closed_without_quorum(self):
        self.sim = DroneMeshSimulation(self.drones)
        with self.assertRaises(PermissionError):
            self.sim.command_formation("v", (0, 0, 10), (1, 0))

    def test_simulated_leader_crash_recovery(self):
        self.sim = DroneMeshSimulation(self.drones)
        self.sim.start()
        self.assertEqual(self.sim.wait_for_leader(9), 1)
        self.sim.stop_node(1)
        self.assertEqual(self.sim.wait_for_leader(9), 2)


if __name__ == "__main__":
    unittest.main()
