"""Fail-closed, quorum-scoped *planning* state machine for simulated task recovery.

One task has at most one outstanding coordinator lease. Reassignment requires
a matching, validly signed STOPPED receipt from the prior lease holder; merely
losing heartbeats, reaching lease expiry, or electing a new coordinator never
establishes that an old physical actuator has stopped. STOPPED/COMPLETED
signatures are untrusted member claims, NOT tamper-proof vehicle attestation.

No flight command is emitted from this module. The host must authenticate
coordinator authority and persist the intent separately. This provides an
auditable software decision protocol, NOT exactly-once physical execution.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping, Optional, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from swarm_mesh import HealthReport, SwarmIdentity
from swarm_tasks import allocate_tasks


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _xyz(raw: Sequence[float]) -> tuple[float, float, float]:
    try:
        xyz = tuple(float(x) for x in raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid task target") from exc
    if len(xyz) != 3 or not all(math.isfinite(x) for x in xyz):
        raise ValueError("Task target must contain finite XYZ")
    if not 1 <= xyz[2] <= 100:
        raise ValueError("Task altitude outside simulation safety window")
    return xyz


def _time(value: float) -> float:
    v = float(value)
    if not math.isfinite(v) or v < 0:
        raise ValueError("Invalid virtual time")
    return v


@dataclass(frozen=True)
class RecoveryPolicy:
    lease_s: float = 5.0
    receipt_max_delay_s: float = 20.0
    max_per_node: int = 1

    def __post_init__(self):
        if (not math.isfinite(self.lease_s) or self.lease_s <= 0 or
                not math.isfinite(self.receipt_max_delay_s) or
                self.receipt_max_delay_s <= 0 or
                not isinstance(self.max_per_node, int) or
                isinstance(self.max_per_node, bool) or self.max_per_node < 1):
            raise ValueError("Invalid recovery policy")


@dataclass(frozen=True)
class SignedTaskReceipt:
    mission_id: str
    task_id: str
    owner_id: int
    lease_version: int
    authority_epoch: int
    action: str
    observed_at: float
    signature_b64: str

    def unsigned(self) -> dict:
        return {
            "domain": "swarm-sim-task-lease-receipt-v1",
            "mission_id": self.mission_id, "task_id": self.task_id,
            "owner_id": int(self.owner_id),
            "lease_version": int(self.lease_version),
            "authority_epoch": int(self.authority_epoch),
            "action": self.action,
            "observed_at": float(self.observed_at),
        }


def sign_task_receipt(identity: SwarmIdentity, *, mission_id: str,
                      task_id: str, lease_version: int, authority_epoch: int,
                      action: str, observed_at: float) -> SignedTaskReceipt:
    """Sign owner testimony. Only STOPPED or COMPLETED are permitted."""
    if not isinstance(mission_id, str) or not mission_id or len(mission_id) > 128:
        raise ValueError("Invalid mission id")
    if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
        raise ValueError("Invalid task id")
    if action not in ("STOPPED", "COMPLETED"):
        raise ValueError("Invalid receipt action")
    if not isinstance(lease_version, int) or lease_version < 1:
        raise ValueError("Invalid lease version")
    if not isinstance(authority_epoch, int) or authority_epoch < 0:
        raise ValueError("Invalid epoch")
    issued = SignedTaskReceipt(
        mission_id, task_id, identity.node_id, lease_version, authority_epoch,
        action, _time(observed_at), "")
    proof = base64.b64encode(identity.private_key.sign(
        _canonical(issued.unsigned()))).decode("ascii")
    return SignedTaskReceipt(
        issued.mission_id, issued.task_id, issued.owner_id,
        issued.lease_version, issued.authority_epoch, issued.action,
        issued.observed_at, proof)


class TaskRecoveryLedger:
    """One-writer mission recovery ledger with stale-version fencing.

    Coordinator-safe intent is NOT a fleet-wide exactly-once property. Before
    applying any plan in a connected simulator, an external certified quorum
    audit should approve precisely the same preview and revision.
    """

    def __init__(self, mission_id: str, roster: Mapping[int, bytes],
                 policy: RecoveryPolicy = RecoveryPolicy()):
        if not isinstance(mission_id, str) or not mission_id or len(mission_id) > 128:
            raise ValueError("Invalid mission id")
        if len(roster) < 4 or len(roster) > 50:
            raise ValueError("Fixed roster requires 4..50 members")
        self.roster = {int(k): bytes(v) for k, v in roster.items()}
        for key in self.roster.values():
            Ed25519PublicKey.from_public_bytes(key)
        self.mission_id = mission_id
        self.policy = policy
        self.tasks: dict[str, dict] = {}
        self.revision = 0
        self.highest_authority_epoch = -1
        self.last_now = 0.0
        self.events: list[dict] = []
        # Commit only the exact preview just produced. A local digest is an
        # anti-tamper consistency check, NOT a distributed authorization proof.
        self._pending_preview_hash: Optional[str] = None

    def _record(self, kind: str, payload: dict, now: float) -> None:
        previous = self.events[-1]["hash"] if self.events else "0" * 64
        event = {
            "seq": len(self.events) + 1, "time": now,
            "kind": kind, "data": payload, "previous_hash": previous,
        }
        event["hash"] = hashlib.sha256(_canonical(event)).hexdigest()
        self.events.append(event)
        self.revision += 1

    def verify_local_chain(self) -> bool:
        """Detect accidental local edit, not cryptographic authenticity."""
        prev = "0" * 64
        for index, event in enumerate(self.events, start=1):
            if event.get("seq") != index or event.get("previous_hash") != prev:
                return False
            body = {k: value for k, value in event.items() if k != "hash"}
            if hashlib.sha256(_canonical(body)).hexdigest() != event.get("hash"):
                return False
            prev = event["hash"]
        return True

    def register(self, tasks: Mapping[str, Sequence[float]], *, now: float) -> dict:
        now = _time(now)
        if now < self.last_now:
            raise ValueError("Nonmonotonic virtual clock")
        if len(self.tasks) + len(tasks) > 1000:
            raise ValueError("Too many tasks")
        checked = {}
        for task_id, target in tasks.items():
            if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
                raise ValueError("Invalid task id")
            point = _xyz(target)
            if task_id in self.tasks and self.tasks[task_id]["target"] != point:
                raise ValueError("Conflicting task ID reuse")
            checked[task_id] = point
        new_ids = []
        for task_id, point in sorted(checked.items()):
            if task_id in self.tasks:
                continue
            self.tasks[task_id] = {
                "target": point, "status": "PENDING", "version": 0,
                "lease": None, "completed_at": None,
            }
            new_ids.append(task_id)
        self.last_now = now
        if new_ids:
            self._pending_preview_hash = None
        if new_ids:
            self._record("tasks_registered", {"task_ids": new_ids}, now)
        return {"new": new_ids, "existing": sorted(set(tasks) - set(new_ids))}

    def _eligibility(self, *, now: float, epoch: int, leader_id: int,
                     quorum_verified: bool) -> None:
        _time(now)
        if now < self.last_now:
            raise ValueError("Nonmonotonic virtual clock")
        if not isinstance(epoch, int) or epoch < 0 or epoch < self.highest_authority_epoch:
            raise PermissionError("Stale authority epoch")
        if leader_id not in self.roster or not quorum_verified:
            raise PermissionError("No verified quorum-certified coordinator")

    def preview(self, *, now: float, epoch: int, leader_id: int,
                quorum_verified: bool,
                positions: Mapping[int, Sequence[float]],
                health: Mapping[int, HealthReport],
                allowed_members: Optional[set[int]] = None) -> dict:
        """Plan without any ledger mutation. No commands are transmitted."""
        self._eligibility(now=now, epoch=epoch, leader_id=leader_id,
                          quorum_verified=quorum_verified)
        # Any outstanding attempt occupies its owner, even after expiry.
        # Without a signed stopping receipt, expiry is UNKNOWN, not STOPPED.
        reserved = {
            state["lease"]["owner_id"] for state in self.tasks.values()
            if state["lease"] is not None
        }
        if allowed_members is None:
            accepted = set(self.roster)
        else:
            accepted = set(allowed_members) & set(self.roster)
        fresh_positions = {i: p for i, p in positions.items()
                           if i in accepted and i not in reserved and i in health}
        fresh_health = {i: health[i] for i in fresh_positions}
        pending = {task_id: state["target"] for task_id, state in self.tasks.items()
                   if state["status"] == "PENDING"}
        allocations = allocate_tasks(
            fresh_positions, fresh_health, pending,
            max_per_node=self.policy.max_per_node)
        proposed = []
        for member, assignments in sorted(allocations.items()):
            for task_id, target in assignments:
                state = self.tasks[task_id]
                version = state["version"] + 1
                proposed.append({
                    "task_id": task_id, "owner_id": member,
                    "lease_version": version, "authority_epoch": epoch,
                    "leader_id": leader_id, "issued_at": now,
                    "expires_at": now + self.policy.lease_s,
                    "target": list(target),
                })
        proposed.sort(key=lambda x: (x["task_id"], x["owner_id"]))
        waiting = sorted(task_id for task_id, state in self.tasks.items()
                         if state["status"] == "PENDING" and
                         task_id not in {p["task_id"] for p in proposed})
        uncertain = sorted(task_id for task_id, state in self.tasks.items()
                           if state["lease"] is not None and
                           now >= state["lease"]["expires_at"])
        result = {
            "mission_id": self.mission_id, "expected_revision": self.revision,
            "leader_id": leader_id, "epoch": epoch, "decision_at": now,
            "proposed": proposed, "waiting": waiting,
            "expired_unconfirmed": uncertain,
            "active_lease_count": sum(s["lease"] is not None
                                      for s in self.tasks.values()),
            "status": ("READY" if proposed else
                       "HOLD_UNCONFIRMED" if uncertain else "NO_ELIGIBLE_PENDING"),
            "broadcast_commands_issued": False,
            "physical_execution_verified": False,
        }
        self._pending_preview_hash = hashlib.sha256(_canonical(result)).hexdigest()
        return result

    def commit(self, proposal: dict, *, quorum_verified: bool) -> dict:
        """Apply an externally authenticated/audited preview once."""
        if proposal.get("mission_id") != self.mission_id:
            raise ValueError("Mismatched mission")
        if proposal.get("expected_revision") != self.revision:
            raise ValueError("Changed ledger revision; replan before committing")
        if (self._pending_preview_hash is None or
                self._pending_preview_hash != hashlib.sha256(
                    _canonical(proposal)).hexdigest()):
            raise ValueError("Proposal changed since certified preview")
        now = _time(proposal["decision_at"])
        epoch = int(proposal["epoch"])
        leader = int(proposal["leader_id"])
        # Replay protection: re-evaluate from the coordinator's current ledger
        # (but without relying on any external observed positions).
        self._eligibility(now=now, epoch=epoch, leader_id=leader,
                          quorum_verified=quorum_verified)
        if not proposal.get("proposed"):
            self._pending_preview_hash = None
            return {"committed": [], "revision": self.revision}
        tasks = {x["task_id"] for x in proposal["proposed"]}
        owners = {x["owner_id"] for x in proposal["proposed"]}
        if len(tasks) != len(proposal["proposed"]):
            raise ValueError("A task cannot receive two concurrent leases")
        # A caller must not be able to forge the preview to bypass eligibility:
        # the only reliable commit is the one based on the saved preview hash
        # from a verified coordinator. Require a deterministic token created
        # only by preview() and validated against the ledger's pending state.
        if len(owners) < 1:
            raise ValueError("No owners")
        assigned_counts = {owner: sum(x["owner_id"] == owner
                                      for x in proposal["proposed"])
                           for owner in owners}
        if any(value > self.policy.max_per_node for value in assigned_counts.values()):
            raise ValueError("Recovery capacity exceeded")
        for item in proposal["proposed"]:
            task = self.tasks.get(item["task_id"])
            if (task is None or task["status"] != "PENDING" or task["lease"] is not None or
                    item["owner_id"] not in self.roster or
                    item["lease_version"] != task["version"] + 1 or
                    item["authority_epoch"] != epoch or
                    item["leader_id"] != leader or
                    item["issued_at"] != now or
                    item["expires_at"] != now + self.policy.lease_s or
                    item["target"] != list(task["target"])):
                raise ValueError("Invalid lease proposal")
        for item in proposal["proposed"]:
            task = self.tasks[item["task_id"]]
            task["lease"] = dict(item)
            task["version"] = item["lease_version"]
            task["status"] = "LEASED"
        self.highest_authority_epoch = max(self.highest_authority_epoch, epoch)
        self.last_now = now
        self._pending_preview_hash = None
        self._record("leases_committed", {
            "leader_id": leader, "epoch": epoch,
            "task_versions": {x["task_id"]: x["lease_version"]
                              for x in proposal["proposed"]},
            "owners": {x["task_id"]: x["owner_id"]
                       for x in proposal["proposed"]},
        }, now)
        return {"committed": proposal["proposed"], "revision": self.revision}

    def _verified_receipt(self, receipt: SignedTaskReceipt, now: float) -> dict:
        now = _time(now)
        if now < self.last_now:
            raise ValueError("Nonmonotonic virtual clock")
        if receipt.mission_id != self.mission_id or receipt.action not in (
                "STOPPED", "COMPLETED") or receipt.owner_id not in self.roster:
            raise PermissionError("Receipt not from an enrolled mission owner")
        task = self.tasks.get(receipt.task_id)
        if task is None or task["lease"] is None:
            raise PermissionError("No matching active lease")
        lease = task["lease"]
        if (receipt.lease_version != lease["lease_version"] or
                receipt.authority_epoch != lease["authority_epoch"] or
                receipt.owner_id != lease["owner_id"] or
                not math.isfinite(receipt.observed_at) or
                not lease["issued_at"] <= receipt.observed_at <= now or
                now - receipt.observed_at > self.policy.receipt_max_delay_s):
            raise PermissionError("Stale, future or mismatched receipt")
        try:
            signature = base64.b64decode(receipt.signature_b64, validate=True)
            Ed25519PublicKey.from_public_bytes(
                self.roster[receipt.owner_id]).verify(
                    signature, _canonical(receipt.unsigned()))
        except (InvalidSignature, ValueError, TypeError, OverflowError, binascii.Error):
            raise PermissionError("Invalid signed owner receipt") from None
        return task

    def receive(self, receipt: SignedTaskReceipt, *, now: float) -> dict:
        """Accept an owner's signed STOPPED or COMPLETED *claim*, not truth.

        An active malicious owner can sign a false STOPPED or COMPLETED claim.
        Without independent or trusted vehicle stop enforcement, a recovered
        lease may overlap physical motion even though coordinator state does not.
        """
        task = self._verified_receipt(receipt, now)
        before = task["lease"]
        self.last_now = now
        if receipt.action == "COMPLETED":
            task["status"] = "COMPLETED"
            task["completed_at"] = now
        else:
            task["status"] = "PENDING"
        task["lease"] = None
        self._pending_preview_hash = None
        self._record("owner_receipt_" + receipt.action.lower(), {
            "task_id": receipt.task_id, "owner_id": receipt.owner_id,
            "version": before["lease_version"], "epoch": before["authority_epoch"],
        }, now)
        return {"task_id": receipt.task_id, "state": task["status"],
                "acknowledgment_only": True, "revision": self.revision}

    def snapshot(self, *, now: float) -> dict:
        _time(now)
        tasks = {}
        for task_id, state in sorted(self.tasks.items()):
            lease = state["lease"]
            tasks[task_id] = {
                "target": list(state["target"]),
                "status": state["status"],
                "version": state["version"],
                "lease": dict(lease) if lease else None,
                "completed_at": state["completed_at"],
                "expired_unconfirmed": bool(lease and now >= lease["expires_at"]),
            }
        return {
            "mission_id": self.mission_id, "revision": self.revision,
            "highest_authority_epoch": self.highest_authority_epoch,
            "tasks": tasks, "events": list(self.events),
            "local_hash_chain_valid": self.verify_local_chain(),
            "hardware_execution_attested": False,
        }
