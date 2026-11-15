"""Step 8 independently sampled paired robust-vs-veto witness diagnostic study.

The frozen Step 8 protocol declares dev root 82026 and unseen heldout root
82027, 4 fleet sizes and 9 fault scenarios. Source reports pass real
MeshNode signed+encrypted verification. Truth is only for separately
modeled witness generation and post-decision evaluation. Neither strategy
ever receives it in its allocation inputs.
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

from swarm_consistency_gate import ConsistencyPolicy, consistency_gated_allocate
from swarm_independent_pilot import _generate_episode, _pairs, FLEET_SIZES
from swarm_robust_witness_gate import RobustWitnessPolicy, robust_witness_allocate
from swarm_tasks import allocate_tasks

SCENARIOS = (
    "benign", "benign_noise", "signed_false_health", "signed_false_position",
    "malicious_witness", "colluding_witness", "motion_jump",
    "quorum_partition", "mixed_loss",
)
POLICIES = (
    "greedy_signed", "age_only", "motion_age", "veto_3",
    "median_3_age", "median_3_motion",
)
DEV_ROOT = 82026
HOLDOUT_ROOT = 82027
BOOTSTRAP_ROOT = 82028


def episode_seed(root: int, n: int, scenario: str, index: int) -> int:
    text = f"swarm-step8-v1|{root}|{n}|{scenario}|{index}"
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def _run_allocation(observation: dict, method: str):
    if method not in POLICIES:
        raise ValueError("Unknown allocation policy")
    if not observation["quorum_available"] or not observation["leader_certified"]:
        return {"allocations":{}, "decisions":{}, "unassigned":sorted(observation["tasks"])}
    common = {
        "positions":observation["positions"], "health":observation["health"],
        "health_seen_at":observation["health_seen"],
        "position_seen_at":observation["position_seen"],
        "now":observation["now"],"tasks":observation["tasks"],
        "roster":observation["roster"],"epoch":observation["epoch"],
    }
    if method == "greedy_signed":
        return {
            "allocations":allocate_tasks(
                observation["positions"],observation["health"],observation["tasks"]),
            "decisions":{},
        }
    if method == "age_only":
        return consistency_gated_allocate(
            **common, policy=ConsistencyPolicy(), previous_positions={},
            witnesses={},
        )
    if method == "motion_age":
        return consistency_gated_allocate(
            **common, policy=ConsistencyPolicy(),
            previous_positions=observation["previous"], witnesses={},
        )
    if method == "veto_3":
        return consistency_gated_allocate(
            **common,policy=ConsistencyPolicy(min_health_witnesses=3),
            previous_positions={},witnesses=observation["witnesses"],
        )
    robust_policy=RobustWitnessPolicy(
        health_witness_quorum=3,assumed_faulty_witnesses=1)
    return robust_witness_allocate(
        **common,witnesses=observation["witnesses"],
        previous_positions=(observation["previous"] if
                            method=="median_3_motion" else {}),
        policy=robust_policy,
    )


def run_case(*, n: int, scenario: str, seed: int) -> tuple[dict, list[dict]]:
    observation,truth=_generate_episode(
        n=n,scenario=scenario,seed=seed,witness_count=3)
    # IMPORTANT: allocate before touching truth; a regression test mutates
    # oracle values to demonstrate that assignment pairs do not change.
    predicted={method:_run_allocation(observation,method) for method in POLICIES}
    tasks=observation["tasks"]
    health=truth["health"]
    positions=truth["positions"]
    truth_feasible={
        member:report.battery>=30. and report.motor_health>=75. and
               report.link_quality>=40.
        for member,report in health.items()
    }
    records=[]
    source={
        "seed":seed,"n":n,"scenario":scenario,
        "quorum_available":observation["quorum_available"],
        "certified_leader":observation["leader_certified"],
        "num_tasks":len(tasks),
        "target_member":truth["target"],
        "compromised_count":truth["compromised_count"],
        "declared_fault_bound":truth["declared_fault_bound"],
        "within_fault_bound":truth["within_fault_bound"],
        "verified_heartbeat_packets":truth["verified"],
        "dropped_heartbeat_packets":truth["dropped"],
        "available_signed_witnesses":truth["witness_claims"],
        "missing_witnesses":truth["missing_witnesses"],
        "receiver_snapshot":{
            "positions":{str(k):list(v) for k,v in
                         observation["positions"].items()},
            "health":{str(k):v.to_dict() for k,v in
                      observation["health"].items()},
            "health_received_at":{str(k):v for k,v in
                                  observation["health_seen"].items()},
            "position_received_at":{str(k):v for k,v in
                                    observation["position_seen"].items()},
            "tasks":{k:list(v) for k,v in tasks.items()},
        },
        "offline_evaluation_truth":{
            "positions":{str(k):list(v) for k,v in positions.items()},
            "health":{str(k):v.to_dict() for k,v in health.items()},
        },
        "signed_witnesses_model":"idealized_peer_claims_with_authentic_signatures",
        "real_hardware":False,
        "real_radio_latency":False,
    }
    for method,result in predicted.items():
        assignments=_pairs(result["allocations"])
        decisions=result["decisions"]
        bad=sum(not truth_feasible[member] for member,_ in assignments)
        distance=math.fsum(
            math.dist(positions[member],tasks[task_id])
            for member,task_id in assignments)
        false_rejection_count=sum(
            verdict["action"]=="REJECT" and truth_feasible.get(member,False)
            for member,verdict in decisions.items())
        records.append({
            "seed":seed, "n":n, "scenario":scenario,"method":method,
            "tasks_requested":len(tasks),"tasks_assigned":len(assignments),
            "tasks_unassigned":len(tasks)-len(assignments),
            "task_coverage":len(assignments)/len(tasks),
            "any_truth_ineligible_assignment":int(bad>0),
            "truth_ineligible_assignment_count":bad,
            "false_rejected_healthy_members":false_rejection_count,
            "offline_true_travel_distance_m":distance,
            "quorum_available":observation["quorum_available"],
            "rejected_members":sum(x["action"]=="REJECT" for x in decisions.values()),
            "missing_evidence_members":sum(
                x["action"]=="REQUEST_FRESH_EVIDENCE"
                for x in decisions.values()),
            "assignment_pairs":[
                {"member":member,"task_id":task_id} for member,task_id in assignments
            ],
            "decision_reasons":{str(member):x["reason"]
                                for member,x in decisions.items()},
            "synthetic_only":True,
        })
    return source,records


def run_study(*, sizes=FLEET_SIZES, scenarios=SCENARIOS,
              trials: int = 8, root: int = DEV_ROOT
              ) -> tuple[list[dict],list[dict]]:
    if (not sizes or len(set(sizes))!=len(sizes) or
            any(n not in FLEET_SIZES for n in sizes)):
        raise ValueError("Invalid fleet sizes")
    if (not scenarios or len(set(scenarios))!=len(scenarios) or
            any(x not in SCENARIOS for x in scenarios)):
        raise ValueError("Invalid scenario list")
    if not isinstance(trials,int) or isinstance(trials,bool) or not 1<=trials<=100:
        raise ValueError("Trials must be 1..100")
    sources,rows=[],[]
    for n in sizes:
        for scenario in scenarios:
            for trial in range(trials):
                seed=episode_seed(root,n,scenario,trial)
                source,paired=run_case(n=n,scenario=scenario,seed=seed)
                source["trial"]=trial
                for row in paired:
                    row["trial"]=trial
                sources.append(source)
                rows.extend(paired)
    if len({(x["n"],x["scenario"],x["seed"]) for x in sources})!=len(sources):
        raise AssertionError("Episode seed collision")
    return sources,rows


def _bootstrap_contrast(pairs, key: str, *, seed: int, samples=500):
    differences=[
        float(new[key])-float(old[key])
        for old,new in pairs
    ]
    rng=random.Random(seed)
    point=statistics.fmean(differences)
    ranked=sorted(
        statistics.fmean(differences[rng.randrange(len(differences))]
                          for _ in differences)
        for _ in range(samples))
    return {
        "difference":point,
        "percentile_95_low":ranked[int((samples-1)*0.025)],
        "percentile_95_high":ranked[int((samples-1)*0.975)],
    }


def summarize(rows: list[dict]) -> list[dict]:
    episodes={}
    for row in rows:
        case=episodes.setdefault((row["n"],row["scenario"],row["seed"]),{})
        if row["method"] in case:
            raise ValueError("Duplicate policy within paired episode")
        case[row["method"]]=row
    grouped={}
    for (n,scenario,seed),case in episodes.items():
        if set(case)!=set(POLICIES):
            raise ValueError("Incomplete paired method record")
        grouped.setdefault((n,scenario),[]).append((seed,case))
    summaries=[]
    for (n,scenario),collection in sorted(grouped.items()):
        episodes_ordered=[case for _,case in sorted(collection)]
        reference=episodes_ordered[0]
        paired_median_veto=[(x["veto_3"],x["median_3_motion"])
                            for x in episodes_ordered]
        paired_median_age=[(x["age_only"],x["median_3_motion"])
                           for x in episodes_ordered]
        contrasts={}
        for name,pairs in (("median_minus_veto",paired_median_veto),
                           ("median_minus_age",paired_median_age)):
            for metric in ("any_truth_ineligible_assignment","task_coverage"):
                contrasts[name+"_"+metric]=_bootstrap_contrast(
                    pairs,metric,seed=episode_seed(
                        BOOTSTRAP_ROOT,n,scenario,
                        0 if name=="median_minus_veto" else 1) +
                        (0 if metric=="any_truth_ineligible_assignment" else 2))
        for method in POLICIES:
            records=[ep[method] for ep in episodes_ordered]
            summaries.append({
                "n":n,"scenario":scenario,"method":method,
                "episodes":len(records),
                "harmful_episodes":sum(x["any_truth_ineligible_assignment"]
                                       for x in records),
                "harmful_episode_rate":statistics.fmean(
                    x["any_truth_ineligible_assignment"] for x in records),
                "mean_task_coverage":statistics.fmean(
                    x["task_coverage"] for x in records),
                "mean_tasks_assigned":statistics.fmean(
                    x["tasks_assigned"] for x in records),
                "mean_false_rejected_healthy_members":statistics.fmean(
                    x["false_rejected_healthy_members"] for x in records),
                "paired_exploratory_contrasts":contrasts,
                "confirmatory_external_validity":False,
            })
    return summaries


def _commit() -> str:
    if os.getenv("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"],
                                       text=True,stderr=subprocess.DEVNULL,
                                       timeout=3).strip()
    except (OSError,subprocess.SubprocessError):
        return "unavailable"


def write_evidence(folder:Path,sources:list[dict],rows:list[dict],
                   summaries:list[dict],*,sample_type:str,root:int)->dict:
    if sample_type not in ("development","heldout"):
        raise ValueError("Unknown sample type")
    folder.mkdir(parents=True,exist_ok=True)
    files={
        "episodes.json":sources,"paired_policies.json":rows,
        "stratum_summaries.json":summaries,
    }
    for file,data in files.items():
        (folder/file).write_text(
            json.dumps(data,sort_keys=True,indent=2,allow_nan=False)+"\n",
            encoding="utf-8")
    fields=(
        "n","scenario","seed","trial","method","tasks_requested",
        "tasks_assigned","tasks_unassigned","task_coverage",
        "any_truth_ineligible_assignment","truth_ineligible_assignment_count",
        "false_rejected_healthy_members","offline_true_travel_distance_m",
        "quorum_available","rejected_members","missing_evidence_members",
    )
    with (folder/"paired_metrics.csv").open("w",newline="",encoding="utf-8") as h:
        writer=csv.DictWriter(h,fieldnames=fields)
        writer.writeheader()
        for record in rows:
            writer.writerow({key:record[key] for key in fields})
    hashes={name:hashlib.sha256((folder/name).read_bytes()).hexdigest()
            for name in ("episodes.json","paired_policies.json",
                         "stratum_summaries.json","paired_metrics.csv")}
    m={
        "schema_version":1,"sample_type":sample_type,"root_seed":root,
        "source_revision":_commit(),"platform":platform.platform(),
        "python":sys.version.split()[0],
        "episodes":len(sources),"paired_rows":len(rows),
        "summary_rows":len(summaries),
        "fleet_sizes":sorted({x["n"] for x in sources}),
        "conditions":sorted({x["scenario"] for x in sources}),
        "methods":list(POLICIES),"sha256":hashes,
        "truth_separate_from_allocator":True,
        "independent_signatures_authenticated":True,
        "witnesses_are_synthetic_not_hardware":True,
        "single_fault_median_assumption_tested":True,
        "two_colluding_reporters_can_defeat_median":True,
        "full_cbba_comparison_completed":False,
        "external_preregistration":False,
        "physical_flight":False,
        "real_radio_link":False,
        "scientific_novelty_proven":False,
        "prior_step7_pilot_mixed_into_heldout":False,
    }
    (folder/"manifest.json").write_text(
        json.dumps(m,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return m


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sample",choices=("development","heldout"),
                   default="development")
    p.add_argument("--sizes",nargs="+",type=int,default=list(FLEET_SIZES))
    p.add_argument("--trials",type=int,default=None)
    p.add_argument("--seed",type=int,default=None)
    p.add_argument("--scenarios",nargs="+",default=list(SCENARIOS))
    p.add_argument("--out",default="experiment_outputs/consistency-gated-step8")
    args=p.parse_args()
    expected_seed=DEV_ROOT if args.sample=="development" else HOLDOUT_ROOT
    expected_trials=8 if args.sample=="development" else 20
    if args.trials is not None and args.trials != expected_trials:
        raise ValueError("Frozen Step 8 trial count mismatch")
    if args.seed is not None and args.seed != expected_seed:
        raise ValueError("Frozen Step 8 root seed mismatch")
    sources,rows=run_study(
        sizes=tuple(args.sizes),scenarios=tuple(args.scenarios),
        trials=expected_trials,root=expected_seed)
    summaries=summarize(rows)
    manifest=write_evidence(
        Path(args.out),sources,rows,summaries,
        sample_type=args.sample,root=expected_seed)
    print(json.dumps({
        "sample":args.sample,"episodes":manifest["episodes"],
        "paired_rows":manifest["paired_rows"],
        "summary_rows":manifest["summary_rows"],
        "sha256":manifest["sha256"],"out":args.out,
    },sort_keys=True,indent=2))


if __name__=="__main__":
    main()
