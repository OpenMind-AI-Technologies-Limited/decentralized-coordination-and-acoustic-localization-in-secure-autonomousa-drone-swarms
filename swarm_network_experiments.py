"""Seeded packet-level quorum experiments using production MeshNode crypto.

All packet delay and drop events use a deterministic virtual network. These
are SOFTWARE experiments, not measured RF latency or physical UAV behavior.
"""
from __future__ import annotations

import heapq
import os
import random
import time
from swarm_mesh import HealthReport, MeshNode, SwarmIdentity, _b64, _vote_payload

SCENARIOS = ("healthy", "packet_loss", "byzantine_withholding",
             "byzantine_equivocation", "tampered_packets",
             "quorum_partition", "minority_partition", "leader_failure")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class VirtualNetwork:
    def __init__(self, agents, clock, rng, loss=0.0, blocked=None, silent=None):
        self.agents, self.clock, self.rng = agents, clock, rng
        self.loss = loss
        self.blocked = blocked or set()
        self.silent = silent or set()
        self.queue = []
        self.serial = 0
        self.sent = self.delivered = self.dropped = self.rejected = 0
        self.bytes_sent = self.bytes_delivered = 0

    def send(self, source, packet, recipients=None):
        for target in (sorted(self.agents) if recipients is None else recipients):
            if target == source or target not in self.agents:
                continue
            self.sent += 1
            self.bytes_sent += len(packet)
            if ((source, target) in self.blocked or target in self.silent
                    or self.rng.random() < self.loss):
                self.dropped += 1
                continue
            self.serial += 1
            delay_ms = self.rng.uniform(1, 12)
            heapq.heappush(self.queue,
                           (self.clock.now + delay_ms/1000, self.serial,
                            source, target, packet))

    def drain(self):
        processed = 0
        while self.queue:
            processed += 1
            if processed > 200000:
                raise RuntimeError("Packet amplification bound exceeded")
            arrival, _, _, target, packet = heapq.heappop(self.queue)
            self.clock.now = max(arrival, self.clock.now)
            try:
                responses = self.agents[target].receive(packet)
            except Exception:
                self.rejected += 1
                continue
            self.delivered += 1
            self.bytes_delivered += len(packet)
            for reply in responses:
                self.send(target, reply)

    def counters(self):
        return {"packets_sent": self.sent, "packets_delivered": self.delivered,
                "packets_dropped": self.dropped, "packets_rejected": self.rejected,
                "wire_bytes_sent": self.bytes_sent,
                "wire_bytes_delivered": self.bytes_delivered}


def run_election_trial(nodes, seed, scenario, *, loss_rate=0.15):
    """Execute a genuine signed quorum election through synthetic packet delivery."""
    if not 4 <= nodes <= 50 or scenario not in SCENARIOS:
        raise ValueError("Invalid experiment topology")
    if not 0 <= loss_rate < 1:
        raise ValueError("Invalid packet loss fraction")
    rng, clock = random.Random(int(seed)), Clock()
    identities = {i: SwarmIdentity(i) for i in range(1, nodes+1)}
    roster = {i: identity.public_bytes() for i, identity in identities.items()}
    key = os.urandom(32)
    agents = {i: MeshNode(identity, roster, key, clock=clock)
              for i, identity in identities.items()}
    f = (nodes - 1) // 3
    q = nodes - f
    malicious = (set(range(nodes-f+1, nodes+1))
                 if scenario.startswith("byzantine") else set())
    n_split = (nodes//2 if scenario == "minority_partition" else
               f if scenario == "quorum_partition" else 0)
    blocked = (
        {(a, b) for a in range(1, n_split+1)
         for b in range(n_split+1, nodes+1)}
        | {(b, a) for a in range(1, n_split+1)
           for b in range(n_split+1, nodes+1)}
    ) if n_split else set()
    net = VirtualNetwork(agents, clock, rng,
                         loss=loss_rate if scenario == "packet_loss" else 0.0,
                         blocked=blocked, silent=malicious)
    t0, wall0 = clock.now, time.perf_counter()
    for i, agent in agents.items():
        packet = agent.publish_health(HealthReport(
            battery=95 - 0.1*i, motor_health=95, link_quality=90))
        net.send(i, packet)
    net.drain()
    voters = sorted(set(agents) - malicious)
    ballots = []
    for i in voters:
        candidate = agents[i].choose_candidate()
        if candidate is not None:
            ballots.append((i, agents[i].begin_election(candidate)))
    for i, packet in ballots:
        net.send(i, packet)

    if scenario == "byzantine_equivocation":
        for i in sorted(malicious):
            agent = agents[i]
            for candidate in (2, 3):
                signature = _b64(agent.identity.private_key.sign(
                    _vote_payload(1, candidate)))
                net.send(i, agent.channel.seal("vote", 1, {
                    "candidate": candidate, "proof": signature}))
    if scenario == "tampered_packets":
        agent = agents[1]
        signature = _b64(agent.identity.private_key.sign(_vote_payload(1, 1)))
        raw = bytearray(agent.channel.seal(
            "vote", 1, {"candidate": 1, "proof": signature}))
        raw[len(raw)//2] ^= 1
        net.send(1, bytes(raw))
    net.drain()
    if scenario == "packet_loss":
        for _ in range(3):
            for i in voters:
                message = agents[i].retransmit_vote()
                if message is not None:
                    net.send(i, message)
            net.drain()
            for i in voters:
                agent = agents[i]
                net.send(i, agent.publish_health(agent.health[i][0]))
            net.drain()

    if scenario == "leader_failure" and agents[1].leader == 1:
        clock.now += agents[2].timeout_s + 0.2
        # A stopped member cannot send stale certificates or receive gossip.
        net.blocked |= {(1, i) for i in range(2, nodes+1)}
        net.blocked |= {(i, 1) for i in range(2, nodes+1)}
        for i in range(2, nodes+1):
            agents[i].expire_leader()
        for i in range(2, nodes+1):
            agent = agents[i]
            net.send(i, agent.publish_health(
                HealthReport(95-0.1*i, 95, 90)),
                recipients=list(range(2, nodes+1)))
        net.drain()
        for i in range(2, nodes+1):
            net.send(i, agents[i].begin_election(candidate=2),
                     recipients=list(range(2, nodes+1)))
        net.drain()

    for i in voters:
        agent = agents[i]
        if (scenario != "leader_failure" or i != 1) and agent.certificate is not None:
            net.send(i, agent.publish_health(agent.health[i][0]))
    net.drain()
    live = set(voters)
    if scenario == "leader_failure":
        live.discard(1)
    if scenario == "quorum_partition":
        live -= set(range(1, n_split+1))
    expected = (None if scenario == "minority_partition" else
                n_split + 1 if scenario == "quorum_partition" else
                2 if scenario == "leader_failure" else 1)
    certificates = {
        i: (agents[i].certificate.epoch, agents[i].leader)
        for i in live if agents[i].certificate is not None
    }
    epoch_leaders = {}
    for epoch, leader in certificates.values():
        epoch_leaders.setdefault(epoch, set()).add(leader)
    conflict = any(len(leaders) > 1 for leaders in epoch_leaders.values())
    converged = (not certificates if expected is None else
                 all(i in certificates and certificates[i][1] == expected
                     for i in live))
    return {
        "family": "election", "scenario": scenario, "nodes": nodes,
        "seed": int(seed), "fault_budget": f, "quorum": q,
        "faults_injected": len(malicious),
        "converged": converged,
        "same_epoch_conflict": conflict,
        "certified_honest_nodes": len(certificates),
        "honest_nodes_considered": len(live),
        "detected_equivocations": sum(
            len(a.equivocators.get(1, ())) for a in agents.values()),
        "virtual_time_ms": round((clock.now-t0)*1000, 3),
        "harness_wall_ms": round((time.perf_counter()-wall0)*1000, 3),
        **net.counters(),
    }
