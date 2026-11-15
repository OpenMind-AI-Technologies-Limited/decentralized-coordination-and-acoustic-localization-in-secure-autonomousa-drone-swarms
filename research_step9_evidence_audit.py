"""Step 9 independent, fail-closed scientific-evidence integrity audit.

Audits ORIGINAL generated Step 8 development/heldout directories without
rerunning the experiment or trusting its already-computed result columns.
Reconstructs assignment feasibility and true-space travel distance from each
episode's offline truth, validates paired units and exact stratum summaries,
and reports balanced-scenario safety–availability trade-offs. Does NOT prove
Ed25519 envelopes when those envelopes were not archived.

Usage:
 python research_step9_evidence_audit.py \
    --development experiment_outputs/consistency-gated-step8/development \
    --heldout experiment_outputs/consistency-gated-step8/heldout \
    --out experiment_outputs/consistency-gated-step9-audit

No hardware or journal-level novelty claims are made.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import fmean
import sys

FLEETS = (5, 10, 20, 50)
SCENARIOS = (
    "benign", "benign_noise", "signed_false_health", "signed_false_position",
    "malicious_witness", "colluding_witness", "motion_jump",
    "quorum_partition", "mixed_loss",
)
METHODS = (
    "greedy_signed", "age_only", "motion_age", "veto_3",
    "median_3_age", "median_3_motion",
)
DATA_FILES = (
    "episodes.json", "paired_policies.json",
    "stratum_summaries.json", "paired_metrics.csv",
)
CSV_FIELDS = (
    "n", "scenario", "seed", "trial", "method", "tasks_requested",
    "tasks_assigned", "tasks_unassigned", "task_coverage",
    "any_truth_ineligible_assignment", "truth_ineligible_assignment_count",
    "false_rejected_healthy_members", "offline_true_travel_distance_m",
    "quorum_available", "rejected_members", "missing_evidence_members",
)


class EvidenceAuditError(ValueError):
    """Any mismatch must block CI and any claim of verified evidence."""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceAuditError(message)


def seed_for(root: int, size: int, scenario: str, index: int) -> int:
    # Independently rederive the frozen Step 8 SHA-256 sample assignment.
    label = f"swarm-step8-v1|{root}|{size}|{scenario}|{index}"
    return int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], "big")


def source_json(folder: Path, filename: str):
    with (folder / filename).open(encoding="utf-8") as stream:
        return json.load(stream)


def close_number(observed, expected, *, label: str) -> None:
    check(math.isfinite(float(observed)) and
          math.isclose(float(observed), float(expected),
                       rel_tol=1e-10, abs_tol=1e-8),
          f"Numerical mismatch: {label} ({observed} != {expected})")


def audit_dir(folder: Path, *, sample_type: str, root: int,
              trials: int) -> dict:
    """Full-trace check using independent metric arithmetic.

    Do not count policy rows as independent trials. These are repeated
    decisions on the same random episode, with paired method assignment.
    """
    check(sample_type in ("development", "heldout"), "Invalid sample type")
    manifest = source_json(folder, "manifest.json")
    check(manifest["sample_type"] == sample_type, "Mismatched sample type")
    check(manifest["root_seed"] == root, "Wrong frozen root")
    check(manifest["fleet_sizes"] == list(FLEETS), "Fleet size altered")
    check(set(manifest["conditions"]) == set(SCENARIOS), "Scenario changed")
    check(manifest["methods"] == list(METHODS), "Method comparison changed")
    check(manifest["external_preregistration"] is False and
          manifest["physical_flight"] is False and
          manifest["real_radio_link"] is False and
          manifest["scientific_novelty_proven"] is False and
          manifest["full_cbba_comparison_completed"] is False,
          "Overclaimed methodological provenance")
    check(set(manifest["sha256"]) == set(DATA_FILES), "Unexpected archive members")
    for name, expected_hash in manifest["sha256"].items():
        actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
        check(actual == expected_hash, "SHA-256 mismatch: " + name)

    sources = source_json(folder, "episodes.json")
    rows = source_json(folder, "paired_policies.json")
    summaries = source_json(folder, "stratum_summaries.json")
    expected_count = len(FLEETS) * len(SCENARIOS) * trials
    check(manifest["episodes"] == len(sources) == expected_count,
          "Incomplete randomized episode inventory")
    check(manifest["paired_rows"] == len(rows) == expected_count*len(METHODS),
          "Incomplete paired policy rows")
    check(manifest["summary_rows"] == len(summaries) ==
          len(FLEETS)*len(SCENARIOS)*len(METHODS),
          "Incomplete stratum summaries")
    source_keys = {}
    for item in sources:
        n, scenario, iteration = item["n"], item["scenario"], item["trial"]
        check(n in FLEETS and scenario in SCENARIOS and
              isinstance(iteration, int) and 0 <= iteration < trials,
              "Unknown source stratum/trial")
        expected_seed = seed_for(root, n, scenario, iteration)
        check(item["seed"] == expected_seed, "Episode seed not frozen SHA-256")
        key = (n, scenario, expected_seed)
        check(key not in source_keys, "Repeated episode source")
        check(item["num_tasks"] == len(item["receiver_snapshot"]["tasks"]) > 0,
              "Missing requested tasks")
        check(item["within_fault_bound"] ==
              (item["compromised_count"] <= (n-1)//3),
              "Incorrect signed-witness fault-budget label")
        check(item["declared_fault_bound"] == (n-1)//3,
              "Incorrect declared quorum fault bound")
        check(item["certified_leader"] is True,
              "No recorded signed leader certification")
        source_keys[key] = item
    check(len(source_keys) == expected_count,
          "Duplicate, missing or altered episode seeds")
    check(set((x["n"], x["scenario"]) for x in sources) ==
          {(n, s) for n in FLEETS for s in SCENARIOS},
          "Missing fleet/scenario combinations")
    check(all(sum(item["n"] == n and item["scenario"] == scenario
                  for item in sources) == trials
              for n in FLEETS for scenario in SCENARIOS),
          "Unequal trial counts across frozen strata")
    # Conservative rule: each paired policy must be present once for every
    # episode regardless of evidence availability or malicious claims.
    pairing = defaultdict(dict)
    for row in rows:
        key = (row["n"], row["scenario"], row["seed"])
        check(key in source_keys, "Unlinked policy result")
        source = source_keys[key]
        check(row["trial"] == source["trial"], "Wrong paired trial index")
        method = row["method"]
        check(method in METHODS, "Unknown policy")
        check(method not in pairing[key], "Duplicate policy on one episode")
        check(row["synthetic_only"] is True, "Hardware claim in software pilot")
        check(row["quorum_available"] == source["quorum_available"],
              "Policy-specific quorum availability mismatch")
        check(row["tasks_requested"] == source["num_tasks"],
              "Different task information budget")
        assigned = row["assignment_pairs"]
        check(isinstance(assigned, list) and
              len(assigned) == row["tasks_assigned"], "Assignment count mismatch")
        check(row["tasks_unassigned"] == row["tasks_requested"] - len(assigned),
              "Inconsistent task coverage denominator")
        close_number(row["task_coverage"],
                     len(assigned) / row["tasks_requested"],
                     label="task coverage")
        truth = source["offline_evaluation_truth"]
        reported = source["receiver_snapshot"]
        members, jobs = set(), set()
        ineligible = 0
        true_distance = 0.0
        for assignment in assigned:
            member, job = str(assignment["member"]), assignment["task_id"]
            check(member not in members and job not in jobs,
                  "Duplicate job or owner within one task assignment")
            members.add(member)
            jobs.add(job)
            check(member in truth["health"] and member in truth["positions"],
                  "Missing ground-truth member")
            check(member in reported["health"] and
                  member in reported["positions"],
                  "Assignment uses unobserved member")
            check(job in reported["tasks"], "Assignment to unknown task")
            health = truth["health"][member]
            ineligible += int(
                health["battery"] < 30 or
                health["motor_health"] < 75 or
                health["link_quality"] < 40
            )
            true_distance += math.dist(
                truth["positions"][member], reported["tasks"][job])
        check(row["truth_ineligible_assignment_count"] == ineligible and
              row["any_truth_ineligible_assignment"] == int(ineligible > 0),
              "Ground-truth ineligible assignment label is inaccurate")
        close_number(row["offline_true_travel_distance_m"],
                     true_distance, label="offline true travel distance")
        if not source["quorum_available"]:
            check(len(assigned) == 0, "Assignment without fresh quorum")
        check(0 <= row["rejected_members"] <= source["n"] and
              0 <= row["missing_evidence_members"] <= source["n"],
              "Invalid gate diagnostic counts")
        pairing[key][method] = row
    check(len(pairing) == expected_count and
          all(set(case) == set(METHODS) for case in pairing.values()),
          "Missing policy in at least one independent episode")

    # Verify the CSV against JSON, including the exact per-row policy order.
    with (folder / "paired_metrics.csv").open(
            encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        check(tuple(reader.fieldnames or ()) == CSV_FIELDS,
              "Published CSV columns altered")
        table = list(reader)
    check(len(table) == len(rows), "CSV missing or extra policy records")
    for idx, (entry, record) in enumerate(zip(table, rows)):
        check(all(entry[name] == str(record[name]) for name in CSV_FIELDS),
              f"CSV/JSON mismatch at row {idx}")

    # Recalculate every reported stratum descriptive rate from raw rows.
    bucket = defaultdict(list)
    for row in rows:
        bucket[row["n"], row["scenario"], row["method"]].append(row)
    seen_summaries = set()
    for item in summaries:
        key = item["n"], item["scenario"], item["method"]
        check(key not in seen_summaries and key in bucket,
              "Repeated or unknown stratum summary")
        seen_summaries.add(key)
        group = bucket[key]
        check(item["episodes"] == len(group) == trials,
              "Incorrect descriptive summary denominator")
        bad_episodes = sum(x["any_truth_ineligible_assignment"] for x in group)
        check(item["harmful_episodes"] == bad_episodes,
              "Incorrect descriptive harmful incident count")
        for name, expected in (
            ("harmful_episode_rate", bad_episodes/trials),
            ("mean_task_coverage", fmean(x["task_coverage"] for x in group)),
            ("mean_tasks_assigned", fmean(x["tasks_assigned"] for x in group)),
            ("mean_false_rejected_healthy_members",
             fmean(x["false_rejected_healthy_members"] for x in group)),
        ):
            close_number(item[name], expected, label=name)
        check(item["confirmatory_external_validity"] is False,
              "Unsupported generalizability claim")
        # Independently recompute the archived 500-resample paired
        # percentile contrasts. Only the same (n, scenario, seed) is an
        # independent unit; never bootstrap six policies as six trials.
        cohort = [pairing[(n, scenario, seed)]
                  for n, scenario, seed in sorted(pairing)
                  if n == item["n"] and scenario == item["scenario"]]
        archived = item["paired_exploratory_contrasts"]
        check(len(archived) == 4, "Missing original paired CI effects")
        for label, baseline, offset in (
            ("median_minus_veto", "veto_3", 0),
            ("median_minus_age", "age_only", 1),
        ):
            for metric, effect_offset in (
                ("any_truth_ineligible_assignment", 0),
                ("task_coverage", 2),
            ):
                key = label + "_" + metric
                check(key in archived, "Missing archived paired contrast "+key)
                bootstrap = paired_bootstrap(
                    cohort, baseline=baseline, candidate="median_3_motion",
                    value=metric,
                    seed=seed_for(82028, item["n"], item["scenario"], offset)
                    + effect_offset,
                )
                original = archived[key]
                close_number(original["difference"],
                             bootstrap["mean_difference"],
                             label="archived paired contrast difference")
                close_number(original["percentile_95_low"],
                             bootstrap["percentile_95_interval"][0],
                             label="archived paired contrast lower bound")
                close_number(original["percentile_95_high"],
                             bootstrap["percentile_95_interval"][1],
                             label="archived paired contrast upper bound")
    check(len(seen_summaries) == len(FLEETS)*len(SCENARIOS)*len(METHODS),
          "Missing stratum summaries")
    return {
        "sample_type":sample_type,
        "root_seed":root,
        "source_revision":manifest["source_revision"],
        "episodes":len(sources),
        "policy_rows":len(rows),
        "stratum_rows":len(summaries),
        "source_hashes":manifest["sha256"],
        "episode_seed_set":sorted(x["seed"] for x in sources),
        "within_fault_bound_episodes":sum(x["within_fault_bound"] for x in sources),
        "outside_fault_bound_episodes":sum(not x["within_fault_bound"] for x in sources),
        "paired_episodes":pairing,
    }


def wilson95(successes: int, trials: int) -> dict:
    z=1.959963984540054
    p=successes/trials
    d=1+z*z/trials
    c=(p+z*z/(2*trials))/d
    h=z*math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/d
    return {"rate":p,"lower":max(0,c-h),"upper":min(1,c+h)}


def paired_bootstrap(episodes: list[dict], *, baseline: str,
                     candidate: str, value: str,
                     seed: int, draws: int = 500) -> dict:
    delta=[
        float(item[candidate][value])-float(item[baseline][value])
        for item in episodes
    ]
    rng=random.Random(seed)
    ranked=sorted(
        fmean(delta[rng.randrange(len(delta))] for _ in delta)
        for _ in range(draws)
    )
    lo=ranked[int((draws-1)*0.025)]
    hi=ranked[int((draws-1)*0.975)]
    return {
        "mean_difference":fmean(delta),
        "percentile_95_interval":[lo,hi],
        "unit":"paired_synthetic_episode",
        "exploratory_only":True,
    }


def report(dev: dict, holdout: dict) -> dict:
    check(dev["source_revision"] == holdout["source_revision"],
          "Development/heldout use different code revisions")
    check(not set(dev["episode_seed_set"]) &
          set(holdout["episode_seed_set"]), "Leaked dev seed into heldout")
    groups=holdout["paired_episodes"]
    sorted_keys=sorted(groups)
    rows=[groups[key] for key in sorted_keys]
    counts={}
    for method in METHODS:
        harm=sum(x[method]["any_truth_ineligible_assignment"] for x in rows)
        counts[method]={
            "harmful_episodes":harm,"episode_count":len(rows),
            "synthetic_wilson_95":wilson95(harm,len(rows)),
            "mean_task_coverage":fmean(x[method]["task_coverage"] for x in rows),
            "mean_assigned_tasks":fmean(x[method]["tasks_assigned"] for x in rows),
        }
    contrasts={}
    for original, new in (
        ("veto_3","median_3_motion"),
        ("age_only","median_3_motion"),
        ("median_3_age","median_3_motion"),
    ):
        label=f"{new}_minus_{original}"
        contrasts[label]={
            metric:paired_bootstrap(
                rows, baseline=original, candidate=new, value=metric,
                seed=hashlib.sha256((label+"|"+metric+"|step9").encode()).digest()[0]+9116)
            for metric in ("any_truth_ineligible_assignment","task_coverage")
        }
        contrasts[label]["discordant_safety_pairs"]={
            "only_baseline_harmful":sum(
                x[original]["any_truth_ineligible_assignment"]==1 and
                x[new]["any_truth_ineligible_assignment"]==0 for x in rows),
            "only_candidate_harmful":sum(
                x[original]["any_truth_ineligible_assignment"]==0 and
                x[new]["any_truth_ineligible_assignment"]==1 for x in rows),
        }
    by_scenario={}
    for scenario in SCENARIOS:
        items=[groups[k] for k in sorted_keys if k[1]==scenario]
        by_scenario[scenario]={
            method:{
                "harmful_episodes":sum(x[method]["any_truth_ineligible_assignment"]
                                       for x in items),
                "n_episodes":len(items),
                "mean_coverage":fmean(x[method]["task_coverage"] for x in items),
            }
            for method in METHODS
        }
    return {
        "audit_status":"PASS",
        "scientific_readiness":"NO_GO_FOR_ALGORITHMIC_SUPERIORITY",
        "source_revision":holdout["source_revision"],
        "development_episodes":dev["episodes"],
        "heldout_episodes":holdout["episodes"],
        "heldout_policy_rows":holdout["policy_rows"],
        "heldout_summaries":holdout["stratum_rows"],
        "outside_fleet_fault_bound_heldout_episodes":
            holdout["outside_fault_bound_episodes"],
        "synthetic_safety_coverage":counts,
        "exploratory_paired_contrasts":contrasts,
        "scenario_results":by_scenario,
        "evidence_limitations":[
            "Full signed witness envelopes, cryptographic signatures and quorum vote envelopes are not saved in the archival episode snapshot; the archive cannot independently cryptographically replay them.",
            "Witness observations are generated from synthetic oracle truth, not deployed sensors.",
            "Physical stop/execution, distributed task-ledger consensus and asynchronous full CBBA are not validated.",
            "Balanced synthetic scenario mixture does not estimate real incident prevalence.",
            "Resource-ineligible assignment does not detect plausible forged positions or collision risks.",
            "false_rejected_healthy_members is NOT necessarily a false positive (motion inconsistency may justify rejection).",
            "No preregistered confirmatory hypothesis test or externally validated effect/generalizability.",
            "A three-witness median with assumed f_w=1 is a known robust statistic, not proof of methodological novelty.",
        ],
        "prohibited_manuscript_claims":[
            "The proposed median strictly outperforms the conservative veto in safety.",
            "Cryptographic signing verifies physical telemetry correctness.",
            "Zero observed unsafe assignments proves zero future failure probability.",
            "The Step 5 static bundle auction is a faithful full published CBBA benchmark.",
            "The Step 8 archive independently verifies every original signature.",
            "The proposed recovery ledger guarantees exactly-once drone actuation.",
        ],
    }


def write_audit(output: Path, report_data: dict) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    data_path=output/"scientific_evidence_audit.json"
    data_path.write_text(
        json.dumps(report_data,sort_keys=True,indent=2,allow_nan=False)+"\n",
        encoding="utf-8")
    counts=report_data["synthetic_safety_coverage"]
    lines=[
        "# Step 9 independent evidence audit — heldout software study",
        "",
        "**Status:** Data integrity PASS. **Scientific novelty/superiority: NO-GO**.",
        "",
        f"Source revision: `{report_data['source_revision']}`.",
        f"Development episodes: {report_data['development_episodes']}; "
        f"heldout episodes: {report_data['heldout_episodes']}; "
        f"heldout correlated policy rows: {report_data['heldout_policy_rows']}.",
        "",
        "## Validated heldout summary (balanced synthetic scenario mixture)",
        "",
        "| Policy | Resource-ineligible episodes | Mean task coverage |",
        "|---|---:|---:|",
    ]
    for method in METHODS:
        entry=counts[method]
        lines.append(
            f"| `{method}` | {entry['harmful_episodes']}/"
            f"{entry['episode_count']} | {entry['mean_task_coverage']:.2%} |")
    lines.extend([
        "",
        "No reported number measures actual physical UAV flight safety. The "
        "sampling scheme does not imply real-world attack prevalence.",
        "",
        "## Pooled paired exploratory comparisons",
        "",
    ])
    for label, group in report_data["exploratory_paired_contrasts"].items():
        d=group["any_truth_ineligible_assignment"]
        c=group["task_coverage"]
        lines.append(
            f"- `{label}`: harmful-episode difference "
            f"{d['mean_difference']:+.2%} "
            f"(percentile 95% interval {d['percentile_95_interval'][0]:+.2%} to "
            f"{d['percentile_95_interval'][1]:+.2%}); "
            f"coverage difference {c['mean_difference']:+.2%} "
            f"({c['percentile_95_interval'][0]:+.2%} to "
            f"{c['percentile_95_interval'][1]:+.2%})."
        )
    lines.extend([
        "",
        "Intervals are post-hoc exploratory, paired over **independent episode "
        "units**, not policy rows; no multiplicity correction or external "
        "validity claim.",
        "",
        "## Critical evidence and generalizability blockers",
        "",
    ])
    lines.extend("- "+line for line in report_data["evidence_limitations"])
    lines.extend(["","## Claims prohibited by current evidence",""])
    lines.extend("- "+line for line in report_data["prohibited_manuscript_claims"])
    lines.extend([
        "",
        "**Recommendation:** Reframe as a reproducible empirical "
        "safety–availability limits / negative-results study, subject to "
        "novelty/literature fit and further external validation. Do not "
        "submit the current work as a novel provably Byzantine-robust "
        "allocation algorithm.",
        "",
    ])
    doc=output/"scientific_evidence_audit.md"
    doc.write_text("\n".join(lines),encoding="utf-8")
    hashes={f:hashlib.sha256((output/f).read_bytes()).hexdigest()
            for f in ("scientific_evidence_audit.json",
                      "scientific_evidence_audit.md")}
    output_manifest={
        "schema_version":1,
        "source_step8_revision":report_data["source_revision"],
        "audit_integrity":"PASS",
        "novelty_submission_gate":"NO_GO",
        "audited_files_sha256":hashes,
    }
    (output/"audit_manifest.json").write_text(
        json.dumps(output_manifest,indent=2,sort_keys=True)+"\n",
        encoding="utf-8")
    return output_manifest


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--development",type=Path,required=True)
    p.add_argument("--heldout",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    dev=audit_dir(args.development,sample_type="development",
                  root=82026,trials=8)
    hold=audit_dir(args.heldout,sample_type="heldout",
                   root=82027,trials=20)
    findings=report(dev,hold)
    manifest=write_audit(args.out,findings)
    print(json.dumps({
        "status":"PASS","scientific_novelty":"NO_GO",
        "heldout":findings["heldout_episodes"],
        "paired_rows":findings["heldout_policy_rows"],
        "report_sha256":manifest["audited_files_sha256"],
    },sort_keys=True,indent=2))


if __name__ == "__main__":
    try:
        main()
    except (EvidenceAuditError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"STEP9 EVIDENCE AUDIT FAILED: {exc}",file=sys.stderr)
        sys.exit(1)
