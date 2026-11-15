"""Step 8 opt-in, explicit-assumption robust peer-witness consistency policy.

Quorum median is NOT sensor attestation, Byzantine agreement or a novel
robust statistic. With 3 signed peer claims and <=1 arbitrary witness, the
median cannot be arbitrarily moved away from *two independently bounded*
honest observations. 2 colluding witnesses can defeat this assumption.
No change to Step 3's existing single-conflict veto or default allocation.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
from typing import Mapping, Optional, Sequence

from swarm_consistency_gate import (
    ConsistencyPolicy, SignedWitness, _valid_witness, consistency_gated_allocate,
)
from swarm_mesh import HealthReport
from swarm_tasks import allocate_tasks


@dataclass(frozen=True)
class RobustWitnessPolicy:
    health_witness_quorum: int = 3
    assumed_faulty_witnesses: int = 1
    health_tolerance_pct: float = 8.
    require_position_witnesses: bool = False
    max_position_error_m: float = 5.
    max_health_age_s: float = 2.
    max_position_age_s: float = 2.
    max_witness_age_s: float = 2.
    max_speed_m_s: float = 25.
    motion_slack_m: float = 2.

    def __post_init__(self):
        if (not isinstance(self.health_witness_quorum, int) or
                isinstance(self.health_witness_quorum, bool) or
                not isinstance(self.assumed_faulty_witnesses, int) or
                isinstance(self.assumed_faulty_witnesses, bool) or
                self.assumed_faulty_witnesses < 0 or
                self.health_witness_quorum < 2*self.assumed_faulty_witnesses+1 or
                self.health_witness_quorum < 1):
            raise ValueError("Insufficient unique witness quorum for assumed faults")
        values=(self.health_tolerance_pct,self.max_position_error_m,
                self.max_health_age_s,self.max_position_age_s,
                self.max_witness_age_s,self.max_speed_m_s,self.motion_slack_m)
        if not all(math.isfinite(x) for x in values):
            raise ValueError("Nonfinite robust witness policy parameter")
        if (self.health_tolerance_pct < 0 or self.max_position_error_m < 0 or
                min(self.max_health_age_s,self.max_position_age_s,
                    self.max_witness_age_s,self.max_speed_m_s) <= 0 or
                self.motion_slack_m < 0):
            raise ValueError("Invalid robust witness tolerances")

    def original_policy(self) -> ConsistencyPolicy:
        return ConsistencyPolicy(
            max_health_age_s=self.max_health_age_s,
            max_position_age_s=self.max_position_age_s,
            max_witness_age_s=self.max_witness_age_s,
            max_speed_m_s=self.max_speed_m_s,
            motion_slack_m=self.motion_slack_m,
            max_witness_health_error_pct=self.health_tolerance_pct,
        )


def robust_witness_allocate(
    *, positions: Mapping[int, Sequence[float]],
    health: Mapping[int, HealthReport],
    health_seen_at: Mapping[int, float],
    position_seen_at: Mapping[int, float],
    now: float, tasks: Mapping[str, Sequence[float]],
    roster: Mapping[int, bytes], epoch: int,
    witnesses: Mapping[int, Sequence[SignedWitness]],
    policy: RobustWitnessPolicy = RobustWitnessPolicy(),
    previous_positions: Optional[Mapping[int, tuple[Sequence[float], float]]] = None,
) -> dict:
    """Robustly filter authenticated source reports against signed peer claims.

    First stage uses Step 3 freshness / optional bounded motion without any
    witness; second stage uses only fresh, signed and distinct registered
    witness claims. Ambiguous repeated claims from one signer invalidate that
    reporter's evidence for this subject, not the whole fleet.
    """
    base=consistency_gated_allocate(
        positions=positions,health=health,health_seen_at=health_seen_at,
        position_seen_at=position_seen_at,now=now,tasks=tasks,
        roster=roster,epoch=epoch,policy=policy.original_policy(),
        previous_positions=previous_positions,witnesses={},
    )
    decisions={member:dict(record) for member,record in base["decisions"].items()}
    accepted_health={}
    accepted_positions={}
    for member in sorted(roster):
        if decisions[member]["action"] != "ACCEPT":
            continue
        signed={}
        equivocated=set()
        for witness in witnesses.get(member,()):
            if not _valid_witness(
                witness,subject=member,epoch=epoch,now=now,roster=roster,
                policy=policy.original_policy()):
                continue
            source=witness.reporter_id
            if source in equivocated:
                continue
            if source in signed:
                # Even bitwise-identical repeat testimony cannot inflate count;
                # inconsistent repeat testimony is excluded entirely.
                if witness != signed[source]:
                    equivocated.add(source)
                    signed.pop(source,None)
                continue
            signed[source]=witness
        selected=[signed[src] for src in sorted(signed)]
        health_evidence=[w.health for w in selected if w.health is not None]
        position_evidence=[w.position for w in selected if w.position is not None]
        detail=decisions[member]
        detail["health_witnesses"]=len(health_evidence)
        detail["position_witnesses"]=len(position_evidence)
        detail["independent_signature_sources"]=sorted(signed)
        detail["equivocating_sources"]=sorted(equivocated)
        if len(health_evidence) < policy.health_witness_quorum or (
            policy.require_position_witnesses and
            len(position_evidence) < policy.health_witness_quorum
        ):
            detail.update(
                action="REQUEST_FRESH_EVIDENCE",
                reason="robust_witness_quorum_unavailable",
                evidence_tier="insufficient_verified_witnesses",
            )
            continue
        # Use EXACT required 3 witnesses for frozen Step 8: if > quorum are
        # available, median uses all, never truth-selected subset.
        center={field:statistics.median(
            float(getattr(w,field)) for w in health_evidence)
            for field in ("battery","motor_health","link_quality")}
        self_report=HealthReport.from_dict(health[member].to_dict())
        divergence=max(abs(float(getattr(self_report,field))-value)
                       for field,value in center.items())
        detail["health_median_disagreement_pct"]=round(divergence,6)
        if divergence > policy.health_tolerance_pct:
            detail.update(
                action="REJECT",reason="robust_witness_median_conflict",
                evidence_tier="median_of_distinct_signed_witnesses",
            )
            continue
        if policy.require_position_witnesses:
            center_xyz=tuple(
                statistics.median(float(p[axis]) for p in position_evidence)
                for axis in range(3))
            if math.dist(tuple(float(x) for x in positions[member]),center_xyz) > (
                    policy.max_position_error_m):
                detail.update(
                    action="REJECT", reason="robust_witness_position_conflict",
                    evidence_tier="median_of_distinct_signed_witnesses",
                )
                continue
        detail.update(
            action="ACCEPT", reason="robust_median_consistent",
            evidence_tier="median_of_distinct_signed_witnesses",
        )
        accepted_health[member]=self_report
        accepted_positions[member]=positions[member]
    allocations=allocate_tasks(accepted_positions,accepted_health,tasks)
    assigned={job for items in allocations.values() for job,_ in items}
    return {
        "allocations":allocations,
        "unassigned":sorted(set(tasks)-assigned),
        "decisions":decisions,
        "decision_status":"ACCEPT" if assigned else "ABSTAIN",
        "policy":{
            "mode":"quorum_median_health",
            "health_witness_quorum":policy.health_witness_quorum,
            "assumed_faulty_witnesses":policy.assumed_faulty_witnesses,
            "max_health_age_s":policy.max_health_age_s,
            "max_position_age_s":policy.max_position_age_s,
            "requires_physical_attestation":False,
        },
    }
