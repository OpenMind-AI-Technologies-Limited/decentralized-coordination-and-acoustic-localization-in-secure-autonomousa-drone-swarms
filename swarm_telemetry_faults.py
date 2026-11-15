"""Seeded adversarial telemetry + network fault injection for research Step 4.

This module exercises real Ed25519/AES-GCM MeshNode packet verification, then
compares the unmodified allocator and experimental evidence gate on the SAME
coordinator-visible observations. A separate offline oracle holds simulated
truth; no aircraft, RF network, trustworthy sensor or physical attack is used.

All scenarios are diagnostic/experimental-design fixtures, NOT a publication-
scale efficacy study. Bootstrap/quorum establishment uses a fault-free in-memory
mesh; network faults are injected only during the later telemetry update phase.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
import os
import random
from typing import Optional

from cryptography.exceptions import InvalidTag

from swarm_consistency_gate import ConsistencyPolicy, consistency_gated_allocate, sign_witness
from swarm_mesh import HealthReport, InMemoryMesh, MeshNode, SwarmIdentity
from swarm_tasks import allocate_tasks


SCENARIOS = (
    "healthy_control",
    "stale_position",
    "signed_false_health",
    "signed_position_spoof",
    "bounded_slow_drift",
    "honest_witnesses",
    "malicious_witness",
    "colluding_witnesses",
    "no_independent_witnesses",
    "packet_loss",
    "partition",
    "delayed_update",
    "tampered_packet",
)


@dataclass(frozen=True)
class FaultCase:
    scenario: str
    seed: int
    nodes: int = 5
    packet_loss: float = 0.0

    def __post_init__(self):
        if self.scenario not in SCENARIOS:
            raise ValueError("Unknown fault scenario")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("Seed must be an integer")
        if not isinstance(self.nodes, int) or not 4 <= self.nodes <= 50:
            raise ValueError("Swarm size must be 4..50")
        if not math.isfinite(self.packet_loss) or not 0 <= self.packet_loss < 1:
            raise ValueError("Invalid packet loss")


class ManualClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class FaultNetwork:
    """Deterministic packet scheduler with real authenticated receiver.

    Noise/corruption and drop/partition are applied only to network packets
    originating from legitimate registered members. Trace contains no secret
    keys, signed ciphertext or personally identifying data.
    """
    def __init__(self, receiver: MeshNode, clock: ManualClock, seed: int):
        self.receiver = receiver
        self.clock = clock
        self.rng = random.Random(seed)
        self.queue = []
        self.serial = 0
        self.events = []

    def send(self, *, source: int, packet: bytes, reason: str,
             packet_loss: float = 0.0, partition: bool = False,
             force_drop: bool = False, delay_s: Optional[float] = None,
             tamper: bool = False) -> None:
        if source == self.receiver.node_id:
            raise ValueError("Use local publish for coordinator self")
        if not 0 <= packet_loss < 1:
            raise ValueError("Invalid loss rate")
        event = {
            "source": source, "destination": self.receiver.node_id,
            "kind": "signed_heartbeat", "reason": reason,
            "bytes": len(packet), "sent_virtual_s": round(self.clock.now, 6),
        }
        if partition or force_drop or self.rng.random() < packet_loss:
            event.update({"outcome": "dropped",
                          "drop_cause": "partition" if partition else
                                        "injected_loss" if force_drop else "seeded_loss"})
            self.events.append(event)
            return
        if delay_s is None:
            delay_s = self.rng.uniform(0.001, 0.016)
        if not math.isfinite(delay_s) or delay_s < 0:
            raise ValueError("Invalid delay")
        if tamper:
            wire = bytearray(packet)
            wire[len(wire)//2] ^= 1
            packet = bytes(wire)
            event["corrupted_in_transit"] = True
        self.serial += 1
        arrival = self.clock.now + delay_s
        heapq.heappush(self.queue, (arrival, self.serial, packet, event))

    def drain(self, *, until: Optional[float] = None) -> None:
        while self.queue and (until is None or self.queue[0][0] <= until):
            at, _, wire, event = heapq.heappop(self.queue)
            self.clock.now = max(self.clock.now, at)
            event["received_virtual_s"] = round(self.clock.now, 6)
            try:
                self.receiver.receive(wire)
            except (InvalidTag, ValueError, KeyError, TypeError, OverflowError):
                event["outcome"] = "rejected_by_crypto_or_protocol"
            else:
                event["outcome"] = "authenticated_delivered"
            self.events.append(event)


def _assignee(allocations: dict) -> Optional[int]:
    assigned = sorted(int(member) for member, entries in allocations.items() if entries)
    if len(assigned) > 1:
        raise AssertionError("Step 4 diagnostic uses one requested task")
    return assigned[0] if assigned else None


def _offered_health(nodes: int) -> dict[int, HealthReport]:
    return {i: HealthReport(90., 100., 95.) for i in range(1, nodes+1)}


def _scene_positions(nodes: int) -> dict[int, tuple[float, float, float]]:
    return {
        i: (60., 0., 10.) if i == 1 else
           (0., 0., 10.) if i == 2 else
           (100. + 20. * (i-3), 0., 10.)
        for i in range(1, nodes+1)
    }


def _observed_by_witnesses(*, case: FaultCase, identities: dict,
                           truth_health: dict, claimed_health: dict,
                           observed_time: float, epoch: int) -> dict:
    """Generate separately signed synthetic sensor claims.

    This is an explicitly idealized measurement model, not a real sensor.
    Signed witnesses have **no** hard-to-forge attestation of physical truth.
    """
    mode = case.scenario
    if mode not in ("honest_witnesses", "malicious_witness",
                    "colluding_witnesses"):
        return {}
    evidence = {}
    for subject in sorted(identities):
        reporters = ([3, 4] if subject == 2 else
                     [i for i in sorted(identities) if i != subject][:2])
        signed = []
        for reporter in reporters:
            report = truth_health[subject]
            if subject == 2 and (
                mode == "colluding_witnesses" or
                mode == "malicious_witness" and reporter == 3):
                # A legitimate registered witness intentionally lies.
                report = (claimed_health[2] if mode == "colluding_witnesses"
                          else HealthReport(15., 60., 50.))
            signed.append(sign_witness(
                identities[reporter], subject_id=subject, epoch=epoch,
                observed_at=observed_time, health=report))
        evidence[subject] = signed
    return evidence


def run_fault_case(case: FaultCase) -> dict:
    """Run one source-verified, seeded diagnostic episode.

    The offline position/health oracle is never passed to the allocator.
    No physical trajectory or real-world message timing is measured.
    """
    rng = random.Random(case.seed)
    clock = ManualClock()
    identities = {i: SwarmIdentity(i) for i in range(1, case.nodes+1)}
    roster = {i: identity.public_bytes() for i, identity in identities.items()}
    group_key = os.urandom(32)
    nodes = {i: MeshNode(identity, roster, group_key, clock=clock,
                         heartbeat_timeout_s=20.0)
             for i, identity in identities.items()}
    bootstrap = InMemoryMesh(list(nodes.values()))

    coords = _scene_positions(case.nodes)
    true_positions = dict(coords)
    true_health = _offered_health(case.nodes)
    claimed_health = _offered_health(case.nodes)
    if case.scenario in ("signed_false_health", "honest_witnesses",
                         "colluding_witnesses", "no_independent_witnesses"):
        true_health[2] = HealthReport(15., 60., 50.)
        claimed_health[2] = HealthReport(99., 100., 99.)
    if case.scenario in ("signed_position_spoof", "bounded_slow_drift"):
        # Receiver sees a signed false coordinate near the task.
        # True location is held by the independent offline evaluation oracle.
        true_positions[2] = (80., 0., 10.)

    # Fault-free bootstrap: every MeshNode receives genuine signed, encrypted
    # initial reports. Election gets a registered quorum before the attack.
    for member in sorted(nodes):
        bootstrap.broadcast(member,
                            nodes[member].publish_health(
                                claimed_health[member], coords[member]))
    ballots = [(member, nodes[member].begin_election(candidate=1))
               for member in sorted(nodes)]
    for sender, packet in ballots:
        bootstrap.broadcast(sender, packet)
    leader = nodes[1]
    if leader.leader != 1 or leader.certificate is None:
        raise AssertionError("Failed to establish certified leader before fault injection")

    network = FaultNetwork(leader, clock, case.seed + 3109)
    old_position_age_expected = False

    if case.scenario == "bounded_slow_drift":
        # 2 m per simulated second is under the default max-speed bound.
        # Ground truth stays at 80 m while self-signed reports drift to 6 m.
        # No independent witness exists: this is an intentional blind spot.
        for tick in (1, 2, 3):
            clock.now = 1000. + tick
            coords[2] = (float(tick*2), 0., 10.)
            packet = nodes[2].publish_health(claimed_health[2], coords[2])
            network.send(source=2, packet=packet, reason="gradual_signed_position_drift")
            network.drain()
    else:
        clock.now = 1007.0 if case.scenario in (
            "stale_position", "packet_loss", "partition",
            "delayed_update", "tampered_packet") else 1001.0
        if case.scenario in ("stale_position", "packet_loss", "partition",
                             "delayed_update", "tampered_packet"):
            # 80 m over 7 s is a plausible 11.4 m/s virtual movement,
            # not an instant 220 m teleport.
            true_positions[2] = (80., 0., 10.)
            old_position_age_expected = True

        for member in sorted(nodes):
            if member == 1:
                leader.publish_health(claimed_health[member], coords[member])
                continue
            position = (None if member == 2 and
                        case.scenario == "stale_position" else
                        true_positions[2] if member == 2 and
                        case.scenario in ("packet_loss", "partition",
                                          "delayed_update", "tampered_packet")
                        else coords[member])
            packet = nodes[member].publish_health(claimed_health[member], position)
            network.send(
                source=member, packet=packet, reason="post_bootstrap_telemetry",
                packet_loss=case.packet_loss,
                force_drop=(member == 2 and case.scenario == "packet_loss"),
                partition=(member == 2 and case.scenario == "partition"),
                delay_s=(5.0 if member == 2 and case.scenario == "delayed_update"
                         else None),
                tamper=(member == 2 and case.scenario == "tampered_packet"),
            )
        network.drain(until=(1007.05 if case.scenario == "delayed_update" else None))

    reported_health = {
        member: report for member, (report, seen) in leader.health.items()
        if 0 <= clock.now - seen <= leader.timeout_s
    }
    reported_positions = {
        member: leader.positions[member] for member in reported_health
        if member in leader.positions
    }
    tasks = {"inspection-001": (1., 0., 10.)}
    witness_map = _observed_by_witnesses(
        case=case, identities=identities, truth_health=true_health,
        claimed_health=claimed_health, observed_time=clock.now,
        epoch=leader.epoch,
    )

    baseline = allocate_tasks(reported_positions, reported_health, tasks)
    age_gate = consistency_gated_allocate(
        positions=reported_positions, health=reported_health,
        health_seen_at={i:stamp for i, (_,stamp) in leader.health.items()},
        position_seen_at=leader.positions_seen_at,
        previous_positions=leader.previous_positions,
        now=clock.now, tasks=tasks, roster=roster, epoch=leader.epoch,
        policy=ConsistencyPolicy(),
    )
    strict_gate = consistency_gated_allocate(
        positions=reported_positions, health=reported_health,
        health_seen_at={i:stamp for i, (_,stamp) in leader.health.items()},
        position_seen_at=leader.positions_seen_at,
        previous_positions=leader.previous_positions,
        now=clock.now, tasks=tasks, roster=roster, epoch=leader.epoch,
        policy=ConsistencyPolicy(min_health_witnesses=2),
        witnesses=witness_map,
    )
    oracle = allocate_tasks(true_positions, true_health, tasks)
    oracle_member = _assignee(oracle)

    def decision_info(allocations: dict, *, per_member: Optional[dict] = None) -> dict:
        member = _assignee(allocations)
        known_good = (member is not None and
                      true_health[member].battery >= 30 and
                      true_health[member].motor_health >= 75 and
                      true_health[member].link_quality >= 40)
        return {
            "assignee": member,
            "truth_ineligible": member is not None and not known_good,
            "disagrees_with_offline_oracle": member != oracle_member,
            "unassigned_tasks": int(member is None),
            "reason_node_2": (per_member or {}).get(2, {}).get("reason"),
        }

    traces = sorted(network.events, key=lambda x: (
        x["sent_virtual_s"], x["source"], x["reason"]))
    old_position_age = clock.now - leader.positions_seen_at[2]
    stats = {
        "sent": len(network.events) + len(network.queue),
        "authenticated_delivered": sum(e.get("outcome")=="authenticated_delivered"
                                       for e in network.events),
        "rejected": sum(e.get("outcome")=="rejected_by_crypto_or_protocol"
                        for e in network.events),
        "dropped": sum(e.get("outcome")=="dropped" for e in network.events),
        "pending_delay": len(network.queue),
        "transmitted_bytes": sum(e["bytes"] for e in network.events) +
                             sum(p[3]["bytes"] for p in network.queue),
    }
    return {
        "scenario": case.scenario, "seed": case.seed, "nodes": case.nodes,
        "packet_loss_configured": case.packet_loss,
        "scope": "seeded_software_fault_injection_not_field_measurement",
        "signed_authenticated_bootstrap": True,
        "signed_quorum_certified_before_attack": True,
        "quorum_fresh_at_decision": leader.has_fresh_quorum(),
        "leader": leader.leader,
        "oracle_assignee_offline": oracle_member,
        "baseline": decision_info(baseline),
        "age_only": decision_info(age_gate["allocations"],
                                  per_member=age_gate["decisions"]),
        "witness_strict": decision_info(strict_gate["allocations"],
                                       per_member=strict_gate["decisions"]),
        "witnesses_available": bool(witness_map),
        "witness_assumptions": (
            "idealized_two_peer_observations_with_possible_malicious_reporters"
            if witness_map else "no_independent_observation"),
        "compromised_witness_count": (
            2 if case.scenario == "colluding_witnesses" else
            1 if case.scenario == "malicious_witness" else 0),
        "declared_byzantine_fault_budget": (case.nodes-1)//3,
        "old_position_age_expected": old_position_age_expected,
        "coordinator_member_2_position_age_s": round(old_position_age, 4),
        "coordinator_member_2_reported_position": list(leader.positions[2]),
        "oracle_member_2_position_offline": list(true_positions[2]),
        # Exact shared observed input for fair comparator replay. These are
        # member-local, signed/verified receiver snapshots, not model truth.
        "comparison_input": {
            "decision_virtual_s": clock.now,
            "tasks": {task_id: list(target) for task_id, target in tasks.items()},
            "reported_positions": {str(i): list(xyz) for i, xyz in reported_positions.items()},
            "reported_health": {str(i): h.to_dict() for i, h in reported_health.items()},
            "health_seen_at": {str(i): leader.health[i][1] for i in reported_health},
            "position_seen_at": {str(i): leader.positions_seen_at[i] for i in reported_positions},
            "age_gate_decisions": {str(i): detail for i, detail in age_gate["decisions"].items()},
            "witness_gate_decisions": {str(i): detail for i, detail in strict_gate["decisions"].items()},
        },
        # Explicitly segregated OFFLINE oracle: never provided to a method.
        "comparison_offline_truth": {
            "positions": {str(i): list(p) for i, p in true_positions.items()},
            "health": {str(i): h.to_dict() for i, h in true_health.items()},
        },
        "network": stats,
        "network_events": traces,
        "physical_uav_flight": False,
        "real_sensor_measurements": False,
    }
