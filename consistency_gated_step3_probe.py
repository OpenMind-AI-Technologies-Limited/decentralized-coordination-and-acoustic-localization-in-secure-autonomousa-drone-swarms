"""Handcrafted Step 3 gate diagnostics; not independent research trial data.

The idealized independent witness channel is a modeling ASSUMPTION and has
no hardware backing. True health/XYZ reaches only the offline oracle and the
explicit synthetic witness generator, never the allocation API directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from swarm_consistency_gate import (
    ConsistencyPolicy, consistency_gated_allocate, sign_witness,
)
from swarm_mesh import HealthReport, SwarmIdentity
from swarm_tasks import allocate_tasks


def _assignee(allocations: dict) -> int | None:
    found = [int(member) for member, values in allocations.items() if values]
    if len(found) > 1:
        raise AssertionError("Diagnostic requests exactly one task")
    return found[0] if found else None


def run_diagnostics() -> list[dict]:
    ids = {i: SwarmIdentity(i) for i in range(1, 5)}
    roster = {i: ident.public_bytes() for i, ident in ids.items()}
    tasks = {"inspection": (1., 0., 10.)}
    base_xyz = {
        1: (60., 0., 10.), 2: (0., 0., 10.),
        3: (100., 0., 10.), 4: (130., 0., 10.),
    }
    all_healthy = HealthReport(90., 100., 95.)
    conditions = (
        "healthy_control",
        "stale_position",
        "signed_false_health_no_witness",
        "signed_false_health_corrob",
        "signed_false_health_missing_witness_strict",
    )
    results = []
    for scenario in conditions:
        now = 1000.
        positions = dict(base_xyz)
        reported_health = {i: all_healthy for i in ids}
        offline_true_positions = dict(positions)
        offline_true_health = dict(reported_health)
        position_seen = {i: now for i in ids}
        witness_map = {}
        policy = ConsistencyPolicy()
        if scenario == "stale_position":
            position_seen[2] = now-7.
            offline_true_positions[2] = (220., 0., 10.)
        if scenario.startswith("signed_false_health"):
            reported_health[2] = HealthReport(99., 100., 99.)
            offline_true_health[2] = HealthReport(15., 60., 50.)
        if scenario.endswith("_corrob"):
            policy = ConsistencyPolicy(min_health_witnesses=2)
            # In this controlled idealized case, two other registered
            # observers directly measure each subject's true resource state.
            # They sign those independently obtained synthetic measurements.
            witness_map = {
                subject: [
                    sign_witness(ids[reporter], subject_id=subject, epoch=1,
                                 observed_at=now,
                                 health=offline_true_health[subject])
                    for reporter in ids if reporter != subject
                ][:2] for subject in ids
            }
        if scenario.endswith("_strict"):
            policy = ConsistencyPolicy(min_health_witnesses=2)
        baseline = allocate_tasks(positions, reported_health, tasks)
        filtered = consistency_gated_allocate(
            positions=positions, health=reported_health,
            health_seen_at={i:now for i in ids},
            position_seen_at=position_seen, now=now,
            tasks=tasks, roster=roster, epoch=1,
            policy=policy, witnesses=witness_map)
        oracle = allocate_tasks(offline_true_positions,offline_true_health,tasks)
        old = _assignee(baseline)
        new = _assignee(filtered["allocations"])
        true_ineligible = (
            new is not None and (
                offline_true_health[new].battery < 30 or
                offline_true_health[new].motor_health < 75 or
                offline_true_health[new].link_quality < 40
            ))
        results.append({
            "scenario": scenario,
            "baseline_assignee": old,
            "gate_assignee": new,
            "offline_oracle_assignee": _assignee(oracle),
            "gate_disagrees_with_oracle": new != _assignee(oracle),
            "gate_assignee_truth_ineligible": true_ineligible,
            "gate_reason_member_2": filtered["decisions"][2]["reason"],
            "gate_action_member_2": filtered["decisions"][2]["action"],
            "gate_evidence_tier_member_2": filtered["decisions"][2]["evidence_tier"],
            "gate_status": filtered["decision_status"],
            "unassigned_count": len(filtered["unassigned"]),
            "independent_observation_model": (
                "idealized_peer_sensor_truth"
                if witness_map else "none"),
            "physical_flight_performed": False,
        })
    return results


def write_output(folder: Path, rows: list[dict]) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(rows, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    (folder/"gate_diagnostics.json").write_bytes(raw)
    try:
        sha = os.environ.get("GITHUB_SHA") or subprocess.check_output(
            ["git","rev-parse","HEAD"],text=True,stderr=subprocess.DEVNULL,timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        sha = "unavailable"
    manifest = {
        "schema_version": 1,
        "source_revision": sha,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "scope": "software_only_five_handcrafted_diagnostics",
        "rows": len(rows),
        "independent_experiment_episodes": 0,
        "hardware_verified": False,
        "real_witness_measurements": False,
        "new_paper_comparative_results_established": False,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    (folder/"manifest.json").write_text(
        json.dumps(manifest,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="experiment_outputs/consistency-gated-step3")
    args=parser.parse_args()
    rows=run_diagnostics()
    manifest=write_output(Path(args.out),rows)
    print(json.dumps({"sha256":manifest["sha256"],"incidents":rows},indent=2))


if __name__=="__main__":
    main()
