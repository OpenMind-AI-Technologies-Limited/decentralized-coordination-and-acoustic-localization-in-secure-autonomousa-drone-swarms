"""Opt-in integration of peer coordination with the existing Drone physics simulator.

This adapter deliberately DOES NOT instantiate SwarmManager: its legacy centralized
command path would bypass quorum authorization. It rejects MAVSDK/real-drone
connections and never auto-arms a drone in response to a network packet.

Run: python mesh_simulation.py
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Mapping, Optional

from drone import Drone, FlightMode, Position
from swarm_mesh import HealthReport, MeshNode, SwarmIdentity
from swarm_identity_store import IdentityStore, VoteJournal
from swarm_runtime import MeshRuntime
from swarm_tasks import allocate_tasks
from swarm_transport import UdpPeerTransport


class DroneMeshSimulation:
    """One local UDP agent per independently simulated Drone object."""

    def __init__(self, drones: Mapping[int, Drone], *,
                 heartbeat_interval_s: float = 0.12,
                 election_retry_s: float = 0.65,
                 heartbeat_timeout_s: float = 1.5,
                 identity_dir: Optional[str] = None):
        if len(drones) < 4 or len(drones) > 50:
            raise ValueError("Demo requires between 4 and 50 fixed-member simulation nodes")
        self.drones = dict(drones)
        for node_id, drone in self.drones.items():
            if int(node_id) != drone.drone_id:
                raise ValueError("Drone map keys must equal their registered IDs")
            if drone.use_real_drone or drone.real_drone_connection or drone.mavlink_connected:
                raise PermissionError("Mesh simulation rejects all physical MAVSDK connections")
        self._lock = threading.RLock()
        self.events: list[dict] = []
        self.running = False
        self._owned_drone_ids: set[int] = set()
        self._runtimes: dict[int, MeshRuntime] = {}
        self._transports: dict[int, UdpPeerTransport] = {}
        # Persisted identities are opt-in. Each drone must have exactly one
        # trusted state writer; never share the directory between hosts.
        self._identity_store = IdentityStore(identity_dir) if identity_dir is not None else None
        self._identities = {
            node_id: (self._identity_store.load_or_create(node_id)
                      if self._identity_store is not None else SwarmIdentity(node_id))
            for node_id in self.drones
        }
        roster = {node_id: ident.public_bytes() for node_id, ident in self._identities.items()}
        group_key = os.urandom(32)  # Ephemeral demo secret. No persistent enrollment implied.
        try:
            for node_id in self.drones:
                self._transports[node_id] = UdpPeerTransport(node_id, ("127.0.0.1", 0))
            addresses = {i: t.address for i, t in self._transports.items()}
            for node_id, transport in self._transports.items():
                transport.configure_peers({peer: addr for peer, addr in addresses.items() if peer != node_id})
                node = MeshNode(
                    self._identities[node_id], roster, group_key,
                    heartbeat_timeout_s=heartbeat_timeout_s,
                    vote_journal=(VoteJournal(identity_dir, self._identities[node_id])
                                  if self._identity_store is not None else None),
                )
                drone = self.drones[node_id]
                self._runtimes[node_id] = MeshRuntime(
                    node, transport,
                    health_provider=lambda d=drone: self._health(d),
                    command_handler=lambda action, d=drone: self._dispatch(d, action),
                    heartbeat_interval_s=heartbeat_interval_s,
                    election_retry_s=election_retry_s,
                )
        except Exception:
            for transport in self._transports.values():
                transport.close()
            raise

    def _health(self, drone: Drone):
        motors = list(drone.motors)
        motor_health = 100.0 * sum(1 for motor in motors if motor.operational) / max(1, len(motors))
        if not drone.is_active or drone.flight_mode in (FlightMode.CRASHED, FlightMode.EMERGENCY_LANDING):
            motor_health = 0.0
        report = HealthReport(
            battery=max(0.0, min(100.0, float(drone.battery_level))),
            motor_health=motor_health,
            link_quality=max(0.0, min(100.0, float(drone.signal_strength))),
        )
        p = drone.current_position
        return report, (float(p.x), float(p.y), float(p.z))

    def _dispatch(self, drone: Drone, action: dict) -> None:
        """Only simulation-safe, explicitly authorized movement is permitted."""
        node_id = drone.drone_id
        event = {"drone_id": node_id, "kind": action.get("kind"), "accepted": False}
        try:
            if drone.use_real_drone or drone.real_drone_connection or drone.mavlink_connected:
                raise PermissionError("Real UAV connection detected")
            if action.get("kind") != "goto":
                raise ValueError("Unsupported network action")
            position = action["target_xyz"]
            if not isinstance(position, (list, tuple)) or len(position) != 3:
                raise ValueError("Expected three target coordinates")
            xyz = tuple(float(value) for value in position)
            if not all(math.isfinite(value) for value in xyz):
                raise ValueError("Target has nonfinite coordinates")
            if not (1.0 <= xyz[2] <= min(100.0, float(drone.MAX_ALTITUDE))):
                raise ValueError("Target altitude outside simulation safety window")
            if not drone.is_active or not drone.is_armed:
                raise ValueError("Drone not explicitly armed locally")
            if drone.flight_mode not in (FlightMode.HOVER, FlightMode.FLYING):
                raise ValueError("Drone not in a controllable flight state")
            if not drone.goto(Position(*xyz)):
                raise ValueError("Drone rejected target under its own flight constraints")
            event.update({"accepted": True, "target_xyz": list(xyz),
                          "epoch": action.get("coordination_epoch"),
                          "task_id": action.get("task_id")})
        except (ValueError, TypeError, KeyError, PermissionError) as exc:
            event["reason"] = str(exc)
        finally:
            with self._lock:
                self.events.append(event)

    @property
    def nodes(self) -> dict[int, MeshNode]:
        return {i: runtime.node for i, runtime in self._runtimes.items()}

    def start(self):
        if self.running:
            return
        self.running = True
        for node_id, drone in self.drones.items():
            if not drone.running:
                drone.start()
                self._owned_drone_ids.add(node_id)
        for runtime in self._runtimes.values():
            runtime.start()

    def stop_node(self, node_id: int) -> None:
        """Crash a simulated node and stop its UDP channel and physical model."""
        runtime = self._runtimes[node_id]
        runtime.stop()
        self.drones[node_id].stop()
        self._owned_drone_ids.discard(node_id)

    def leader(self) -> Optional[int]:
        """Return a leader only if at least one registered quorum agrees."""
        votes: dict[int, int] = {}
        for runtime in self._runtimes.values():
            node = runtime.node
            if runtime._stop.is_set() or node.leader is None or node.certificate is None:
                continue
            # A locally crashed process must never be reported as an active leader
            # while other nodes are still waiting for its heartbeat lease to expire.
            candidate_runtime = self._runtimes.get(node.leader)
            if candidate_runtime is None or candidate_runtime._stop.is_set():
                continue
            if not node.has_fresh_quorum():
                continue
            votes[node.leader] = votes.get(node.leader, 0) + 1
        quorum = next(iter(self.nodes.values())).quorum
        eligible = [node_id for node_id, count in votes.items() if count >= quorum]
        return eligible[0] if len(eligible) == 1 else None

    def wait_for_leader(self, timeout_s: float = 8.0) -> Optional[int]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            winner = self.leader()
            if winner is not None:
                return winner
            time.sleep(0.05)
        return None

    def command_formation(self, pattern: str, leader_position: tuple[float, float, float],
                          heading_xy: tuple[float, float], spacing_m: float = 12.0) -> int:
        leader_id = self.leader()
        if leader_id is None:
            raise PermissionError("No quorum-certified leader available")
        self._runtimes[leader_id].broadcast_action({
            "kind": "formation", "pattern": pattern,
            "leader_position": list(leader_position),
            "heading": list(heading_xy), "spacing_m": float(spacing_m),
        })
        return leader_id

    def command_tasks(self, tasks: Mapping[str, tuple[float, float, float]]) -> dict:
        """Send a certified greedy task plan based on fresh signed telemetry."""
        leader_id = self.leader()
        if leader_id is None:
            raise PermissionError("No quorum-certified task coordinator available")
        node = self._runtimes[leader_id].node
        now = node.clock()
        fresh_health = {
            peer: health for peer, (health, seen_at) in node.health.items()
            if peer in node.roster and 0 <= now - seen_at <= node.timeout_s
        }
        fresh_positions = {peer: node.positions[peer] for peer in fresh_health if peer in node.positions}
        allocations = allocate_tasks(fresh_positions, fresh_health, tasks)
        command_map = {
            str(peer): {"task_id": task_id, "target_xyz": list(target)}
            for peer, assignments in allocations.items()
            for task_id, target in assignments
        }
        assigned_ids = {detail["task_id"] for detail in command_map.values()}
        unassigned = sorted(task_id for task_id in tasks if task_id not in assigned_ids)
        if command_map:
            self._runtimes[leader_id].broadcast_action({
                "kind": "task_assignment",
                "assignments": command_map,
            })
        return {
            "leader": leader_id,
            "assigned": command_map,
            "unassigned": unassigned,
        }

    def stop(self):
        if not self.running:
            for transport in self._transports.values():
                transport.close()
            return
        self.running = False
        for runtime in self._runtimes.values():
            runtime.stop()
        for node_id in list(self._owned_drone_ids):
            self.drones[node_id].stop()
            self._owned_drone_ids.discard(node_id)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _type, _value, _traceback):
        self.stop()


def demo():
    """Run a headless, simulation-only election/formation/failure scenario."""
    homes = [(0, 0), (25, 0), (0, 25), (-25, 0)]
    drones = {i: Drone(i, Position(x, y, 0)) for i, (x, y) in enumerate(homes, start=1)}
    # Explicit local simulation arming; a network packet never arms a drone.
    for drone in drones.values():
        drone.TAKEOFF_ALTITUDE = 2.0
        drone.wind_enabled = False
    with DroneMeshSimulation(drones) as sim:
        # Physics threads start inside the adapter; flight commands remain local.
        for drone in drones.values():
            if not drone.arm() or not drone.takeoff():
                raise RuntimeError("Local simulator takeoff was rejected")
        if not sim.wait_for_leader(9):
            raise RuntimeError("No quorum-certified leader in simulation")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and any(
            drone.flight_mode is not FlightMode.HOVER for drone in drones.values()
        ):
            time.sleep(0.1)
        if any(drone.flight_mode is not FlightMode.HOVER for drone in drones.values()):
            raise RuntimeError("Simulated takeoff did not finish")
        first_leader = sim.command_formation("v", (0.0, 0.0, 5.0), (1.0, 0.0))
        time.sleep(0.5)
        sim.stop_node(first_leader)
        recovered = sim.wait_for_leader(8.0)
        if recovered is None or recovered == first_leader:
            raise RuntimeError("No replacement leader after simulated crash")
        print(json.dumps({"initial_leader": first_leader,
                          "replacement_leader": recovered,
                          "accepted_commands": sum(event["accepted"] for event in sim.events),
                          "events": sim.events}, indent=2))


if __name__ == "__main__":
    demo()
