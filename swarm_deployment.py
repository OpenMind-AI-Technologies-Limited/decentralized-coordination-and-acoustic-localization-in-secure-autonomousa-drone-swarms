"""Provision and run independent fixed-membership swarm research nodes.

Only inert simulated telemetry and callback logging are exposed. This CLI never
imports MAVSDK, arms a drone, or connects to physical flight hardware.

Usage:
    python swarm_deployment.py provision --out /tmp/swarm --members 4 --port 33000
    python swarm_deployment.py run --node /tmp/swarm/member-1 --duration 20
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from typing import Optional, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

from swarm_identity_store import IdentityStore, VoteJournal, _atomic_json, _load_json, _safe_root
from swarm_mesh import HealthReport, MeshNode
from swarm_runtime import MeshRuntime
from swarm_transport import UdpPeerTransport


def _roster_digest(roster: dict) -> str:
    return hashlib.sha256(json.dumps(
        roster, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def provision_members(root: str | os.PathLike, count: int, first_port: int,
                      host: str = "127.0.0.1",
                      ports: Optional[Sequence[int]] = None) -> list[Path]:
    """Create immutable local credential bundles for a fixed registered fleet."""
    if not 4 <= count <= 50:
        raise ValueError("Requires 4–50 registered members")
    port_list = ([first_port + i for i in range(count)]
                 if ports is None else [int(port) for port in ports])
    if len(port_list) != count or len(set(port_list)) != count or any(
        port < 1024 or port > 65535 for port in port_list
    ):
        raise ValueError("Requires distinct unprivileged UDP ports")
    # Local loopback is deliberate: opening remote sockets requires an
    # operator to provision a trusted network and firewall first.
    if host != "127.0.0.1":
        raise ValueError("Prototype provisioner is restricted to 127.0.0.1")
    root_path = Path(root)
    if root_path.exists() and any(root_path.iterdir()):
        raise FileExistsError("Refuse to overwrite deployed membership or private keys")
    _safe_root(root_path)
    directories = [root_path / f"member-{i}" for i in range(1, count + 1)]
    identities = {i: IdentityStore(directories[i - 1]).load_or_create(i)
                  for i in range(1, count + 1)}
    roster = {str(i): identities[i].public_bytes().hex() for i in identities}
    digest = _roster_digest(roster)
    group_key = os.urandom(32).hex()
    addresses = {str(i): [host, port_list[i - 1]] for i in identities}
    authority = Ed25519PrivateKey.generate()
    authority_pub = authority.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    authority_priv = authority.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    # Authority private key stays in root; copy only each member directory
    # to its assigned peer. Never publish or distribute this signing key.
    _atomic_json(root_path / "operator-authority.json", {
        "version": 1, "private_key_hex": authority_priv, "public_key_hex": authority_pub
    })
    for i, directory in enumerate(directories, start=1):
        record = {
            "version": 1, "node_id": i, "roster": roster,
            "roster_sha256": digest, "group_key_hex": group_key,
            "addresses": addresses, "battery": 100.0 - i,
            "motor_health": 100.0, "link_quality": 95.0,
            "position": [float(i * 20), 0.0, 10.0],
            "authority_pub_hex": authority_pub,
        }
        content = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        record["membership_signature_hex"] = authority.sign(content).hex()
        _atomic_json(directory / "member.json", record)
    _atomic_json(root_path / "public-roster.json", {
        "version": 1, "roster": roster, "roster_sha256": digest,
        "addresses": addresses,
    })
    return directories


def load_member(directory: str | os.PathLike):
    node_dir = Path(directory)
    record = _load_json(node_dir / "member.json")
    if record is None or record.get("version") != 1:
        raise ValueError("Missing member configuration")
    signature_hex = record.pop("membership_signature_hex", None)
    if not isinstance(signature_hex, str):
        raise ValueError("Member configuration lacks operator signature")
    authority_hex = str(record.get("authority_pub_hex", ""))
    pinned = os.environ.get("SWARM_MESH_AUTHORITY_PUB_HEX", "").strip().lower()
    if pinned and authority_hex != pinned:
        raise PermissionError("Operator public key differs from pinned trust anchor")
    try:
        content = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(authority_hex)).verify(
            bytes.fromhex(signature_hex), content)
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise ValueError("Invalid operator membership signature") from exc
    identity = IdentityStore(node_dir).load_or_create(int(record["node_id"]))
    roster = {int(i): bytes.fromhex(public) for i, public in record["roster"].items()}
    if (_roster_digest(record["roster"]) != record["roster_sha256"] or
            roster.get(identity.node_id) != identity.public_bytes()):
        raise ValueError("Untrusted or modified membership roster")
    if len(roster) < 4 or len(roster) > 50 or len(set(roster)) != len(roster):
        raise ValueError("Invalid roster size")
    addresses = {int(i): (str(a[0]), int(a[1]))
                 for i, a in record["addresses"].items()}
    if set(addresses) != set(roster):
        raise ValueError("Member address map and roster must match")
    if any(host != "127.0.0.1" or not 1 <= port <= 65535
           for host, port in addresses.values()):
        raise ValueError("Only loopback addresses supported by this prototype")
    if len({address for address in addresses.values()}) != len(addresses):
        raise ValueError("Duplicate member UDP address")
    key = bytes.fromhex(record["group_key_hex"])
    if len(key) != 32:
        raise ValueError("Invalid shared transport key")
    position = tuple(float(x) for x in record["position"])
    if len(position) != 3:
        raise ValueError("Invalid position")
    health = HealthReport.from_dict({
        "battery": record["battery"],
        "motor_health": record["motor_health"],
        "link_quality": record["link_quality"],
    })
    journal = VoteJournal(node_dir, identity)
    node = MeshNode(identity, roster, key, vote_journal=journal,
                    heartbeat_timeout_s=1.5)
    return node, addresses, health, position


def run_member(directory: str | os.PathLike, duration_s: float = 20.0) -> dict:
    """Execute exactly one independent UDP member in this operating-system process."""
    if not 0.1 <= duration_s <= 3600:
        raise ValueError("Duration must be between 0.1 and 3600 seconds")
    directory = Path(directory)
    node, addresses, health, position = load_member(directory)
    transport = UdpPeerTransport(node.node_id, addresses[node.node_id])
    transport.configure_peers({i: addr for i, addr in addresses.items() if i != node.node_id})
    commands = []
    runtime = MeshRuntime(
        node, transport,
        health_provider=lambda: (health, position),
        command_handler=lambda action: commands.append(action),
        heartbeat_interval_s=0.12,
        election_retry_s=0.65,
    )
    runtime.start()
    initial_time = time.monotonic()
    snapshot = {}
    try:
        while time.monotonic() - initial_time < duration_s:
            snapshot = {
                "node_id": node.node_id, "pid": os.getpid(),
                "leader": node.leader, "epoch": node.epoch,
                "quorum": node.quorum, "has_certificate": node.certificate is not None,
                "fresh_quorum": node.has_fresh_quorum(),
                "commands": len(commands),
                "uptime_seconds": round(time.monotonic() - initial_time, 3),
            }
            _atomic_json(directory / "status.json", snapshot)
            time.sleep(0.15)
        return snapshot
    finally:
        runtime.stop()
        _atomic_json(directory / "status.json",
                     {**snapshot, "running": False})


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Loopback-only swarm peer laboratory")
    command = parser.add_subparsers(dest="command", required=True)
    provision = command.add_parser("provision", help="Generate fixed trusted member bundles")
    provision.add_argument("--out", required=True)
    provision.add_argument("--members", type=int, default=4)
    provision.add_argument("--port", type=int, default=33000)
    run = command.add_parser("run", help="Run one registered member in this process")
    run.add_argument("--node", required=True)
    run.add_argument("--duration", type=float, default=20)
    args = parser.parse_args(argv)
    if args.command == "provision":
        dirs = provision_members(args.out, args.members, args.port)
        print(json.dumps({"members": [str(d) for d in dirs], "mode": "loopback-only"}))
    else:
        print(json.dumps(run_member(args.node, args.duration)))


if __name__ == "__main__":
    main()
