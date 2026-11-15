"""Step 5: paired comparator diagnostics on EXACT Step 4 signed observations.

One fault episode is the paired comparison unit. Three independent information
conditions are never pooled: raw self reports, age/motion-filtered reports,
and strict synthetic peer witness-filtered reports (information advantage).
All four allocators inside each condition see IDENTICAL tasks, eligible member
IDs, reported health, positions, capacity and cost. The oracle is offline only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import platform

from swarm_allocation_baselines import ComparableProblem, compare_allocators, hungarian_comparable
from swarm_mesh import HealthReport
from swarm_telemetry_faults import FaultCase, SCENARIOS, run_fault_case


FILTERS = ("self_reports", "age_motion_gate", "strict_synthetic_witness_gate")
COMPARATORS = ("greedy", "hungarian", "cbaa", "cbba_static")


def _health_from_dict(records: dict) -> dict[int, HealthReport]:
    return {int(member): HealthReport.from_dict(values)
            for member, values in records.items()}


def _coordinates_from_dict(records: dict) -> dict[int, tuple[float, float, float]]:
    return {int(member): tuple(float(value) for value in values)
            for member, values in records.items()}


def _make_study_tasks(fault_case: dict, seed: int) -> dict:
    """Generate extra tasks without reading truth or attacker labels."""
    rng = random.Random(int(seed) ^ 0x4F3025)
    tasks = {name: tuple(target)
             for name, target in fault_case["comparison_input"]["tasks"].items()}
    tasks["inspection-002"] = (
        round(35.0 + rng.uniform(-12., 12.), 5),
        round(18.0 + rng.uniform(-12., 12.), 5), 10.)
    tasks["inspection-003"] = (
        round(90.0 + rng.uniform(-14., 14.), 5),
        round(-25.0 + rng.uniform(-12., 12.), 5), 10.)
    return tasks


def compare_one_fault_case(fault_case: dict) -> list[dict]:
    snapshot = fault_case["comparison_input"]
    reported_positions = _coordinates_from_dict(snapshot["reported_positions"])
    reported_health = _health_from_dict(snapshot["reported_health"])
    truth = fault_case["comparison_offline_truth"]
    truth_positions = _coordinates_from_dict(truth["positions"])
    truth_health = _health_from_dict(truth["health"])
    tasks = _make_study_tasks(fault_case, int(fault_case["seed"]))
    offline = ComparableProblem.build(truth_positions, truth_health, tasks)
    oracle = hungarian_comparable(offline)
    oracle_pairs = sorted((member, task_id) for member, a in oracle["allocations"].items()
                          for task_id, _ in a)

    output = []
    for cohort in FILTERS:
        if cohort == "self_reports":
            accepted = set(reported_positions) & set(reported_health)
        else:
            field = ("age_gate_decisions" if cohort == "age_motion_gate"
                     else "witness_gate_decisions")
            accepted = {
                int(member) for member, details in snapshot[field].items()
                if details["action"] == "ACCEPT"
            }
        # Every comparator in the same cohort uses exactly the same
        # authenticated receiver snapshot and accepted membership mask.
        observed_problem = ComparableProblem.build(
            {i: reported_positions[i] for i in accepted if i in reported_positions},
            {i: reported_health[i] for i in accepted if i in reported_health},
            tasks, max_per_node=1)
        for method, result in compare_allocators(observed_problem,
                                                  methods=COMPARATORS).items():
            pairs = sorted((member, task_id) for member, values in
                           result["allocations"].items() for task_id, _ in values)
            ground_truth_ineligible = sum(
                truth_health[member].battery < 30 or
                truth_health[member].motor_health < 75 or
                truth_health[member].link_quality < 40
                for member, _ in pairs)
            # This offline distance score uses TRUE XYZ but is computed
            # *after* allocation. It never affects a comparator's decision.
            true_total_distance = math.fsum(
                math.dist(truth_positions[member], tasks[task_id])
                for member, task_id in pairs)
            true_utility_cost = math.fsum(
                math.dist(truth_positions[member], tasks[task_id]) +
                0.35*(100-truth_health[member].battery) +
                0.50*(100-truth_health[member].motor_health) +
                0.15*(100-truth_health[member].link_quality)
                for member, task_id in pairs)
            output.append({
                "scenario": fault_case["scenario"],
                "seed": fault_case["seed"],
                "nodes": fault_case["nodes"],
                "information_cohort": cohort,
                "optimizer": method,
                "source": "Step4_signed_authentication_receiver_snapshot",
                "task_count": len(tasks),
                "members_reported": len(reported_positions),
                "members_accepted": len(observed_problem.positions),
                "tasks_assigned": result["tasks_assigned"],
                "tasks_unassigned": len(result["unassigned"]),
                "pairs": [{"member": member, "task_id": task_id}
                          for member, task_id in pairs],
                "offline_hungarian_pairs": [{"member": member, "task_id": task_id}
                                           for member, task_id in oracle_pairs],
                "matches_offline_assignment": pairs == oracle_pairs,
                "ineligible_assignments_offline": ground_truth_ineligible,
                "reported_cost": result["objective_total_cost"],
                "offline_true_total_distance_m": true_total_distance,
                "offline_true_total_penalized_cost": true_utility_cost,
                "logical_bid_messages": result["logical_bid_messages"],
                "consensus_rounds": result["consensus_rounds"],
                "communication_model": result["communication_model"],
                "sensor_information_advantage": (
                    "idealized_peer_reports_possible" if
                    cohort == "strict_synthetic_witness_gate" else "none"),
                "real_hardware_evidence": False,
            })
    return output


def run_comparison_suite(*, sizes=(5, 10), trials=2, seed=2026,
                         scenarios=SCENARIOS, packet_loss=0.15) -> tuple[list[dict], list[dict]]:
    if not sizes or len(set(sizes)) != len(sizes) or any(not 4 <= n <= 50 for n in sizes):
        raise ValueError("Require distinct swarm sizes 4..50")
    if not 1 <= trials <= 20:
        raise ValueError("Step 5 diagnostic repeats must be 1..20")
    if not scenarios or len(set(scenarios)) != len(scenarios) or any(
            name not in SCENARIOS for name in scenarios):
        raise ValueError("Require distinct valid fault scenarios")
    if not 0 <= packet_loss < 1:
        raise ValueError("Invalid packet loss")
    sources, compared = [], []
    for n in sizes:
        for scenario_idx, scenario in enumerate(scenarios):
            for trial in range(trials):
                episode_seed = int(seed) + n*101 + scenario_idx*100003 + trial*1009
                fault_case = run_fault_case(FaultCase(
                    scenario=scenario, nodes=n, seed=episode_seed,
                    packet_loss=packet_loss if scenario == "packet_loss" else 0.))
                sources.append({
                    "scenario": scenario, "nodes": n, "trial": trial,
                    "seed": episode_seed,
                    "snapshot": fault_case["comparison_input"],
                    "offline_truth": fault_case["comparison_offline_truth"],
                    "signed_bootstrap": fault_case["signed_authenticated_bootstrap"],
                    "network": fault_case["network"],
                })
                compared.extend(compare_one_fault_case(fault_case))
    return sources, compared


def _git_sha() -> str:
    if os.getenv("GITHUB_SHA"):
        return str(os.environ["GITHUB_SHA"])
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL,
                                       timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def write_comparison(directory: Path, episodes: list[dict],
                     comparisons: list[dict]) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    for filename, records in (
        ("signed_episode_snapshots.json", episodes),
        ("paired_baseline_trials.json", comparisons),
    ):
        (directory / filename).write_text(
            json.dumps(records, sort_keys=True, indent=2, allow_nan=False)+"\n",
            encoding="utf-8",
        )
    columns = (
        "scenario", "nodes", "seed", "information_cohort", "optimizer",
        "task_count", "members_accepted", "tasks_assigned", "tasks_unassigned",
        "ineligible_assignments_offline", "matches_offline_assignment",
        "reported_cost", "offline_true_total_distance_m",
        "offline_true_total_penalized_cost", "logical_bid_messages",
        "consensus_rounds",
    )
    with (directory / "paired_baseline_metrics.csv").open(
            "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in comparisons:
            writer.writerow({col: row[col] for col in columns})
    files = ("signed_episode_snapshots.json", "paired_baseline_trials.json",
             "paired_baseline_metrics.csv")
    digests = {file: hashlib.sha256((directory/file).read_bytes()).hexdigest()
               for file in files}
    manifest = {
        "schema_version": 1,
        "source_revision": _git_sha(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "source_fault_episodes": len(episodes),
        "paired_comparator_rows": len(comparisons),
        "source_kind": "Step4_signed_fault_synthetic_diagnostics",
        "optimizers": list(COMPARATORS),
        "information_cohorts": list(FILTERS),
        "cbaa_single_assignment_only": True,
        "cbba_static_specialization_not_full_cbba": True,
        "offline_truth_never_in_optimizer_inputs": True,
        "independent_observation_is_idealized": True,
        "statistical_superiority_established": False,
        "hardware_experiment": False,
        "real_radio_messages_measured": False,
        "no_reuse_of_previous_supplementary_results": True,
        "sha256": digests,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[5, 10])
    parser.add_argument("--trials", type=int, default=2)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--packet-loss", type=float, default=0.15)
    parser.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    parser.add_argument("--out",default="experiment_outputs/consistency-gated-step5")
    args=parser.parse_args()
    episodes, trials = run_comparison_suite(
        sizes=tuple(args.sizes), trials=args.trials, seed=args.seed,
        scenarios=tuple(args.scenarios), packet_loss=args.packet_loss)
    manifest = write_comparison(Path(args.out), episodes, trials)
    print(json.dumps({
        "source_episodes": manifest["source_fault_episodes"],
        "paired_comparison_rows": manifest["paired_comparator_rows"],
        "optimizers": manifest["optimizers"],
        "information_cohorts": manifest["information_cohorts"],
        "sha256": manifest["sha256"],
        "out": args.out,
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
