"""Controlled dynamic task-lease recovery diagnostic episodes (research Step 6).

The source event stream models truthful, missing, or malicious signed STOP
claims, quorum transitions and task arrivals. It does NOT deliver flight
commands or establish actual hardware stop enforcement. No incident-frequency
or physical exactly-once statement may be inferred from this fixture set.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys

from swarm_mesh import HealthReport, SwarmIdentity
from swarm_task_recovery import (
    RecoveryPolicy, TaskRecoveryLedger, sign_task_receipt,
)


SCENARIOS = (
    "normal_completion",
    "signed_stop_reassign",
    "unconfirmed_failure",
    "quorum_partition",
    "epoch_failover",
    "forged_stop_attempt",
    "false_signed_stop",
    "late_stop_after_expiry",
    "new_task_arrival",
    "no_eligible_recovery",
)


def run_recovery_case(*, scenario: str, size: int, seed: int) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError("Unknown recovery scenario")
    if not 4 <= size <= 50:
        raise ValueError("Invalid simulated swarm size")
    rng = random.Random(seed)
    identities = {i: SwarmIdentity(i) for i in range(1, size + 1)}
    roster = {i: identity.public_bytes() for i, identity in identities.items()}
    ledger = TaskRecoveryLedger(f"recovery-{size}-{seed}-{scenario}", roster,
                                RecoveryPolicy(lease_s=5.0, max_per_node=1))
    xyz = {i: (65.0 + (i - 1) * 12.0, 0.0, 10.0) for i in identities}
    xyz[2] = (0.0, 0.0, 10.0)
    # Small seeded variation of *honest input* positions, same fixed
    # scenario structure for all runs. Not an independent fleet distribution.
    for i in xyz:
        x, y, z = xyz[i]
        xyz[i] = (round(x + rng.uniform(-0.2, 0.2), 5), y, z)
    health = {i: HealthReport(90., 100., 95.) for i in identities}
    ledger.register({"inspection-001": (1.0, 0.0, 10.0)}, now=1000.0)
    steps = []
    discarded_receipts = 0
    accepted_receipts = 0

    def state_event(name: str, timepoint: float, plan: dict | None = None, **extra) -> None:
        state = ledger.snapshot(now=timepoint)
        steps.append({
            "event": name, "time_s": timepoint, "revision": state["revision"],
            "tasks": {task_id: {
                "status": x["status"], "version": x["version"],
                "owner_id": x["lease"]["owner_id"] if x["lease"] else None,
                "expired_unconfirmed": x["expired_unconfirmed"],
            } for task_id, x in state["tasks"].items()},
            "proposed": plan["proposed"] if plan else [],
            "held": plan["expired_unconfirmed"] if plan else [],
            **extra,
        })

    def schedule(now: float, *, epoch: int = 1, quorum: bool = True,
                 allowed: set[int] | None = None) -> dict | None:
        try:
            plan = ledger.preview(
                now=now, epoch=epoch, leader_id=1, quorum_verified=quorum,
                positions=xyz, health=health, allowed_members=allowed)
            if plan["proposed"]:
                ledger.commit(plan, quorum_verified=quorum)
            state_event("plan", now, plan=plan, epoch=epoch, quorum=quorum)
            return plan
        except PermissionError as error:
            state_event("plan_denied", now, epoch=epoch, quorum=quorum,
                        reason=str(error))
            return None

    def acknowledge(now: float, *, kind: str, signer: int = 2,
                    version: int = 1, epoch: int = 1,
                    observed: float | None = None) -> bool:
        nonlocal discarded_receipts, accepted_receipts
        receipt = sign_task_receipt(
            identities[signer], mission_id=ledger.mission_id,
            task_id="inspection-001", lease_version=version,
            authority_epoch=epoch, action=kind,
            observed_at=now if observed is None else observed)
        try:
            result = ledger.receive(receipt, now=now)
            accepted_receipts += 1
            state_event("receipt_accepted", now, kind=kind, signer=signer,
                        acknowledgment_only=result["acknowledgment_only"])
            return True
        except PermissionError:
            discarded_receipts += 1
            state_event("receipt_rejected", now, kind=kind, signer=signer)
            return False

    first = schedule(1000.0)
    if not first or not first["proposed"] or first["proposed"][0]["owner_id"] != 2:
        raise AssertionError("Recovery diagnostic fixture requires owner 2 initially")

    if scenario == "normal_completion":
        acknowledge(1001.0, kind="COMPLETED")
        schedule(1002.0)
    elif scenario == "new_task_arrival":
        ledger.register({"inspection-002": (64.0, 0.0, 10.0)}, now=1001.0)
        state_event("task_added", 1001.0)
        schedule(1001.0)
    elif scenario == "unconfirmed_failure":
        schedule(1007.0, epoch=2, allowed=set(identities) - {2})
    elif scenario == "quorum_partition":
        schedule(1001.0, epoch=1, quorum=False, allowed=set(identities) - {2})
        schedule(1008.0, epoch=2, quorum=True, allowed=set(identities) - {2})
    elif scenario == "forged_stop_attempt":
        acknowledge(1001.0, kind="STOPPED", signer=1)
        schedule(1008.0, epoch=2, allowed=set(identities) - {2})
    else:
        if scenario == "late_stop_after_expiry":
            schedule(1007.0, epoch=2, allowed=set(identities) - {2})
            acknowledge(1008.0, kind="STOPPED")
            schedule(1009.0, epoch=2, allowed=set(identities) - {2})
        else:
            acknowledge(1001.0, kind="STOPPED")
            if scenario == "no_eligible_recovery":
                schedule(1002.0, epoch=2, allowed=set())
            else:
                schedule(1002.0, epoch=2, allowed=set(identities) - {2})
            if scenario == "epoch_failover":
                acknowledge(1003.0, kind="COMPLETED", signer=2, version=1, epoch=1)
                schedule(1003.0, epoch=1, allowed=set(identities) - {2})

    final_time = steps[-1]["time_s"]
    snapshot = ledger.snapshot(now=final_time)
    leases = [item for item in snapshot["tasks"].values() if item["lease"]]
    version_advance = snapshot["tasks"]["inspection-001"]["version"]
    return {
        "scenario": scenario, "size": size, "seed": seed,
        "mission_id": ledger.mission_id,
        "simulated_truthful_stop_confirmed": scenario not in (
            "false_signed_stop", "forged_stop_attempt",
            "unconfirmed_failure", "quorum_partition", "no_eligible_recovery"),
        "false_stop_claim_injected": scenario == "false_signed_stop",
        "signed_owner_ack_does_not_attest_hardware": True,
        "accepted_owner_receipts": accepted_receipts,
        "rejected_receipts": discarded_receipts,
        "task_versions_issued": version_advance,
        "current_outstanding_leases": len(leases),
        "expired_unconfirmed": sum(item["expired_unconfirmed"]
                                   for item in snapshot["tasks"].values()),
        "task_count": len(snapshot["tasks"]),
        "local_audit_chain_valid": ledger.verify_local_chain(),
        "all_steps": steps,
        "ledger_events": ledger.events,
        "physical_flight": False,
        "packet_loss_modeled": False,
        "synthetic_observation_only": True,
        "global_exactly_once_execution_verified": False,
    }


def run_recovery_suite(*, sizes=(5,10), trials=2, seed=2026) -> list[dict]:
    if not sizes or len(set(sizes)) != len(sizes) or any(
            not isinstance(n,int) or not 4 <= n <= 50 for n in sizes):
        raise ValueError("Distinct 4..50 fleet sizes required")
    if not isinstance(trials,int) or not 1 <= trials <= 20:
        raise ValueError("Step 6 diagnostic repeats must be 1..20")
    results = []
    for size in sizes:
        for index, name in enumerate(SCENARIOS):
            for trial in range(trials):
                episode_seed = int(seed) + size*101 + index*100003 + trial*1009
                results.append({
                    **run_recovery_case(scenario=name, size=size,
                                        seed=episode_seed),
                    "trial": trial,
                })
    return results


def write_recovery_evidence(directory: Path, rows: list[dict]) -> dict:
    directory.mkdir(parents=True,exist_ok=True)
    raw = (json.dumps(rows, indent=2, sort_keys=True,allow_nan=False)+"\n").encode()
    (directory/"recovery_episodes.json").write_bytes(raw)
    columns=("scenario","size","trial","seed","task_count",
             "accepted_owner_receipts","rejected_receipts",
             "task_versions_issued","current_outstanding_leases",
             "expired_unconfirmed","local_audit_chain_valid",
             "false_stop_claim_injected","simulated_truthful_stop_confirmed")
    with (directory/"recovery_metrics.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({name:row[name] for name in columns})
    if os.getenv("GITHUB_SHA"):
        revision=os.environ["GITHUB_SHA"]
    else:
        try:
            revision=subprocess.check_output(
                ["git","rev-parse","HEAD"],text=True,
                stderr=subprocess.DEVNULL,timeout=3).strip()
        except (OSError,subprocess.SubprocessError):
            revision="unavailable"
    hashes={
        name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
        for name in ("recovery_episodes.json","recovery_metrics.csv")
    }
    manifest={
        "schema_version":1,"source_revision":revision,
        "platform":platform.platform(),"python":sys.version.split()[0],
        "scope":"software_only_fixed_scenario_recovery_diagnostics",
        "episode_rows":len(rows),"scenario_count":len(SCENARIOS),
        "sizes":sorted({row["size"] for row in rows}),
        "scenarios":list(SCENARIOS),"sha256":hashes,
        "signed_stopping_claim_not_physical_proof":True,
        "local_ledger_only_not_distributed_consensus":True,
        "no_flight_commands_emitted":True,
        "independent_publication_scale_evidence":False,
        "new_paper_statistical_superiority_established":False,
        "prior_supplementary_378_trials_untouched":True,
        "recovery_time_is_virtual_s":True,
    }
    (directory/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return manifest


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes",nargs="+",type=int,default=[5,10])
    parser.add_argument("--trials",type=int,default=2)
    parser.add_argument("--seed",type=int,default=2026)
    parser.add_argument("--out",default="experiment_outputs/consistency-gated-step6")
    args=parser.parse_args()
    rows=run_recovery_suite(sizes=tuple(args.sizes),
                            trials=args.trials,seed=args.seed)
    manifest=write_recovery_evidence(Path(args.out),rows)
    print(json.dumps({
        "episodes":manifest["episode_rows"],
        "scenarios":manifest["scenario_count"],
        "sizes":manifest["sizes"],"sha256":manifest["sha256"],
        "out":args.out,
    },indent=2,sort_keys=True))


if __name__=="__main__":
    main()
