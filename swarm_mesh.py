"""Authenticated, independently executable coordination nodes for UAV-swarm research.

Implements quorum-certified elections under static, preauthenticated membership.
Does not claim full PBFT, dynamic membership, or asynchronous Byzantine liveness.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import math
import os
import time
import threading
from typing import Callable, Dict, Mapping, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from swarm_identity_store import VoteJournal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _bounded_percent(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Non-finite health metric")
    return min(100.0, max(0.0, value))


@dataclass(frozen=True)
class HealthReport:
    battery: float
    motor_health: float
    link_quality: float

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "HealthReport":
        return cls(*(_bounded_percent(value[key]) for key in ("battery", "motor_health", "link_quality")))

    def to_dict(self) -> dict:
        return {"battery": self.battery, "motor_health": self.motor_health, "link_quality": self.link_quality}

    def score(self) -> float:
        """MCSS, normalized to [0, 1]."""
        return (0.45 * self.battery + 0.35 * self.motor_health + 0.20 * self.link_quality) / 100.0


@dataclass(frozen=True)
class ElectionCertificate:
    epoch: int
    candidate: int
    proofs: dict[int, str]

    def to_dict(self) -> dict:
        return {"epoch": self.epoch, "candidate": self.candidate,
                "proofs": {str(k): v for k, v in self.proofs.items()}}


class SwarmIdentity:
    def __init__(self, node_id: int, private_key: Optional[Ed25519PrivateKey] = None):
        self.node_id = int(node_id)
        self.private_key = private_key or Ed25519PrivateKey.generate()

    def public_bytes(self) -> bytes:
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        return self.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class AuthenticatedChannel:
    """Encrypted signed envelopes, membership validation, and bounded replay guard."""

    def __init__(self, identity: SwarmIdentity, peer_keys: Mapping[int, bytes], group_key: bytes,
                 clock: Callable[[], float] = time.time, max_age_s: float = 60.0):
        if len(group_key) != 32:
            raise ValueError("Group key must be 32 bytes")
        if peer_keys.get(identity.node_id) != identity.public_bytes():
            raise ValueError("Local identity must match preauthenticated roster")
        self.identity = identity
        self.peers = {int(k): Ed25519PublicKey.from_public_bytes(v) for k, v in peer_keys.items()}
        self.cipher = AESGCM(group_key)
        self.clock = clock
        self.max_age_s = max_age_s
        self._sequence = 0
        self._boot_id = os.urandom(16).hex()
        self._send_lock = threading.Lock()
        self._receive_lock = threading.RLock()
        # Sequence numbers are scoped to a signed process boot identifier.
        # This permits a restarted peer to use seq=0 without accepting a
        # duplicate message from the previous boot session.
        self._highest: Dict[tuple[int, str], int] = {}
        self._seen: Dict[tuple[int, str], set[int]] = {}
        self._sessions_seen_at: Dict[tuple[int, str], float] = {}

    def seal(self, kind: str, epoch: int, body: dict) -> bytes:
        with self._send_lock:
            sequence = self._sequence
            self._sequence += 1
        message = {"version": 1, "sender": self.identity.node_id,
                   "boot": self._boot_id, "seq": sequence, "time": float(self.clock()),
                   "kind": str(kind), "epoch": int(epoch), "body": body}
        signature = self.identity.private_key.sign(_canonical(message))
        signed = {"message": message, "signature": _b64(signature)}
        nonce = os.urandom(12)
        return _canonical({"version": 1, "nonce": _b64(nonce),
                           "ciphertext": _b64(self.cipher.encrypt(nonce, _canonical(signed), b"swarm-mesh-v1"))})

    def open(self, packet: bytes) -> dict:
        with self._receive_lock:
            return self._open_verified(packet)

    def _open_verified(self, packet: bytes) -> dict:
        outer = json.loads(packet)
        if outer.get("version") != 1:
            raise ValueError("Unsupported frame version")
        data = self.cipher.decrypt(_unb64(outer["nonce"]), _unb64(outer["ciphertext"]), b"swarm-mesh-v1")
        signed = json.loads(data)
        message = signed["message"]
        sender = int(message["sender"])
        key = self.peers.get(sender)
        if key is None or message.get("version") != 1:
            raise ValueError("Unknown member")
        try:
            key.verify(_unb64(signed["signature"]), _canonical(message))
        except InvalidSignature as exc:
            raise ValueError("Invalid identity signature") from exc
        skew = float(self.clock()) - float(message["time"])
        if not (-5.0 <= skew <= self.max_age_s):
            raise ValueError("Expired or future-dated envelope")
        boot_id = message.get("boot")
        if (not isinstance(boot_id, str) or len(boot_id) != 32
                or any(char not in "0123456789abcdef" for char in boot_id)):
            raise ValueError("Invalid signed process boot identity")
        seq = int(message["seq"])
        if seq < 0:
            raise ValueError("Invalid sequence")
        session = (sender, boot_id)
        highest = self._highest.get(session, -1)
        seen = self._seen.setdefault(session, set())
        if seq <= highest - 128 or seq in seen:
            raise ValueError("Replayed envelope")
        seen.add(seq)
        self._highest[session] = max(highest, seq)
        cutoff = self._highest[session] - 128
        self._seen[session] = {number for number in seen if number > cutoff}
        now = float(self.clock())
        self._sessions_seen_at[session] = now
        # Bound state from obsolete sessions. Valid packets have a maximum age
        # above; no eviction of a live session's replay window is permitted.
        if len(self._sessions_seen_at) > max(32, 8 * len(self.peers)):
            for key, last_seen in list(self._sessions_seen_at.items()):
                if key != session and now - last_seen > 2 * self.max_age_s:
                    self._sessions_seen_at.pop(key, None)
                    self._highest.pop(key, None)
                    self._seen.pop(key, None)
        return message


def _vote_payload(epoch: int, candidate: int) -> bytes:
    return _canonical({"domain": "swarm-election-v1", "epoch": int(epoch), "candidate": int(candidate)})


class MeshNode:
    """A single drone's coordination agent, without a shared global leader state."""

    def __init__(self, identity: SwarmIdentity, roster: Mapping[int, bytes], group_key: bytes,
                 clock: Callable[[], float] = time.time, heartbeat_timeout_s: float = 5.0,
                 max_faults: Optional[int] = None,
                 vote_journal: Optional["VoteJournal"] = None):
        self.identity = identity
        self.node_id = identity.node_id
        self.roster = {int(k): bytes(v) for k, v in roster.items()}
        if self.node_id not in self.roster or len(self.roster) < 4:
            raise ValueError("Quorum-election mode needs at least four registered members, including self")
        self.max_faults = ((len(self.roster) - 1) // 3) if max_faults is None else int(max_faults)
        if self.max_faults < 0 or len(self.roster) < 3 * self.max_faults + 1:
            raise ValueError("Invalid Byzantine fault bound")
        self.quorum = len(self.roster) - self.max_faults
        self.clock = clock
        self.timeout_s = heartbeat_timeout_s
        self.channel = AuthenticatedChannel(identity, self.roster, group_key, clock=clock)
        self.vote_journal = vote_journal
        if vote_journal is not None and vote_journal.node_id != identity.node_id:
            raise ValueError("Vote journal identity mismatch")
        persisted_votes = dict(vote_journal.votes) if vote_journal is not None else {}
        self.epoch = max(persisted_votes, default=0)
        self._min_authority_epoch = self.epoch if persisted_votes else 0
        self.certificate: Optional[ElectionCertificate] = None
        self.leader: Optional[int] = None
        self.last_leader_heartbeat: Optional[float] = None
        self.health: Dict[int, tuple[HealthReport, float]] = {}
        self._suspected_failed_leaders: set[int] = set()
        self.voted_epochs: dict[int, int] = persisted_votes
        self.votes: dict[int, dict[int, tuple[int, str]]] = {}
        self.equivocators: dict[int, set[int]] = {}
        self.issued_certificate_epochs: set[int] = set()
        self.delivered_commands: list[dict] = []
        self.positions: Dict[int, tuple[float, float, float]] = {}
        self.on_command: Optional[Callable[[dict], None]] = None

    def publish_health(self, health: HealthReport, position: Optional[tuple[float, float, float]] = None) -> bytes:
        clean = HealthReport.from_dict(health.to_dict())
        self.health[self.node_id] = (clean, self.clock())
        if self.leader == self.node_id and self.certificate is not None:
            self.last_leader_heartbeat = self.clock()
        payload = {"health": clean.to_dict()}
        if self.certificate is not None:
            payload["certificate"] = self.certificate.to_dict()
        if position is not None:
            pos = tuple(float(x) for x in position)
            if len(pos) != 3 or not all(math.isfinite(x) for x in pos):
                raise ValueError("Position must be finite XYZ")
            payload["position"] = list(pos)
            self.positions[self.node_id] = pos
        return self.channel.seal("heartbeat", self.epoch, payload)

    def has_fresh_quorum(self) -> bool:
        """Only trust a control directive while a fresh registered quorum is visible."""
        now = self.clock()
        return sum(
            1 for member, (_, last_seen) in self.health.items()
            if member in self.roster and 0 <= now - last_seen <= self.timeout_s
        ) >= self.quorum

    def choose_candidate(self) -> Optional[int]:
        eligible = ((node_id, report.score()) for node_id, (report, seen_at) in self.health.items()
                    if node_id in self.roster and node_id not in self._suspected_failed_leaders
                    and self.clock() - seen_at <= self.timeout_s)
        ordered = sorted(eligible, key=lambda x: (-x[1], x[0]))
        return ordered[0][0] if ordered else None

    def _record_vote(self, epoch: int, candidate: int) -> None:
        if self.vote_journal is not None:
            self.vote_journal.cast(epoch, candidate)  # fsync before signing
        previous = self.voted_epochs.get(epoch)
        if previous is not None and previous != candidate:
            raise PermissionError("Refusing same-epoch equivocation")
        self.voted_epochs[epoch] = candidate

    def begin_election(self, candidate: Optional[int] = None) -> bytes:
        next_epoch = max(self.epoch + 1, self._min_authority_epoch)
        selected = self.choose_candidate() if candidate is None else int(candidate)
        if selected not in self.roster or selected in self._suspected_failed_leaders:
            raise ValueError("No eligible registered candidate")
        self._record_vote(next_epoch, selected)
        self.epoch = next_epoch
        self.leader = None
        self.certificate = None
        self.last_leader_heartbeat = None
        signature = _b64(self.identity.private_key.sign(_vote_payload(self.epoch, selected)))
        self._accept_vote(self.epoch, self.node_id, selected, signature)
        return self.channel.seal("vote", self.epoch, {"candidate": selected, "proof": signature})

    def retransmit_vote(self) -> Optional[bytes]:
        """Resend the same signed vote without violating one-vote-per-epoch safety."""
        candidate = self.voted_epochs.get(self.epoch)
        if (candidate is None or self.leader is not None
                or self.epoch < self._min_authority_epoch):
            return None
        signature = _b64(self.identity.private_key.sign(_vote_payload(self.epoch, candidate)))
        return self.channel.seal("vote", self.epoch, {"candidate": candidate, "proof": signature})

    def _accept_vote(self, epoch: int, voter: int, candidate: int, proof: str) -> Optional[bytes]:
        if voter not in self.roster or candidate not in self.roster or epoch < self.epoch:
            return None
        try:
            Ed25519PublicKey.from_public_bytes(self.roster[voter]).verify(
                _unb64(proof), _vote_payload(epoch, candidate))
        except (InvalidSignature, ValueError):
            return None
        ballots = self.votes.setdefault(epoch, {})
        if voter in self.equivocators.setdefault(epoch, set()):
            return None
        prior = ballots.get(voter)
        if prior and prior[0] != candidate:
            self.equivocators[epoch].add(voter)
            del ballots[voter]
            return None
        ballots[voter] = (candidate, proof)
        proof_set = {v: p for v, (c, p) in ballots.items() if c == candidate}
        if len(proof_set) >= self.quorum and epoch not in self.issued_certificate_epochs:
            cert = ElectionCertificate(epoch, candidate, proof_set)
            self.issued_certificate_epochs.add(epoch)
            self._install_certificate(cert)
            return self.channel.seal("certificate", epoch, cert.to_dict())
        return None

    def _verify_certificate(self, cert: ElectionCertificate) -> bool:
        if cert.candidate not in self.roster or len(cert.proofs) < self.quorum:
            return False
        for voter, signature in cert.proofs.items():
            pub = self.roster.get(voter)
            if pub is None:
                return False
            try:
                Ed25519PublicKey.from_public_bytes(pub).verify(
                    _unb64(signature), _vote_payload(cert.epoch, cert.candidate))
            except (ValueError, InvalidSignature):
                return False
        return True

    def _install_certificate(self, cert: ElectionCertificate) -> bool:
        if not self._verify_certificate(cert) or cert.epoch < self._min_authority_epoch:
            return False
        # A valid committed certificate may arrive after a node tentatively
        # advanced an election view without obtaining a certificate. The
        # durable authority fence still prevents resurrecting an expired view.
        if self.certificate is not None and cert.epoch < self.certificate.epoch:
            return False
        if self.certificate and self.certificate.epoch == cert.epoch:
            if self.certificate.candidate != cert.candidate:
                raise ValueError("Conflicting quorum certificates: protocol invariant violated")
            return True  # Replayed certificate is not a fresh leader heartbeat.
        self.epoch = cert.epoch
        self.certificate = cert
        self.leader = cert.candidate
        self.last_leader_heartbeat = self.clock()
        return True

    def receive(self, packet: bytes) -> list[bytes]:
        """Validate a peer packet and return any resulting gossip packets."""
        msg = self.channel.open(packet)
        sender, epoch = int(msg["sender"]), int(msg["epoch"])
        kind, body = msg["kind"], msg["body"]
        if kind == "heartbeat":
            report = HealthReport.from_dict(body["health"])
            if isinstance(body.get("certificate"), dict):
                cert_data = body["certificate"]
                cert = ElectionCertificate(int(cert_data["epoch"]), int(cert_data["candidate"]),
                                           {int(k): str(v) for k, v in cert_data["proofs"].items()})
                self._install_certificate(cert)
            self.health[sender] = (report, self.clock())
            # A previously suspected member can rejoin only as a follower
            # after learning the current certified view and proving its
            # identity with a fresh signed heartbeat from that view.
            if (sender in self._suspected_failed_leaders
                    and self.certificate is not None
                    and sender != self.leader
                    and not self.leader_timed_out()
                    and self.has_fresh_quorum()
                    and epoch == self.certificate.epoch
                    and isinstance(body.get("certificate"), dict)
                    and int(body["certificate"].get("candidate", -1)) == self.leader
                    and int(body["certificate"].get("epoch", -1)) == self.certificate.epoch
                    and -2.0 <= self.clock() - float(msg["time"]) <= 3.0):
                self._suspected_failed_leaders.discard(sender)
            if "position" in body:
                pos = tuple(float(x) for x in body["position"])
                if len(pos) != 3 or not all(math.isfinite(x) for x in pos):
                    raise ValueError("Invalid position telemetry")
                self.positions[sender] = pos
            if sender == self.leader and self.certificate is not None and epoch == self.certificate.epoch:
                self.last_leader_heartbeat = self.clock()
            return []
        if kind == "vote":
            if self.leader_timed_out():
                self.expire_leader()
            if epoch > self.epoch + 1 or epoch < self.epoch:
                return []
            candidate, proof = int(body["candidate"]), str(body["proof"])
            try:
                Ed25519PublicKey.from_public_bytes(self.roster[sender]).verify(
                    _unb64(proof), _vote_payload(epoch, candidate))
            except (InvalidSignature, ValueError):
                return []
            if self.certificate is not None and not self.leader_timed_out() and epoch > self.epoch:
                return []
            if epoch > self.epoch:
                self.epoch = epoch
                self.leader = None
                self.certificate = None
            responses = []
            result = self._accept_vote(epoch, sender, candidate, proof)
            if result is not None:
                responses.append(result)
            if epoch not in self.voted_epochs:
                candidate = self.choose_candidate()
                if candidate is not None:
                    self._record_vote(epoch, candidate)
                    proof = _b64(self.identity.private_key.sign(_vote_payload(epoch, candidate)))
                    generated = self._accept_vote(epoch, self.node_id, candidate, proof)
                    responses.append(self.channel.seal("vote", epoch, {"candidate": candidate, "proof": proof}))
                    if generated is not None:
                        responses.append(generated)
            return responses
        if kind == "certificate":
            cert = ElectionCertificate(epoch=int(body["epoch"]), candidate=int(body["candidate"]),
                                       proofs={int(k): str(v) for k, v in body["proofs"].items()})
            if cert.epoch == epoch:
                self._install_certificate(cert)
            return []
        if kind == "command":
            if self.leader_timed_out():
                self.expire_leader()
            if not self.has_fresh_quorum():
                return []
            cert_data = body.get("certificate")
            if not isinstance(cert_data, dict):
                return []
            cert = ElectionCertificate(int(cert_data["epoch"]), int(cert_data["candidate"]),
                                       {int(k): str(v) for k, v in cert_data["proofs"].items()})
            if (not self._verify_certificate(cert) or sender != cert.candidate or epoch != cert.epoch
                    or epoch < self._min_authority_epoch):
                return []
            if self.certificate and epoch < self.certificate.epoch:
                return []
            if not self._install_certificate(cert):
                return []
            action = body.get("action")
            if isinstance(action, dict):
                record = {"leader": sender, "epoch": epoch, "action": action}
                self.delivered_commands.append(record)
                if self.on_command:
                    self.on_command(record)
            return []
        return []

    def issue_command(self, action: dict) -> bytes:
        if self.leader_timed_out():
            self.expire_leader()
        if self.certificate is None or self.leader != self.node_id:
            raise PermissionError("Only a quorum-certified leader may send commands")
        if not self.has_fresh_quorum():
            raise PermissionError("Cannot command without a fresh registered quorum")
        return self.channel.seal("command", self.epoch,
                                 {"certificate": self.certificate.to_dict(), "action": dict(action)})

    def expire_leader(self) -> None:
        """Fence an expired leader and reject its old certificate and commands."""
        if not self.leader_timed_out():
            return
        expired_leader = self.leader
        self.health.pop(expired_leader, None)
        self._suspected_failed_leaders.add(expired_leader)
        self._min_authority_epoch = max(self._min_authority_epoch, self.epoch + 1)
        self.leader = None
        self.certificate = None
        self.last_leader_heartbeat = None

    def leader_timed_out(self) -> bool:
        return (self.leader is not None and self.last_leader_heartbeat is not None
                and self.clock() - self.last_leader_heartbeat > self.timeout_s)


class InMemoryMesh:
    """Deterministic delivery harness, not a centralized coordination authority."""

    def __init__(self, nodes: list[MeshNode]):
        self.nodes = {node.node_id: node for node in nodes}
        self.blocked: set[tuple[int, int]] = set()

    def broadcast(self, sender: int, packet: bytes, recipients: Optional[list[int]] = None):
        pending = [(sender, packet, recipients)]
        while pending:
            src, wire, targets = pending.pop(0)
            for node_id in (targets if targets is not None else list(self.nodes)):
                if node_id == src or (src, node_id) in self.blocked:
                    continue
                outputs = self.nodes[node_id].receive(wire)
                pending.extend((node_id, out, None) for out in outputs)
