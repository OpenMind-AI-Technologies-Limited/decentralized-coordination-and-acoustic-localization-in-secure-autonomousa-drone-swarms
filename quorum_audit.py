"""Static-membership quorum-certified append-only audit log for simulated swarms.

Unlike the legacy FlyingLedger's best-effort replication, a record here needs
N-f distinct Ed25519 approvals before it is committed. Voting is locked by
height and persisted before signing when a state directory is provided.

This is a quorum audit layer, NOT a complete consensus engine: it relies on
the already-certified mesh leader, static membership and bounded reachability.
It does not establish asynchronous Byzantine liveness or dynamic reconfiguration.
"""
from __future__ import annotations

import hashlib
import json
import binascii
from pathlib import Path
from typing import Mapping, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from swarm_identity_store import _atomic_json, _load_json, _safe_root
from swarm_mesh import ElectionCertificate, SwarmIdentity, _canonical, _vote_payload


def digest(obj: object) -> str:
    return hashlib.sha3_256(_canonical(obj)).hexdigest()


GENESIS_HASH = digest({"domain": "swarm-audit-genesis-v1"})


class QuorumAuditLedger:
    def __init__(self, identity: SwarmIdentity, roster: Mapping[int, bytes],
                 store_directory: Optional[str] = None):
        self.identity = identity
        self.node_id = identity.node_id
        self.roster = {int(k): bytes(v) for k, v in roster.items()}
        if self.roster.get(self.node_id) != identity.public_bytes() or len(self.roster) < 4:
            raise ValueError("Identity and static roster mismatch")
        self.f = (len(self.roster) - 1) // 3
        self.quorum = len(self.roster) - self.f
        self.locked_height: dict[int, str] = {}
        self.commits: list[dict] = []
        self.path = (_safe_root(store_directory) / f"audit-{self.node_id}.json"
                     if store_directory is not None else None)
        if self.path is not None:
            saved = _load_json(self.path)
            if saved is not None:
                if saved.get("version") != 1 or saved.get("node_id") != self.node_id:
                    raise ValueError("Audit store metadata mismatch")
                if saved.get("public_key_hex") != identity.public_bytes().hex():
                    raise ValueError("Audit log belongs to another identity")
                initial = list(saved.get("commits", []))
                self.locked_height = {int(k): str(v) for k, v in saved.get("locks", {}).items()}
                # Verify the full certificate chain rather than trusting disk.
                for item in initial:
                    if not self._commit_verified(item, persist=False):
                        raise ValueError("Corrupt persisted quorum audit log")

    @property
    def height(self) -> int:
        return len(self.commits)

    @property
    def tip(self) -> str:
        return GENESIS_HASH if not self.commits else self.commits[-1]["proposal"]["hash"]

    def _persist(self) -> None:
        if self.path is not None:
            _atomic_json(self.path, {
                "version": 1, "node_id": self.node_id,
                "public_key_hex": self.identity.public_bytes().hex(),
                "locks": {str(k): v for k, v in self.locked_height.items()},
                "commits": self.commits,
            })

    def _valid_certificate(self, cert: dict, author: int, epoch: int) -> bool:
        try:
            if int(cert["candidate"]) != author or int(cert["epoch"]) != epoch:
                return False
            approvals = {int(k): str(v) for k, v in cert["proofs"].items()}
            if len(approvals) < self.quorum:
                return False
            for member_id, signature in approvals.items():
                pub = self.roster.get(member_id)
                if pub is None:
                    return False
                import base64
                Ed25519PublicKey.from_public_bytes(pub).verify(
                    base64.b64decode(signature, validate=True),
                    _vote_payload(epoch, author),
                )
            return True
        except (KeyError, ValueError, TypeError, InvalidSignature, binascii.Error):
            return False

    def propose(self, event: dict, election_certificate: dict) -> dict:
        if not isinstance(event, dict):
            raise ValueError("Audit event must be a JSON object")
        epoch = int(election_certificate["epoch"])
        if not self._valid_certificate(election_certificate, self.node_id, epoch):
            raise PermissionError("Only a quorum-certified author may propose")
        core = {
            "domain": "swarm-audit-proposal-v1", "height": self.height + 1,
            "parent": self.tip, "author": self.node_id, "epoch": epoch,
            "event": event,
        }
        hash_value = digest(core)
        return {
            **core,
            "hash": hash_value,
            "author_signature_hex": self.identity.private_key.sign(_canonical(core)).hex(),
            "election_certificate": election_certificate,
        }

    def _validate_proposal(self, proposal: dict) -> bool:
        try:
            if proposal["domain"] != "swarm-audit-proposal-v1":
                return False
            author, epoch, height = (int(proposal[k]) for k in ("author", "epoch", "height"))
            if height < 1 or epoch < 1 or not isinstance(proposal["event"], dict):
                return False
            if not self._valid_certificate(proposal["election_certificate"], author, epoch):
                return False
            public = self.roster.get(author)
            if public is None:
                return False
            core = {k: proposal[k] for k in ("domain", "height", "parent", "author", "epoch", "event")}
            if proposal["hash"] != digest(core):
                return False
            Ed25519PublicKey.from_public_bytes(public).verify(
                bytes.fromhex(proposal["author_signature_hex"]), _canonical(core))
            return True
        except (InvalidSignature, KeyError, ValueError, TypeError, OverflowError):
            return False

    def vote(self, proposal: dict) -> dict:
        if not self._validate_proposal(proposal):
            raise ValueError("Invalid signed audit proposal or election certificate")
        height, hash_value = int(proposal["height"]), str(proposal["hash"])
        if height != self.height + 1 or proposal["parent"] != self.tip:
            raise ValueError("Out-of-order audit proposal")
        locked = self.locked_height.get(height)
        if locked is not None and locked != hash_value:
            raise PermissionError("Conflicting proposal at already signed audit height")
        if locked is None:
            self.locked_height[height] = hash_value
            try:
                self._persist()  # fsync lock before issuing a vote signature
            except Exception:
                del self.locked_height[height]
                raise
        return {
            "node_id": self.node_id,
            "height": height,
            "hash": hash_value,
            "signature_hex": self.identity.private_key.sign(
                _canonical({"domain": "swarm-audit-vote-v1", "height": height, "hash": hash_value})
            ).hex(),
        }

    def _commit_verified(self, record: dict, persist: bool = True) -> bool:
        try:
            proposal, votes = record["proposal"], record["votes"]
            if not self._validate_proposal(proposal):
                return False
            height = int(proposal["height"])
            duplicate = height <= self.height
            if duplicate:
                previous = self.commits[height - 1]
                if previous["proposal"]["hash"] != proposal["hash"]:
                    return False
            elif height != self.height + 1 or proposal["parent"] != self.tip:
                return False
            if self.locked_height.get(height, proposal["hash"]) != proposal["hash"]:
                return False
            if len(votes) < self.quorum:
                return False
            unique = set()
            for vote in votes:
                voter = int(vote["node_id"])
                if voter in unique or voter not in self.roster:
                    return False
                if int(vote["height"]) != height or vote["hash"] != proposal["hash"]:
                    return False
                unique.add(voter)
                Ed25519PublicKey.from_public_bytes(self.roster[voter]).verify(
                    bytes.fromhex(vote["signature_hex"]),
                    _canonical({"domain": "swarm-audit-vote-v1",
                                "height": height, "hash": proposal["hash"]}),
                )
            if len(unique) < self.quorum:
                return False
            if duplicate:
                return True
            original_locks = dict(self.locked_height)
            self.locked_height[height] = proposal["hash"]
            self.commits.append({"proposal": dict(proposal), "votes": list(votes)})
            try:
                if persist:
                    self._persist()
            except Exception:
                self.commits.pop()
                self.locked_height = original_locks
                raise
            return True
        except (InvalidSignature, KeyError, ValueError, TypeError, OverflowError, IndexError):
            return False

    def commit(self, proposal: dict, votes: list[dict]) -> bool:
        return self._commit_verified({"proposal": proposal, "votes": votes})

    def synchronize(self, committed_records: list[dict]) -> int:
        accepted = 0
        for record in committed_records:
            before = self.height
            if self._commit_verified(record):
                if self.height > before:
                    accepted += 1
            else:
                break
        return accepted

    def consistent_with(self, peer: "QuorumAuditLedger") -> bool:
        return self.height == peer.height and self.tip == peer.tip
