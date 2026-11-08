#########################################################################
#                                                                       #
#   SECURE DRONE SWARM SYSTEM - CORE MODULE                             #
#                                                                       #
#   Developer : Md Shahanur Islam Shagor                                #
#   Role      : Project Architect & Lead Developer                      #
#   Version   : 1.0.2                                                   #
#   Status    : Production Ready                                        #
#                                                                       #
#   "Protecting the skies with decentralized intelligence."             #
#                                                                       #
#########################################################################
from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def _stable_serialize(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha3_hex(payload: bytes) -> str:
    return hashlib.sha3_256(payload).hexdigest()


@dataclass
class Block:
    index: int
    timestamp: float
    drone_id: str
    telemetry_hash: str
    event_hash: str
    previous_hash: str
    block_hash: str
    signature: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Block":
        return Block(
            index=int(data["index"]),
            timestamp=float(data["timestamp"]),
            drone_id=str(data["drone_id"]),
            telemetry_hash=str(data["telemetry_hash"]),
            event_hash=str(data["event_hash"]),
            previous_hash=str(data["previous_hash"]),
            block_hash=str(data["block_hash"]),
            signature=str(data["signature"]),
        )


class SignatureProvider:
    """Abstraction layer for post-quantum-ready signature swapping."""

    algorithm_name = "unknown"

    def sign(self, message: bytes) -> str:
        raise NotImplementedError

    def verify(self, public_key_bytes: bytes, message: bytes, signature: str) -> bool:
        raise NotImplementedError

    def public_key_bytes(self) -> bytes:
        raise NotImplementedError


class Ed25519SignatureProvider(SignatureProvider):
    algorithm_name = "ed25519"

    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._private_key = private_key or ed25519.Ed25519PrivateKey.generate()

    def sign(self, message: bytes) -> str:
        signature = self._private_key.sign(message)
        return f"{self.algorithm_name}:{base64.b64encode(signature).decode('ascii')}"

    def verify(self, public_key_bytes: bytes, message: bytes, signature: str) -> bool:
        try:
            algo, raw = signature.split(":", 1)
            if algo.strip().lower() != self.algorithm_name:
                return False
            sig = base64.b64decode(raw.encode("ascii"))
            pub = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            pub.verify(sig, message)
            return True
        except Exception:
            return False

    def public_key_bytes(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )


class FlyingLedger:
    """Per-drone append-only flight ledger with asynchronous replication."""

    def __init__(
        self,
        drone_id: str,
        signature_provider: SignatureProvider,
        broadcaster: Optional[Callable[[dict], None]] = None,
        peer_public_keys: Optional[Dict[str, bytes]] = None,
    ):
        self.drone_id = str(drone_id)
        self.signature_provider = signature_provider
        self.broadcaster = broadcaster
        self.peer_public_keys: Dict[str, bytes] = dict(peer_public_keys or {})
        self.chain: List[Block] = []
        self.replicated_blocks_by_drone: Dict[str, List[Block]] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger(f"FlyingLedger_Drone{self.drone_id}")
        self._create_genesis_block()

    def _create_genesis_block(self):
        with self._lock:
            if self.chain:
                return
            telemetry_hash = _sha3_hex(_stable_serialize({"genesis": True}))
            event_hash = _sha3_hex(_stable_serialize({"event": "GENESIS"}))
            block_hash = self.compute_block_hash(
                index=0,
                timestamp=0.0,
                drone_id="swarm",
                telemetry_hash=telemetry_hash,
                event_hash=event_hash,
                previous_hash="0",
            )
            signature = self.signature_provider.sign(block_hash.encode("utf-8"))
            genesis = Block(
                index=0,
                timestamp=0.0,
                drone_id="swarm",
                telemetry_hash=telemetry_hash,
                event_hash=event_hash,
                previous_hash="0",
                block_hash=block_hash,
                signature=signature,
            )
            self.chain.append(genesis)
            self.replicated_blocks_by_drone.setdefault(self.drone_id, []).append(genesis)

    @staticmethod
    def compute_block_hash(
        index: int,
        timestamp: float,
        drone_id: str,
        telemetry_hash: str,
        event_hash: str,
        previous_hash: str,
    ) -> str:
        payload = (
            f"{int(index)}|{float(timestamp):.9f}|{drone_id}|{telemetry_hash}|{event_hash}|{previous_hash}"
        ).encode("utf-8")
        return _sha3_hex(payload)

    def set_peer_public_keys(self, peer_public_keys: Dict[str, bytes]):
        with self._lock:
            self.peer_public_keys = dict(peer_public_keys)

    def block_height(self) -> int:
        with self._lock:
            return len(self.chain) - 1

    def append_local_event(self, telemetry_snapshot: dict, event_payload: dict) -> Block:
        telemetry_hash = _sha3_hex(_stable_serialize(telemetry_snapshot))
        event_hash = _sha3_hex(_stable_serialize(event_payload))
        with self._lock:
            tail = self.chain[-1]
            index = tail.index + 1
            timestamp = time.time()
            block_hash = self.compute_block_hash(
                index=index,
                timestamp=timestamp,
                drone_id=self.drone_id,
                telemetry_hash=telemetry_hash,
                event_hash=event_hash,
                previous_hash=tail.block_hash,
            )
            signature = self.signature_provider.sign(block_hash.encode("utf-8"))
            block = Block(
                index=index,
                timestamp=timestamp,
                drone_id=self.drone_id,
                telemetry_hash=telemetry_hash,
                event_hash=event_hash,
                previous_hash=tail.block_hash,
                block_hash=block_hash,
                signature=signature,
            )
            self.chain.append(block)
            self.replicated_blocks_by_drone.setdefault(self.drone_id, []).append(block)

        if self.broadcaster:
            threading.Thread(target=self._broadcast_block_safe, args=(block,), daemon=True).start()
        return block

    def _broadcast_block_safe(self, block: Block):
        try:
            self.broadcaster(block.to_dict())
        except Exception as exc:
            self.logger.warning("Ledger broadcast failed: %s", exc)

    def verify_block(self, block: Block) -> bool:
        with self._lock:
            tail = self.chain[-1]
            if block.index != (tail.index + 1):
                return False
            if block.previous_hash != tail.block_hash:
                return False

            expected_hash = self.compute_block_hash(
                index=block.index,
                timestamp=block.timestamp,
                drone_id=block.drone_id,
                telemetry_hash=block.telemetry_hash,
                event_hash=block.event_hash,
                previous_hash=block.previous_hash,
            )
            if expected_hash != block.block_hash:
                return False

            pub = self.peer_public_keys.get(block.drone_id)
            if not pub:
                return False
            return self.signature_provider.verify(pub, block.block_hash.encode("utf-8"), block.signature)

    def append_replicated_block(self, block_data: dict) -> bool:
        try:
            block = Block.from_dict(block_data)
        except (KeyError, TypeError, ValueError, OverflowError):
            return False
        # Atomic check-then-append: concurrent replicas must not both attach
        # blocks to the same parent or silently extend a fork.
        with self._lock:
            if not self.verify_block(block):
                return False
            self.chain.append(block)
            self.replicated_blocks_by_drone.setdefault(block.drone_id, []).append(block)
        return True

    def integrity_ok(self) -> bool:
        with self._lock:
            if not self.chain:
                return False
            for i in range(1, len(self.chain)):
                prev = self.chain[i - 1]
                block = self.chain[i]
                if block.index != prev.index + 1 or block.previous_hash != prev.block_hash:
                    return False
                expected_hash = self.compute_block_hash(
                    index=block.index,
                    timestamp=block.timestamp,
                    drone_id=block.drone_id,
                    telemetry_hash=block.telemetry_hash,
                    event_hash=block.event_hash,
                    previous_hash=block.previous_hash,
                )
                if expected_hash != block.block_hash:
                    return False
                author_key = self.peer_public_keys.get(block.drone_id)
                if not author_key or not self.signature_provider.verify(
                    author_key, block.block_hash.encode("utf-8"), block.signature
                ):
                    return False
        return True
