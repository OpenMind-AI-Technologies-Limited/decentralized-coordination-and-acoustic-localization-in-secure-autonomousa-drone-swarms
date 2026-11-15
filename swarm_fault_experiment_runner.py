#!/usr/bin/env python3
"""Archive reproducible Step 4 signed-telemetry fault-injection diagnostic traces.

No flight hardware, sensor attestations, publication-scale statistics,
algorithm-superiority claims or independent real-world attack demonstrations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from swarm_telemetry_faults import FaultCase, SCENARIOS, run_fault_case


def run_suite(*, sizes=(5, 10), trials=2, seed=2026, scenarios=SCENARIOS,
              packet_loss=0.15) -> list[dict]:
    if not sizes or any(not 4 <= n <= 50 for n in sizes) or len(set(sizes)) != len(sizes):
        raise ValueError("Require unique fleet sizes between 4 and 50")
    if not 1 <= trials <= 20:
        raise ValueError("Step 4 diagnostic repeats must be 1..20")
    if not scenarios or len(set(scenarios)) != len(scenarios) or any(
            scenario not in SCENARIOS for scenario in scenarios):
        raise ValueError("Use distinct, recognized fault scenarios")
    if not 0 <= packet_loss < 1:
        raise ValueError("Invalid loss rate")
    records = []
    for size in sizes:
        for index, scenario in enumerate(scenarios):
            for trial in range(trials):
                scenario_seed = int(seed) + size * 101 + index * 100003 + trial * 1009
                # Loss is only injected during post-bootstrap telemetry.
                # The packet_loss case *also* force-drops the targeted node's
                # update, to guarantee its counterfactual is actually tested.
                case_loss = packet_loss if scenario == "packet_loss" else 0.0
                record = run_fault_case(FaultCase(
                    scenario=scenario, seed=scenario_seed, nodes=size,
                    packet_loss=case_loss))
                records.append({**record, "trial": trial})
    return records


def _revision() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            stderr=subprocess.DEVNULL, timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def write_evidence(directory: Path, rows: list[dict]) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(rows, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    (directory / "fault_trials.json").write_bytes(raw)

    columns = (
        "scenario", "nodes", "trial", "seed", "oracle_assignee_offline",
        "quorum_fresh_at_decision", "baseline_assignee", "age_only_assignee",
        "witness_strict_assignee", "baseline_truth_ineligible",
        "age_only_truth_ineligible", "witness_strict_truth_ineligible",
        "age_only_reason_node_2", "witness_strict_reason_node_2",
        "network_dropped", "network_rejected", "network_pending_delay",
        "network_transmitted_bytes",
    )
    with (directory / "fault_trial_metrics.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "scenario": row["scenario"], "nodes": row["nodes"],
                "trial": row["trial"], "seed": row["seed"],
                "oracle_assignee_offline": row["oracle_assignee_offline"],
                "quorum_fresh_at_decision": row["quorum_fresh_at_decision"],
                "baseline_assignee": row["baseline"]["assignee"],
                "age_only_assignee": row["age_only"]["assignee"],
                "witness_strict_assignee": row["witness_strict"]["assignee"],
                "baseline_truth_ineligible": row["baseline"]["truth_ineligible"],
                "age_only_truth_ineligible": row["age_only"]["truth_ineligible"],
                "witness_strict_truth_ineligible": row["witness_strict"]["truth_ineligible"],
                "age_only_reason_node_2": row["age_only"]["reason_node_2"],
                "witness_strict_reason_node_2": row["witness_strict"]["reason_node_2"],
                "network_dropped": row["network"]["dropped"],
                "network_rejected": row["network"]["rejected"],
                "network_pending_delay": row["network"]["pending_delay"],
                "network_transmitted_bytes": row["network"]["transmitted_bytes"],
            })

    files = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
             for name in ("fault_trials.json", "fault_trial_metrics.csv")}
    manifest = {
        "schema_version": 1,
        "source_revision": _revision(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "scope": "seeded_software_diagnostics_only",
        "separate_from_previous_378_trial_archive": True,
        "full_paper_comparative_evidence_available": False,
        "run_count": len(rows),
        "scenarios": sorted({row["scenario"] for row in rows}),
        "fleet_sizes": sorted({row["nodes"] for row in rows}),
        "trials_per_setting": {
            f"{n}/{scenario}": sum(
                row["nodes"] == n and row["scenario"] == scenario for row in rows)
            for n in sorted({row["nodes"] for row in rows})
            for scenario in sorted({row["scenario"] for row in rows})
        },
        "sha256": files,
        "source_of_truth": "offline_simulated_ground_truth_only",
        "witness_source": "idealized_synthetic_peer_observation",
        "real_packet_crypto_verified": True,
        "faults_injected_only_after_fault_free_bootstrap": True,
        "physical_uav_flight": False,
        "real_radio_latency": False,
        "real_sensor_measurements": False,
        "journaled_network_traffic": "no_keys_no_ciphertext",
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[5, 10])
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--packet-loss", type=float, default=0.15)
    parser.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    parser.add_argument("--out", default="experiment_outputs/consistency-gated-step4")
    args = parser.parse_args()
    rows = run_suite(sizes=tuple(args.sizes), trials=args.trials,
                     seed=args.seed, scenarios=tuple(args.scenarios),
                     packet_loss=args.packet_loss)
    manifest = write_evidence(Path(args.out), rows)
    print(json.dumps({
        "diagnostic_runs": manifest["run_count"],
        "scenarios": len(manifest["scenarios"]),
        "fleet_sizes": manifest["fleet_sizes"],
        "sha256": manifest["sha256"],
        "out": args.out,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
