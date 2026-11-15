"""Step 2 diagnostic: real signed-heartbeat path vs offline allocation truth.

This is a controlled software-only baseline probe, NOT a sample of flight
safety, a Byzantine-detection accuracy study or an evaluation of a new method.
The coordinator does not receive the independent evaluator's ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Dict

from drone import Drone, Position
from mesh_simulation import DroneMeshSimulation
from swarm_mesh import HealthReport, InMemoryMesh
from swarm_tasks import allocate_tasks


class ManualClock:
    """Shared deterministic virtual clock for signed communication."""
    def __init__(self, now: float = 1000.0):
        self.now = float(now)

    def __call__(self) -> float:
        return self.now


def _assignment(plan: dict) -> int | None:
    assigned = [
        int(node_id) for node_id, tasks in plan.items()
        if tasks
    ]
    if len(assigned) > 1:
        raise AssertionError("Probe includes exactly one requested task")
    return assigned[0] if assigned else None


def _revision() -> str:
    if os.environ.get("GITHUB_SHA"):
        return str(os.environ["GITHUB_SHA"])
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            stderr=subprocess.DEVNULL, timeout=3
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def run_case(scenario: str) -> dict:
    """Execute a signed, quorum-certified decision and offline truth comparison.

    Peer dissemination uses the project's real InMemoryMesh cryptographic
    receive path, not running UDP peer threads or physical UAV connections.
    """
    if scenario not in {"healthy_control", "stale_position", "signed_false_health"}:
        raise ValueError("Unsupported diagnostic scenario")

    origin = {1: (60.0, 0.0), 2: (0.0, 0.0),
              3: (100.0, 0.0), 4: (130.0, 0.0)}
    drones = {i: Drone(i, Position(*xy, 0.0)) for i, xy in origin.items()}
    sim = None
    try:
        sim = DroneMeshSimulation(drones, heartbeat_timeout_s=5.0)
        clock = ManualClock()
        for node in sim.nodes.values():
            node.clock = clock
            node.channel.clock = clock

        network = InMemoryMesh(list(sim.nodes.values()))
        reported_xyz = {i: (*xy, 10.0) for i, xy in origin.items()}
        ground_truth_xyz = dict(reported_xyz)
        if scenario == "stale_position":
            # The observer's last known XYZ is old, while the simulated
            # offline truth is far away. This displacement is a controlled
            # evaluator fixture, NOT a modeled physical drone trajectory.
            ground_truth_xyz[2] = (220.0, 0.0, 10.0)

        healthy = HealthReport(90.0, 100.0, 95.0)
        reported_health = {i: healthy for i in origin}
        true_health = dict(reported_health)
        if scenario == "signed_false_health":
            # Node 2 signs its own inflated telemetry with the legitimate
            # identity; no honest peer key is stolen or impersonated.
            reported_health[2] = HealthReport(99.0, 100.0, 99.0)
            true_health[2] = HealthReport(15.0, 60.0, 50.0)

        # Stage 1: every registered node supplies authenticated position +
        # health; node 2's original cached position is near the task.
        initial_position_time = clock.now
        for node_id in sorted(sim.nodes):
            packet = sim.nodes[node_id].publish_health(
                reported_health[node_id], reported_xyz[node_id]
            )
            network.broadcast(node_id, packet)

        # Stage 2: allow the original 5 s lease to expire; re-establish fresh
        # signed health for everybody. Under stale_position, node 2 explicitly
        # omits XYZ; its previous coordinates persist in MeshNode.positions.
        clock.now += 7.0
        for node_id in sorted(sim.nodes):
            position = None if scenario == "stale_position" and node_id == 2 else reported_xyz[node_id]
            packet = sim.nodes[node_id].publish_health(reported_health[node_id], position)
            network.broadcast(node_id, packet)

        leader_node = sim.nodes[1]
        seen_health = leader_node.health[2]
        cached_position = leader_node.positions[2]
        cached_age_s = (clock.now - initial_position_time
                        if scenario == "stale_position" else 0.0)
        fresh_health_age_s = clock.now - seen_health[1]
        if not 0 <= fresh_health_age_s <= leader_node.timeout_s:
            raise AssertionError("Fresh signed health must be accepted")
        if cached_position != reported_xyz[2]:
            raise AssertionError("Cached position must match signed old observation")

        # Real signed epoch ballots, installed certificates and quorum checks.
        ballots = [(i, sim.nodes[i].begin_election(candidate=1))
                   for i in sorted(sim.nodes)]
        for node_id, packet in ballots:
            network.broadcast(node_id, packet)

        leader_id = sim.leader()
        if leader_id != 1:
            raise AssertionError(f"Signed quorum election did not converge: {leader_id}")

        tasks = {"inspection-001": (1.0, 0.0, 10.0)}
        actual_plan = sim.command_tasks(tasks)
        actual_assignee = int(next(iter(actual_plan["assigned"]))) if actual_plan["assigned"] else None

        # IMPORTANT: independent ground truth goes ONLY to the offline
        # evaluator, never to MeshNode, command_tasks or the task allocator.
        oracle = allocate_tasks(ground_truth_xyz, true_health, tasks)
        oracle_assignee = _assignment(oracle)
        actual_ground_truth_ineligible = (
            actual_assignee is not None and
            (true_health[actual_assignee].battery < 30.0 or
             true_health[actual_assignee].motor_health < 75.0 or
             true_health[actual_assignee].link_quality < 40.0)
        )

        return {
            "scenario": scenario,
            "scope": "software_only_single_scenario_diagnostic",
            "registered_member_signed": True,
            "aes_gcm_and_ed25519_receive_path": "MeshNode.receive",
            "signed_quorum_leader": leader_id,
            "recorded_audit_intent": sim.audit_ledgers[leader_id].height >= 1,
            "task_id": "inspection-001",
            "reported_health_member_2": reported_health[2].to_dict(),
            "true_health_member_2_offline_only": true_health[2].to_dict(),
            "coordinator_cached_xyz_member_2": list(cached_position),
            "true_xyz_member_2_offline_only": list(ground_truth_xyz[2]),
            "health_age_s_member_2": fresh_health_age_s,
            "position_age_s_member_2_harness_only": cached_age_s,
            "position_age_available_to_allocator": False,
            "actual_assignee": actual_assignee,
            "offline_oracle_assignee": oracle_assignee,
            "assignment_disagreement": actual_assignee != oracle_assignee,
            "actual_assignee_truth_ineligible": actual_ground_truth_ineligible,
            "actual_assignee_truth_distance_m": (
                math.dist(ground_truth_xyz[actual_assignee], tasks["inspection-001"])
                if actual_assignee is not None else None),
            "oracle_assignee_truth_distance_m": (
                math.dist(ground_truth_xyz[oracle_assignee], tasks["inspection-001"])
                if oracle_assignee is not None else None),
            "physical_flight_performed": False,
            "real_sensor_observations": False,
        }
    finally:
        if sim is not None:
            sim.stop()
        for drone in drones.values():
            if drone.running:
                drone.stop()


def run_all() -> list[dict]:
    return [run_case(scenario) for scenario in
            ("healthy_control", "stale_position", "signed_false_health")]


def write_evidence(out: str | Path, results: list[dict]) -> dict:
    """Write raw observed diagnostic records plus integrity-bound manifest."""
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(results, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    (directory / "incidents.json").write_bytes(payload)
    manifest = {
        "schema_version": 1,
        "scope": "software_only_three_handcrafted_baseline_diagnostics",
        "status": "baseline_counterexamples_not_publication_scale_data",
        "source_revision": _revision(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "result_rows": len(results),
        "scenarios": [row["scenario"] for row in results],
        "incidents_json_sha256": hashlib.sha256(payload).hexdigest(),
        "proposed_method_implemented": False,
        "physical_flight_performed": False,
        "independent_episodes": 0,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiment_outputs/consistency-gated-step2")
    args = parser.parse_args()
    results = run_all()
    manifest = write_evidence(args.out, results)
    print(json.dumps({
        "evidence_path": str(args.out),
        "sha256": manifest["incidents_json_sha256"],
        "observed_decisions": [
            {key: row[key] for key in
             ("scenario", "signed_quorum_leader", "actual_assignee",
              "offline_oracle_assignee", "assignment_disagreement",
              "actual_assignee_truth_ineligible")}
            for row in results
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
