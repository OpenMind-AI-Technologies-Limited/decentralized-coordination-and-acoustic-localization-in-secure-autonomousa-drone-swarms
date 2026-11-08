"""Process-local mesh agent: authenticated telemetry, UDP gossip, certified actions.

Instantiate one runtime per drone/process. Flight commands go to caller-supplied
safety-aware callbacks, never directly to physical actuators.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from swarm_formation import formation_target, separate_from_neighbors
from swarm_mesh import HealthReport, MeshNode
from swarm_transport import UdpPeerTransport


class MeshRuntime:
    def __init__(self, node: MeshNode, transport: UdpPeerTransport,
                 health_provider: Callable[[], tuple[HealthReport, tuple[float, float, float]]],
                 command_handler: Optional[Callable[[dict], None]] = None,
                 heartbeat_interval_s: float = 0.5, election_retry_s: float = 3.0):
        if transport.node_id != node.node_id:
            raise ValueError("Transport identity mismatch")
        if heartbeat_interval_s <= 0 or election_retry_s <= heartbeat_interval_s:
            raise ValueError("Invalid message timings")
        self.node = node
        self.transport = transport
        self.health_provider = health_provider
        self.command_handler = command_handler
        self.heartbeat_interval_s = heartbeat_interval_s
        self.election_retry_s = election_retry_s
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_heartbeat = 0.0
        self._last_election = time.monotonic()
        self._election_retries = 0
        self.logger = logging.getLogger(f"MeshRuntime.{node.node_id}")
        self.node.on_command = self._on_certified_command

    def _on_certified_command(self, record: dict) -> None:
        action = dict(record["action"])
        if action.get("kind") == "formation":
            try:
                desired = formation_target(
                    self.node.node_id, record["leader"], list(self.node.roster),
                    action["leader_position"], action["heading"],
                    action.get("pattern", "v"), float(action.get("spacing_m", 12.0)),
                )
                target = separate_from_neighbors(self.node.node_id, desired, self.node.positions)
            except (KeyError, TypeError, ValueError) as exc:
                self.logger.warning("Rejected invalid formation command: %s", exc)
                return
            action = {"kind": "goto", "target_xyz": list(target), "coordination_epoch": record["epoch"]}
        elif action.get("kind") == "task_assignment":
            assignments = action.get("assignments")
            if not isinstance(assignments, dict):
                self.logger.warning("Rejected malformed task allocation")
                return
            assigned = assignments.get(str(self.node.node_id))
            if assigned is None:
                return
            if not isinstance(assigned, dict):
                self.logger.warning("Rejected malformed local task")
                return
            action = {
                "kind": "goto",
                "target_xyz": assigned.get("target_xyz"),
                "task_id": assigned.get("task_id"),
                "coordination_epoch": record["epoch"],
            }
        if self.command_handler is not None:
            self.command_handler(action)

    def broadcast_action(self, action: dict):
        """Only a quorum-certified leader may publish a flight directive."""
        packet = self.node.issue_command(action)
        # The leader also follows its own certified command; no unsigned
        # direct-call bypass is permitted for the local simulated drone.
        self.node.receive(packet)
        self.transport.send(packet)

    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"mesh-{self.node.node_id}", daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            now = time.monotonic()
            if now - self._last_heartbeat >= self.heartbeat_interval_s:
                try:
                    report, position = self.health_provider()
                    self.transport.send(self.node.publish_health(report, position))
                except Exception:
                    self.logger.exception("Could not publish local health")
                self._last_heartbeat = now
            try:
                packet = self.transport.receive(timeout=0.02)
                for _ in range(64):
                    if not packet:
                        break
                    try:
                        for output in self.node.receive(packet):
                            self.transport.send(output)
                    except Exception as exc:
                        self.logger.debug("Rejected peer packet: %s", exc)
                    packet = self.transport.receive(timeout=0.0)
            except OSError:
                if not self._stop.is_set():
                    self.logger.exception("Mesh receive error")
            now = time.monotonic()
            if self.node.leader_timed_out():
                self.node.expire_leader()
                self._election_retries = 0
                self._last_election = 0.0
            if self.node.leader is not None:
                self._election_retries = 0
            if self.node.leader is None and now - self._last_election >= self.election_retry_s:
                fresh = sum(1 for _, seen_at in self.node.health.values()
                            if self.node.clock() - seen_at <= self.node.timeout_s)
                if fresh >= self.node.quorum:
                    try:
                        if self.node.epoch in self.node.voted_epochs and self._election_retries < 9:
                            packet = self.node.retransmit_vote()
                            self._election_retries += 1
                        else:
                            packet = self.node.begin_election()
                            self._election_retries = 0
                        if packet is not None:
                            self.transport.send(packet)
                    except (ValueError, OSError, RuntimeError) as exc:
                        if not self._stop.is_set():
                            self.logger.warning("Election retry blocked: %s", exc)
                self._last_election = now

    def stop(self):
        self._stop.set()
        self.transport.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
