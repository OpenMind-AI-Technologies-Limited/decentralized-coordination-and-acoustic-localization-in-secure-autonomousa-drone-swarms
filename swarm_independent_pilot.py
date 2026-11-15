"""Step 7 randomized, paired, cryptographically received UAV allocation pilot.

Every episode draws fresh ground-truth/observed state, attacks, tasks, network
drops and witness availability from an independent derived seed. Actual signed
AES-GCM/Ed25519 MeshNode heartbeat and quorum-vote reception is exercised at
the coordinator. Simulated true state is NEVER supplied to allocator methods:
it is used to synthesize separately signed observation claims and afterwards
by the offline evaluation oracle only.

This is synthetic exploratory evidence, not physical UAV safety validation,
trusted sensor attestation, a full CBBA comparison or confirmatory inference.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from typing import Mapping

from swarm_mesh import HealthReport, MeshNode, SwarmIdentity
from swarm_consistency_gate import ConsistencyPolicy, consistency_gated_allocate, sign_witness
from swarm_tasks import allocate_tasks

SCENARIOS = (
    "benign", "benign_noise", "stale_position", "signed_false_health",
    "signed_false_position", "malicious_witness",
    "colluding_witness", "mixed_loss",
)
METHODS = (
    "greedy_signed", "age_only", "motion_age", "witness_age",
    "full_opportunistic", "full_strict",
)
FLEET_SIZES = (5, 10, 20, 50)
PILOT_TRIALS = 30


class ManualClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _seed(root: int, n: int, scenario: str, index: int) -> int:
    payload = f"consistency-gated-step7-v1|{int(root)}|{n}|{scenario}|{index}"
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


def _clip(x: float) -> float:
    return max(0.0, min(100.0, float(x)))


def _health_noise(report: HealthReport, rng: random.Random, sigma: float) -> HealthReport:
    return HealthReport(
        _clip(report.battery + rng.gauss(0., sigma)),
        _clip(report.motor_health + rng.gauss(0., sigma)),
        _clip(report.link_quality + rng.gauss(0., sigma)),
    )


def _point_noise(point, rng: random.Random, sigma: float):
    return (point[0] + rng.gauss(0., sigma),
            point[1] + rng.gauss(0., sigma), point[2])


def _pairs(allocations: Mapping) -> list[tuple[int, str]]:
    return sorted((int(member), str(task))
                  for member, values in allocations.items()
                  for task, _target in values)


def _report_inputs(snapshot: dict, *, method: str) -> dict:
    """Take only coordinator-verified reports, never offline evaluation truth."""
    now = snapshot["now"]
    positions, health, seen_health, seen_pos, history = (
        snapshot["positions"], snapshot["health"],
        snapshot["health_seen"], snapshot["position_seen"], snapshot["previous"],
    )
    tasks, roster, epoch = snapshot["tasks"], snapshot["roster"], snapshot["epoch"]
    if method == "greedy_signed":
        return {"allocations": allocate_tasks(positions, health, tasks),
                "decisions": {}, "unassigned": []}
    with_motion = method in ("motion_age", "full_opportunistic", "full_strict")
    with_witness = method in ("witness_age", "full_opportunistic", "full_strict")
    policy = ConsistencyPolicy(
        max_health_age_s=2., max_position_age_s=2.,
        min_health_witnesses=2 if method == "full_strict" else 0,
    )
    return consistency_gated_allocate(
        positions=positions, health=health, health_seen_at=seen_health,
        position_seen_at=seen_pos, previous_positions=history if with_motion else {},
        now=now, tasks=tasks, roster=roster, epoch=epoch,
        policy=policy, witnesses=snapshot["witnesses"] if with_witness else {},
    )


def _generate_episode(*, n: int, scenario: str, seed: int,
                      witness_count: int = 2) -> tuple[dict, dict]:
    # Step 7's frozen interface (witness_count=2 and its original scenarios)
    # remains unchanged; Step 8 can explicitly opt into a broader stress
    # model and three registered witness claims per subject.
    extended = ("motion_jump", "quorum_partition")
    if (n not in FLEET_SIZES or scenario not in SCENARIOS + extended or
            not isinstance(witness_count,int) or isinstance(witness_count,bool) or
            not 1 <= witness_count < n):
        raise ValueError("Unsupported randomized pilot stratum")
    rng = random.Random(seed)
    clock = ManualClock()
    identities = {i: SwarmIdentity(i) for i in range(1, n + 1)}
    roster = {i: ident.public_bytes() for i, ident in identities.items()}
    shared_key = os.urandom(32)
    nodes = {i: MeshNode(ident, roster, shared_key, clock=clock,
                         heartbeat_timeout_s=12.0)
             for i, ident in identities.items()}
    coordinator = nodes[1]

    true_positions = {
        i: (rng.uniform(-110., 110.), rng.uniform(-110., 110.), 10.)
        for i in nodes
    }
    true_health = {
        i: HealthReport(
            rng.uniform(50., 98.), rng.uniform(82., 100.),
            rng.uniform(65., 100.))
        for i in nodes
    }
    task_count = rng.randint(2, min(6, n))
    tasks = {
        f"job-{j:02d}": (rng.uniform(-110., 110.),
                         rng.uniform(-110., 110.), 10.)
        for j in range(task_count)
    }
    target = rng.choice(list(range(2, n + 1)))
    task_anchor = tasks["job-00"]
    delay = rng.uniform(3.0, 9.0)
    sensor_sigma = 2.5 if scenario == "benign_noise" else 0.6
    loss_prob = 0.35 if scenario == "mixed_loss" else 0.05
    observed_health = {
        i: _health_noise(h, rng, 3.0 if scenario == "benign_noise" else 0.7)
        for i, h in true_health.items()
    }
    observed_positions = {
        i: _point_noise(p, rng, sensor_sigma)
        for i, p in true_positions.items()
    }

    if scenario in ("signed_false_health", "colluding_witness"):
        true_health[target] = HealthReport(
            rng.uniform(8., 25.), rng.uniform(45., 68.),
            rng.uniform(20., 35.))
        observed_health[target] = HealthReport(
            rng.uniform(90., 99.), rng.uniform(92., 100.),
            rng.uniform(88., 99.))
    if scenario in ("signed_false_position", "motion_jump"):
        # Source-signed plausible instant proximity to a randomly generated
        # task; no independent receiver measurement is promised.
        observed_positions[target] = (
            task_anchor[0] + rng.uniform(-3., 3.),
            task_anchor[1] + rng.uniform(-3., 3.), 10.)
    if scenario == "stale_position":
        # One prior authenticated position may differ from current truth by a
        # motion-compatible displacement over the randomized elapsed time.
        theta = rng.uniform(-math.pi, math.pi)
        displacement = rng.uniform(4., 15.) * delay
        observed_positions[target] = (
            true_positions[target][0] + displacement * math.cos(theta),
            true_positions[target][1] + displacement * math.sin(theta), 10.)

    # Establish the same authenticated coordinator and signed quorum
    # certificate used in the preceding source-level diagnostic work.
    for member in sorted(nodes):
        source = nodes[member]
        previous = (
            true_positions[member][0] + rng.uniform(-3., 3.),
            true_positions[member][1] + rng.uniform(-3., 3.), 10.
        )
        initially = observed_positions[member] if member == target and scenario in (
            "stale_position", "signed_false_position") else previous
        if scenario == "motion_jump" and member == target:
            # A signed previously-received XYZ sample 600 m away from the
            # new signed near-task report: physically implausible under
            # 25 m/s for the forthcoming 3–9 seconds of virtual time.
            initially = (observed_positions[member][0]+600.,
                         observed_positions[member][1],10.)
        packet = source.publish_health(observed_health[member], initially)
        if member != 1:
            coordinator.receive(packet)
    # Other signers vote with legitimate registered keys. No vote protocol or
    # certificate is fabricated outside MeshNode.
    coordinator.begin_election(candidate=1)
    for member in range(2, n + 1):
        packet = nodes[member].begin_election(candidate=1)
        coordinator.receive(packet)
    if coordinator.leader != 1 or coordinator.certificate is None:
        raise AssertionError("Authenticated quorum election failed")

    clock.now += (15. if scenario == "quorum_partition" else delay)
    packet_attempts = dropped_packets = verified_packets = 0
    for member in sorted(nodes):
        # Loss is imposed after an authenticated bootstrap, independently of
        # the policies being evaluated. Explicit omission retains old XYZ.
        lost = member != 1 and rng.random() < loss_prob
        if scenario == "quorum_partition" and member != 1:
            lost = True  # no fresh quorum 15 s after prior signed bootstrap
        if member == target and scenario == "stale_position":
            latest_xyz = None
        else:
            latest_xyz = observed_positions[member]
        if member == 1:
            nodes[member].publish_health(observed_health[member], latest_xyz)
        else:
            packet = nodes[member].publish_health(observed_health[member], latest_xyz)
            packet_attempts += 1
            if lost:
                dropped_packets += 1
                continue
            coordinator.receive(packet)  # AES-GCM + Ed25519 validation
            verified_packets += 1

    witness_by_subject = {}
    witness_claims = 0
    witness_missing = 0
    malicious_signers = set()
    for subject in sorted(nodes):
        reporters = rng.sample([i for i in nodes if i != subject], witness_count)
        evidence = []
        for k, reporter in enumerate(reporters):
            # Synthetic peer-observation generation uses oracle truth ONLY
            # here. The signed claim is then the sole witness input.
            claimed = _health_noise(true_health[subject], rng, 0.8)
            if subject == target and scenario == "malicious_witness" and k == 0:
                claimed = HealthReport(0., 0., 0.)
                malicious_signers.add(reporter)
            if subject == target and scenario == "colluding_witness" and (
                    witness_count == 2 or k < 2):
                claimed = observed_health[target]
                malicious_signers.add(reporter)
            # A witness can fail to provide evidence; missingness is
            # determined separately from allocation decisions.
            if rng.random() < (0.35 if scenario == "mixed_loss" else 0.05):
                witness_missing += 1
                continue
            evidence.append(sign_witness(
                identities[reporter], subject_id=subject,
                epoch=coordinator.epoch, observed_at=clock.now,
                health=claimed))
            witness_claims += 1
        witness_by_subject[subject] = evidence

    attacker_count = (1 if scenario in (
        "signed_false_health", "signed_false_position", "motion_jump",
        "stale_position", "colluding_witness") else 0)
    if scenario == "stale_position":
        # Honest sensor omission is NOT a Byzantine signer.
        attacker_count = 0
    attacker_count += len(malicious_signers)
    observations = {
        "now": clock.now,
        "positions": {
            i: coordinator.positions[i] for i in coordinator.health
            if i in coordinator.positions and
            0 <= clock.now - coordinator.health[i][1] <= coordinator.timeout_s
        },
        "health": {
            i: report for i, (report, seen) in coordinator.health.items()
            if 0 <= clock.now - seen <= coordinator.timeout_s
        },
        "health_seen": {i: seen for i, (_, seen) in coordinator.health.items()},
        "position_seen": dict(coordinator.positions_seen_at),
        "previous": dict(coordinator.previous_positions),
        "tasks": tasks, "roster": roster, "epoch": coordinator.epoch,
        "witnesses": witness_by_subject,
        "quorum_available": coordinator.has_fresh_quorum(),
        "leader_certified": bool(coordinator.certificate and
                                 coordinator.leader == 1),
    }
    oracle = {
        "positions": true_positions, "health": true_health,
        "target": target, "scenario": scenario, "seed": seed, "n": n,
        "compromised_count": attacker_count,
        "declared_fault_bound": (n - 1) // 3,
        "within_fault_bound": attacker_count <= (n - 1) // 3,
        "report_attempts": packet_attempts, "verified": verified_packets,
        "dropped": dropped_packets, "witness_claims": witness_claims,
        "missing_witnesses": witness_missing,
        "elapsed_s": delay,
    }
    return observations, oracle


def _evaluate(observation: dict, oracle: dict) -> tuple[dict, list[dict]]:
    """Isolate offline truth: only evaluation sees oracle truth data."""
    tasks = observation["tasks"]
    truth_positions, truth_health = oracle["positions"], oracle["health"]
    true_allocations = allocate_tasks(truth_positions, truth_health, tasks)
    true_assignments = _pairs(true_allocations)
    records = []
    details = {}
    for method in METHODS:
        if observation["quorum_available"] and observation["leader_certified"]:
            result = _report_inputs(observation, method=method)
            pairs = _pairs(result["allocations"])
            decisions = result["decisions"]
        else:
            pairs, decisions = [], {}
        violations = sum(
            (truth_health[member].battery < 30 or
             truth_health[member].motor_health < 75 or
             truth_health[member].link_quality < 40)
            for member, _task in pairs
        )
        true_distance = math.fsum(
            math.dist(truth_positions[member], tasks[task_id])
            for member, task_id in pairs)
        record = {
            "seed": oracle["seed"], "n": oracle["n"],
            "scenario": oracle["scenario"], "method": method,
            "tasks_requested": len(tasks), "tasks_assigned": len(pairs),
            "tasks_unassigned": len(tasks) - len(pairs),
            "any_truth_ineligible_assignment": int(violations > 0),
            "truth_ineligible_assignment_count": violations,
            "missing_assignment_vs_true_oracle": max(0, len(true_assignments) - len(pairs)),
            "owner_pair_mismatch_vs_true_oracle": pairs != true_assignments,
            "offline_true_travel_distance_m": true_distance,
            "quorum_available": observation["quorum_available"],
            "accepted_members": sum(v["action"] == "ACCEPT" for v in decisions.values())
                                if decisions else len(observation["positions"]),
            "evidence_request_members": sum(
                v["action"] == "REQUEST_FRESH_EVIDENCE" for v in decisions.values()),
            "rejected_members": sum(
                v["action"] == "REJECT" for v in decisions.values()),
            "assignment_pairs": [
                {"member": member, "task_id": task_id} for member, task_id in pairs
            ],
            "simulated_only": True,
        }
        records.append(record)
        details[method] = {
            "assignees": record["assignment_pairs"],
            "decision_reasons": {str(k): v["reason"] for k, v in decisions.items()},
        }
    source_row = {
        "seed": oracle["seed"], "n": oracle["n"],
        "scenario": oracle["scenario"], "episode_unit": True,
        "num_tasks": len(tasks), "target_member": oracle["target"],
        "compromised_count": oracle["compromised_count"],
        "declared_fault_bound": oracle["declared_fault_bound"],
        "within_fault_bound": oracle["within_fault_bound"],
        "authenticated_verified_heartbeats": oracle["verified"],
        "injected_dropped_heartbeats": oracle["dropped"],
        "signed_witness_claims_available": oracle["witness_claims"],
        "missing_witness_claims": oracle["missing_witnesses"],
        "quorum_available": observation["quorum_available"],
        "elapsed_virtual_s": oracle["elapsed_s"],
        "observed_positions": {str(i): list(p) for i, p in
                               observation["positions"].items()},
        "observed_health": {str(i): h.to_dict() for i, h in
                            observation["health"].items()},
        "health_received_at": {str(i): t for i, t in
                               observation["health_seen"].items()},
        "position_received_at": {str(i): t for i, t in
                                 observation["position_seen"].items()},
        "tasks": {name: list(t) for name, t in tasks.items()},
        "offline_truth": {
            "positions": {str(i): list(p) for i, p in truth_positions.items()},
            "health": {str(i): h.to_dict() for i, h in truth_health.items()},
        },
        "methods": details,
        "hardware_sensors": False,
    }
    return source_row, records


def run_episode(*, n: int, scenario: str, seed: int) -> tuple[dict, list[dict]]:
    obs, true_state = _generate_episode(n=n, scenario=scenario, seed=seed)
    return _evaluate(obs, true_state)


def run_pilot(*, sizes=FLEET_SIZES, trials=PILOT_TRIALS,
              root_seed=2026, scenarios=SCENARIOS) -> tuple[list[dict], list[dict]]:
    if (not sizes or len(set(sizes)) != len(sizes) or
            any(n not in FLEET_SIZES for n in sizes)):
        raise ValueError("Invalid fleet sizes")
    if (not scenarios or len(set(scenarios)) != len(scenarios) or
            any(s not in SCENARIOS for s in scenarios)):
        raise ValueError("Invalid fault scenario list")
    if not isinstance(trials, int) or not 1 <= trials <= 100:
        raise ValueError("Trials must be in 1..100")
    sources, rows = [], []
    for n in sizes:
        for scenario in scenarios:
            for iteration in range(trials):
                seed = _seed(root_seed, n, scenario, iteration)
                source, compared = run_episode(n=n, scenario=scenario, seed=seed)
                source["trial"] = iteration
                sources.append(source)
                for row in compared:
                    row["trial"] = iteration
                rows.extend(compared)
    if len({(r["n"],r["scenario"],r["seed"]) for r in sources}) != len(sources):
        raise AssertionError("Independent episode seed collision")
    return sources, rows


def _paired_ci(pairs: list[tuple[int, int]], *, seed: int, draws=500) -> tuple[float,float,float]:
    if not pairs:
        raise ValueError("Missing paired observations")
    values = [int(new) - int(old) for old, new in pairs]
    point = statistics.fmean(values)
    rng = random.Random(seed)
    distribution = sorted(statistics.fmean(values[rng.randrange(len(values))]
                                           for _ in values)
                          for _ in range(draws))
    lo = distribution[int((draws - 1)*0.025)]
    hi = distribution[int((draws - 1)*0.975)]
    return point, lo, hi


def summarize_pilot(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[int,str], dict[int,dict[str,dict]]] = {}
    for row in rows:
        key = (row["n"],row["scenario"])
        per_seed = grouped.setdefault(key,{}).setdefault(row["seed"],{})
        if row["method"] in per_seed:
            raise ValueError("Duplicate method in pilot paired unit")
        per_seed[row["method"]] = row
    result=[]
    for (n,scenario), episodes in sorted(grouped.items()):
        if any(set(values) != set(METHODS) for values in episodes.values()):
            raise ValueError("Incomplete paired episode")
        ordered = [episodes[k] for k in sorted(episodes)]
        raw = [case["greedy_signed"] for case in ordered]
        strict = [case["full_strict"] for case in ordered]
        point,lo,hi = _paired_ci([
            (a["any_truth_ineligible_assignment"],
             b["any_truth_ineligible_assignment"])
            for a,b in zip(raw,strict)
        ],seed=_seed(2027,n,scenario,0))
        for method in METHODS:
            observations=[case[method] for case in ordered]
            result.append({
                "n":n,"scenario":scenario,"method":method,
                "episodes":len(observations),
                "harmful_episodes":sum(x["any_truth_ineligible_assignment"]
                                       for x in observations),
                "harmful_episode_rate":statistics.fmean(
                    x["any_truth_ineligible_assignment"] for x in observations),
                "mean_tasks_assigned":statistics.fmean(
                    x["tasks_assigned"] for x in observations),
                "mean_tasks_unassigned":statistics.fmean(
                    x["tasks_unassigned"] for x in observations),
                "mean_missing_vs_oracle":statistics.fmean(
                    x["missing_assignment_vs_true_oracle"] for x in observations),
                "strict_minus_greedy_harm_rate_delta":point,
                "exploratory_bootstrap95_low":lo,
                "exploratory_bootstrap95_high":hi,
                "statistical_superiority_claim":False,
            })
    return result


def _revision() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"],
                                       text=True,stderr=subprocess.DEVNULL,
                                       timeout=3).strip()
    except (OSError,subprocess.SubprocessError):
        return "unavailable"


def write_pilot(directory: Path, sources: list[dict],
                paired: list[dict], summaries: list[dict]) -> dict:
    directory.mkdir(parents=True,exist_ok=True)
    for file,records in (
        ("randomized_episodes.json",sources),
        ("paired_methods.json",paired),
        ("exploratory_stratum_summaries.json",summaries),
    ):
        (directory/file).write_text(
            json.dumps(records,indent=2,sort_keys=True,allow_nan=False)+"\n",
            encoding="utf-8")
    columns=(
        "n","scenario","seed","trial","method","tasks_requested",
        "tasks_assigned","tasks_unassigned",
        "any_truth_ineligible_assignment",
        "truth_ineligible_assignment_count",
        "missing_assignment_vs_true_oracle",
        "owner_pair_mismatch_vs_true_oracle",
        "offline_true_travel_distance_m","quorum_available",
        "accepted_members","evidence_request_members","rejected_members",
    )
    with (directory/"paired_method_metrics.csv").open(
            "w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        for row in paired:
            writer.writerow({k:row[k] for k in columns})
    output_files=(
        "randomized_episodes.json","paired_methods.json",
        "exploratory_stratum_summaries.json","paired_method_metrics.csv",
    )
    hashes={name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
            for name in output_files}
    manifest={
        "schema_version":1,"source_revision":_revision(),
        "python":sys.version.split()[0],"platform":platform.platform(),
        "design_document":"Docs/CONSISTENCY_GATED_STEP7_RANDOMIZED_PILOT_PROTOCOL.md",
        "scope":"synthetic_exploratory_randomized_paired_pilot",
        "source_episode_count":len(sources),
        "paired_method_rows":len(paired),
        "stratum_summary_rows":len(summaries),
        "strata":sorted({f'{x["n"]}/{x["scenario"]}' for x in sources}),
        "methods":list(METHODS),
        "sha256":hashes,
        "source_cryptography":"MeshNode signed encrypted heartbeat + signed quorum vote",
        "independent_experiment_unit":"randomized_episode",
        "policies_with_equal_available_input":True,
        "policies_with_equal_used_information":False,
        "peer_sensors_are_idealized":True,
        "full_published_cbba_not_evaluated":True,
        "confirmatory_holdout_completed":False,
        "multiplicity_adjusted_significance_test":False,
        "physical_flight":False,
        "real_radio_link":False,
        "real_sensor_observations":False,
        "publication_scale_superiority_established":False,
        "prior_378_rows_reused":False,
    }
    (directory/"manifest.json").write_text(
        json.dumps(manifest,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return manifest


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sizes",nargs="+",type=int,default=list(FLEET_SIZES))
    p.add_argument("--trials",type=int,default=PILOT_TRIALS)
    p.add_argument("--seed",type=int,default=2026)
    p.add_argument("--scenarios",nargs="+",default=list(SCENARIOS))
    p.add_argument("--out",default="experiment_outputs/consistency-gated-step7-pilot")
    args=p.parse_args()
    episodes,paired=run_pilot(
        sizes=tuple(args.sizes),trials=args.trials,
        root_seed=args.seed,scenarios=tuple(args.scenarios))
    summary=summarize_pilot(paired)
    m=write_pilot(Path(args.out),episodes,paired,summary)
    print(json.dumps({
        "source_episode_count":m["source_episode_count"],
        "paired_method_rows":m["paired_method_rows"],
        "stratum_summary_rows":m["stratum_summary_rows"],
        "sha256":m["sha256"],"out":args.out,
    },sort_keys=True,indent=2))


if __name__=="__main__":
    main()
