"""Opt-in, evidence-scoped task-allocation gate for simulated authenticated swarms.

A signature authenticates a reporter, not the physical truth of a report.
This module never reads offline ground truth. Independent witness reports have
their own signed domain and require already-enrolled, distinct peer identities.
The policy is a hypothesis for controlled experiments, not a flight-safety proof.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import json
import math
from typing import Mapping, Optional, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from swarm_mesh import HealthReport, SwarmIdentity
from swarm_tasks import allocate_tasks


@dataclass(frozen=True)
class ConsistencyPolicy:
    max_health_age_s: float = 2.0
    max_position_age_s: float = 2.0
    max_witness_age_s: float = 2.0
    max_speed_m_s: float = 25.0
    motion_slack_m: float = 2.0
    max_witness_position_error_m: float = 5.0
    max_witness_health_error_pct: float = 8.0
    min_position_witnesses: int = 0
    min_health_witnesses: int = 0

    def __post_init__(self):
        values = (self.max_health_age_s, self.max_position_age_s,
                  self.max_witness_age_s, self.max_speed_m_s,
                  self.motion_slack_m, self.max_witness_position_error_m,
                  self.max_witness_health_error_pct)
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError("Policy parameters must be finite")
        if min(self.max_health_age_s, self.max_position_age_s,
               self.max_witness_age_s, self.max_speed_m_s) <= 0:
            raise ValueError("Freshness limits and speed must be positive")
        if min(self.motion_slack_m, self.max_witness_position_error_m,
               self.max_witness_health_error_pct) < 0:
            raise ValueError("Evidence tolerances must be nonnegative")
        if (not isinstance(self.min_position_witnesses, int) or
                not isinstance(self.min_health_witnesses, int) or
                min(self.min_position_witnesses, self.min_health_witnesses) < 0):
            raise ValueError("Required witness counts must be nonnegative integers")


@dataclass(frozen=True)
class SignedWitness:
    """A peer-signed *claim*, not hardware attestation or automatic truth."""
    reporter_id: int
    subject_id: int
    epoch: int
    observed_at: float
    position: Optional[tuple[float, float, float]]
    health: Optional[HealthReport]
    position_uncertainty_m: float
    signature_b64: str

    def unsigned_payload(self) -> dict:
        return {
            "domain": "swarm-independent-telemetry-witness-v1",
            "reporter_id": int(self.reporter_id),
            "subject_id": int(self.subject_id),
            "epoch": int(self.epoch),
            "observed_at": float(self.observed_at),
            "position": list(self.position) if self.position is not None else None,
            "health": self.health.to_dict() if self.health is not None else None,
            "position_uncertainty_m": float(self.position_uncertainty_m),
        }


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def sign_witness(identity: SwarmIdentity, *, subject_id: int, epoch: int,
                 observed_at: float,
                 position: Optional[Sequence[float]] = None,
                 health: Optional[HealthReport] = None,
                 position_uncertainty_m: float = 0.0) -> SignedWitness:
    """Produce an enrolled peer's signed report for tests/future observers.

    A compromised witness can sign a lie. A caller must not fabricate
    independent measurements using offline evaluation truth in real studies.
    """
    xyz = tuple(float(v) for v in position) if position is not None else None
    if xyz is not None and (len(xyz) != 3 or not all(math.isfinite(v) for v in xyz)):
        raise ValueError("Witness position must be finite XYZ")
    if not math.isfinite(float(observed_at)) or not math.isfinite(float(position_uncertainty_m)):
        raise ValueError("Witness observation time and uncertainty must be finite")
    if position_uncertainty_m < 0 or (xyz is None and health is None):
        raise ValueError("Witness needs information and valid uncertainty")
    unsigned = SignedWitness(
        identity.node_id, int(subject_id), int(epoch), float(observed_at),
        xyz, health, float(position_uncertainty_m), "")
    signature = identity.private_key.sign(_canonical(unsigned.unsigned_payload()))
    return SignedWitness(
        unsigned.reporter_id, unsigned.subject_id, unsigned.epoch,
        unsigned.observed_at, unsigned.position, unsigned.health,
        unsigned.position_uncertainty_m, base64.b64encode(signature).decode("ascii"))


def _position(value: Sequence[float]) -> tuple[float, float, float]:
    try:
        point = tuple(float(v) for v in value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid position") from exc
    if len(point) != 3 or not all(math.isfinite(v) for v in point):
        raise ValueError("Expected finite XYZ")
    return point


def _valid_witness(witness: SignedWitness, *, subject: int, epoch: int,
                   now: float, roster: Mapping[int, bytes],
                   policy: ConsistencyPolicy) -> bool:
    if (witness.subject_id != subject or witness.reporter_id == subject or
            witness.reporter_id not in roster or witness.epoch != epoch or
            witness.position is None and witness.health is None or
            not math.isfinite(witness.observed_at) or
            not 0 <= now - witness.observed_at <= policy.max_witness_age_s or
            not math.isfinite(witness.position_uncertainty_m) or
            witness.position_uncertainty_m < 0):
        return False
    try:
        if witness.position is not None:
            _position(witness.position)
        signature = base64.b64decode(witness.signature_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(roster[witness.reporter_id]).verify(
            signature, _canonical(witness.unsigned_payload()))
    except (InvalidSignature, ValueError, TypeError, KeyError, OverflowError, 
                        AttributeError, binascii.Error):
        return False
    return True


def _decision(action: str, reason: str, *, position_witnesses: int = 0,
              health_witnesses: int = 0) -> dict:
    return {
        "action": action, "reason": reason,
        "position_witnesses": position_witnesses,
        "health_witnesses": health_witnesses,
        "evidence_tier": ("independently_corroborated"
                          if position_witnesses or health_witnesses
                          else "signed_self_report_only"),
    }


def consistency_gated_allocate(
    *,
    positions: Mapping[int, Sequence[float]],
    health: Mapping[int, HealthReport],
    health_seen_at: Mapping[int, float],
    position_seen_at: Mapping[int, float],
    now: float,
    tasks: Mapping[str, Sequence[float]],
    roster: Mapping[int, bytes],
    epoch: int,
    policy: ConsistencyPolicy = ConsistencyPolicy(),
    previous_positions: Optional[Mapping[int, tuple[Sequence[float], float]]] = None,
    witnesses: Optional[Mapping[int, Sequence[SignedWitness]]] = None,
) -> dict:
    """Filter untrusted inputs before calling the unchanged greedy allocator.

    `health` and `positions` must originate from authenticated MeshNode
    receipt; the coordinator must not use the offline evaluator's truth.
    `position_seen_at` is independent from health age. Corroboration relies
    on explicit assumptions about at least one honest independent reporter.
    """
    if not math.isfinite(float(now)) or int(epoch) < 0:
        raise ValueError("Clock and epoch must be valid")
    prior = previous_positions or {}
    witnesses = witnesses or {}
    selected_health = {}
    selected_position = {}
    decisions = {}
    for node_id in sorted(roster):
        if node_id not in health or node_id not in positions:
            decisions[node_id] = _decision("REQUEST_FRESH_EVIDENCE", "missing_self_observation")
            continue
        try:
            htime = float(health_seen_at[node_id])
            ptime = float(position_seen_at[node_id])
            point = _position(positions[node_id])
            clean_health = HealthReport.from_dict(health[node_id].to_dict())
        except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
            decisions[node_id] = _decision("REJECT", "invalid_self_observation")
            continue
        if not all(math.isfinite(v) for v in (htime, ptime)):
            decisions[node_id] = _decision("REJECT", "invalid_observation_time")
            continue
        if (not 0 <= now - htime <= policy.max_health_age_s or
                not 0 <= now - ptime <= policy.max_position_age_s):
            decisions[node_id] = _decision("REQUEST_FRESH_EVIDENCE", "stale_health_or_position")
            continue

        if node_id in prior:
            try:
                prev, prev_time = prior[node_id]
                prev_point = _position(prev)
                age = ptime - float(prev_time)
                if not math.isfinite(age) or age < 0:
                    raise ValueError("Invalid observation order")
                if math.dist(point, prev_point) > (
                        policy.max_speed_m_s * age + policy.motion_slack_m):
                    decisions[node_id] = _decision("REJECT", "implausible_position_jump")
                    continue
            except (ValueError, TypeError, OverflowError):
                decisions[node_id] = _decision("REJECT", "invalid_position_history")
                continue

        # Even valid self-signatures are never counted as independent witnesses.
        seen = set()
        pos_count = health_count = 0
        conflict = False
        for witness in witnesses.get(node_id, ()):
            if not _valid_witness(witness, subject=node_id, epoch=epoch,
                                  now=now, roster=roster, policy=policy):
                continue
            if witness.reporter_id in seen:
                # Duplicate signed claims cannot inflate independent evidence.
                continue
            seen.add(witness.reporter_id)
            if witness.position is not None:
                pos_count += 1
                tolerance = (policy.max_witness_position_error_m +
                             witness.position_uncertainty_m +
                             policy.max_speed_m_s * abs(ptime - witness.observed_at))
                if math.dist(point, _position(witness.position)) > tolerance:
                    conflict = True
            if witness.health is not None:
                health_count += 1
                if any(abs(float(getattr(clean_health, field)) -
                           float(getattr(witness.health, field))) >
                       policy.max_witness_health_error_pct
                       for field in ("battery", "motor_health", "link_quality")):
                    conflict = True

        if conflict:
            decisions[node_id] = _decision(
                "REJECT", "signed_witness_conflict",
                position_witnesses=pos_count, health_witnesses=health_count)
            continue
        if (pos_count < policy.min_position_witnesses or
                health_count < policy.min_health_witnesses):
            decisions[node_id] = _decision(
                "REQUEST_FRESH_EVIDENCE", "independent_evidence_insufficient",
                position_witnesses=pos_count, health_witnesses=health_count)
            continue
        decisions[node_id] = _decision(
            "ACCEPT", "bounded_observations_pass",
            position_witnesses=pos_count, health_witnesses=health_count)
        selected_health[node_id] = clean_health
        selected_position[node_id] = point

    assignments = allocate_tasks(selected_position, selected_health, tasks)
    requested = {str(task_id) for task_id in tasks}
    assigned = {task_id for values in assignments.values() for task_id, _ in values}
    return {
        "allocations": assignments,
        "unassigned": sorted(requested - assigned),
        "decisions": decisions,
        "decision_status": "ACCEPT" if assigned else "ABSTAIN",
        "policy": {
            "min_position_witnesses": policy.min_position_witnesses,
            "min_health_witnesses": policy.min_health_witnesses,
            "max_health_age_s": policy.max_health_age_s,
            "max_position_age_s": policy.max_position_age_s,
        },
    }
