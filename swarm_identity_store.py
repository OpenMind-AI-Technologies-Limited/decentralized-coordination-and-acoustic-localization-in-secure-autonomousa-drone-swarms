"""Single-writer local Ed25519 identity and crash-safe election vote journal.

The private key is stored in a POSIX 0600 file (Windows filesystem ACLs remain
an operator responsibility). Files use atomic replace with fsync on writes.

This is an opt-in simulation/prototype store, not a hardware-backed keystore or
a distributed enrollment service. Never put this directory under version control.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import threading

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

from swarm_mesh import SwarmIdentity


def _safe_root(path: str | os.PathLike) -> Path:
    root = Path(path)
    if root.is_symlink():
        raise ValueError("Refusing symlinked identity directory")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir():
        raise ValueError("Identity path is not a directory")
    if os.name == "posix":
        root.chmod(0o700)
    return root


def _load_json(path: Path) -> dict | None:
    if path.is_symlink():
        raise ValueError("Refusing symlinked state file")
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("State path must be a regular file")
    if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise PermissionError("Secret file must not be accessible by group or others")
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError("Invalid persisted state object")
    return value


def _atomic_json(path: Path, value: dict) -> None:
    if path.is_symlink():
        raise ValueError("Refusing symlinked state file")
    root = _safe_root(path.parent)
    file_path = None
    try:
        descriptor, file_path = tempfile.mkstemp(prefix=".mesh-", suffix=".tmp", dir=str(root))
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            if os.name == "posix":
                os.chmod(file_path, 0o600)
            json.dump(value, file, sort_keys=True, separators=(",", ":"))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(file_path, path)
        file_path = None
        if os.name == "posix":
            directory_fd = os.open(str(root), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if file_path is not None:
            try:
                os.unlink(file_path)
            except FileNotFoundError:
                pass


class IdentityStore:
    """Creates or retrieves the same local Ed25519 identity after restart."""

    def __init__(self, directory: str | os.PathLike):
        self.directory = _safe_root(directory)
        self._lock = threading.RLock()

    def load_or_create(self, node_id: int) -> SwarmIdentity:
        node_id = int(node_id)
        if node_id < 1:
            raise ValueError("Node ID must be positive")
        with self._lock:
            path = self.directory / f"node-{node_id}.json"
            data = _load_json(path)
            if data is None:
                private = Ed25519PrivateKey.generate()
                raw = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
                _atomic_json(path, {"version": 1, "node_id": node_id, "private_key_hex": raw.hex()})
                return SwarmIdentity(node_id, private)
            if data.get("version") != 1 or data.get("node_id") != node_id:
                raise ValueError("Persisted identity does not match expected node")
            raw = bytes.fromhex(str(data["private_key_hex"]))
            if len(raw) != 32:
                raise ValueError("Ed25519 private key must be 32 bytes")
            return SwarmIdentity(node_id, Ed25519PrivateKey.from_private_bytes(raw))


class VoteJournal:
    """Persist local ballot choices before signing; one writer per node directory."""

    def __init__(self, directory: str | os.PathLike, identity: SwarmIdentity):
        self.directory = _safe_root(directory)
        self.node_id = identity.node_id
        self._public_hex = identity.public_bytes().hex()
        self.path = self.directory / f"votes-{self.node_id}.json"
        self._lock = threading.RLock()
        existing = _load_json(self.path)
        if existing is None:
            self.votes: dict[int, int] = {}
        else:
            if (existing.get("version") != 1 or existing.get("node_id") != self.node_id
                    or existing.get("public_key_hex") != self._public_hex):
                raise ValueError("Vote journal belongs to another identity")
            self.votes = {int(epoch): int(candidate) for epoch, candidate in existing["votes"].items()}
            if any(epoch < 1 or candidate < 1 for epoch, candidate in self.votes.items()):
                raise ValueError("Invalid persisted vote entry")

    def cast(self, epoch: int, candidate: int) -> None:
        epoch, candidate = int(epoch), int(candidate)
        if epoch < 1 or candidate < 1:
            raise ValueError("Invalid election vote")
        with self._lock:
            old = self.votes.get(epoch)
            if old is not None:
                if old != candidate:
                    raise PermissionError("Cannot vote twice for different leaders in one epoch")
                return
            # Prevent an older view from being signed after a later one.
            if self.votes and epoch < max(self.votes):
                raise PermissionError("Cannot sign a vote for a retired election epoch")
            updated = {**self.votes, epoch: candidate}
            _atomic_json(self.path, {
                "version": 1,
                "node_id": self.node_id,
                "public_key_hex": self._public_hex,
                "votes": {str(key): value for key, value in updated.items()},
            })
            self.votes = updated
