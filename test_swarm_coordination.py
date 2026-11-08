"""Quorum, replay, network partition, formation and peer UDP integration tests."""
import base64
import math
import os
import time
import unittest

from swarm_mesh import (AuthenticatedChannel, ElectionCertificate, HealthReport,
                        InMemoryMesh, MeshNode, SwarmIdentity, _vote_payload)
from swarm_formation import formation_target, separate_from_neighbors
from swarm_transport import UdpPeerTransport
from swarm_runtime import MeshRuntime


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class MeshTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.ids = [SwarmIdentity(i) for i in range(1, 5)]
        self.roster = {ident.node_id: ident.public_bytes() for ident in self.ids}
        self.secret = os.urandom(32)
        self.nodes = [MeshNode(i, self.roster, self.secret, clock=self.clock) for i in self.ids]
        self.network = InMemoryMesh(self.nodes)
        reports = [HealthReport(90, 100, 90), HealthReport(70, 90, 80),
                   HealthReport(65, 70, 90), HealthReport(55, 70, 80)]
        for node, health in zip(self.nodes, reports):
            self.network.broadcast(node.node_id, node.publish_health(health))

    def elect_all(self):
        packets = [(node.node_id, node.begin_election()) for node in self.nodes]
        for sender, packet in packets:
            self.network.broadcast(sender, packet)

    def test_code_aligned_mcss_weighting(self):
        self.assertAlmostEqual(HealthReport(100, 0, 0).score(), 0.45)
        self.assertEqual({n.choose_candidate() for n in self.nodes}, {1})

    def test_quorum_certified_election_four_nodes(self):
        self.elect_all()
        for node in self.nodes:
            self.assertEqual(node.leader, 1)
            self.assertEqual(node.quorum, 3)
            self.assertTrue(node._verify_certificate(node.certificate))

    def test_leader_command_and_replay_guard(self):
        self.elect_all()
        packet = self.nodes[0].issue_command({"kind": "hold", "target": [5, 10]})
        self.network.broadcast(1, packet)
        for follower in self.nodes[1:]:
            self.assertEqual(len(follower.delivered_commands), 1)
            with self.assertRaises(ValueError):
                follower.receive(packet)

    def test_non_leader_cannot_issue_command(self):
        self.elect_all()
        with self.assertRaises(PermissionError):
            self.nodes[1].issue_command({"kind": "takeoff"})

    def test_unknown_member_and_corrupt_ciphertext_rejected(self):
        attacker = SwarmIdentity(99)
        outsider_roster = {**self.roster, 99: attacker.public_bytes()}
        sender = AuthenticatedChannel(attacker, outsider_roster, self.secret, clock=self.clock)
        with self.assertRaises(ValueError):
            self.nodes[0].receive(sender.seal("heartbeat", 0, {"health": HealthReport(80, 80, 80).to_dict()}))
        wire = self.nodes[1].publish_health(HealthReport(80, 80, 80))
        with self.assertRaises((ValueError, KeyError)):
            self.nodes[0].receive(wire[:-10] + b"aaaaaaaaaa")

    def test_partition_does_not_authorize_election(self):
        self.network.blocked = {(a, b) for a in (1, 2) for b in (3, 4)} | \
                               {(a, b) for a in (3, 4) for b in (1, 2)}
        self.elect_all()
        for node in self.nodes:
            self.assertIsNone(node.leader)
            self.assertIsNone(node.certificate)

    def test_forged_certificate_rejected(self):
        self.elect_all()
        valid = self.nodes[0].certificate
        forged = ElectionCertificate(valid.epoch + 1, 4, valid.proofs)
        self.assertFalse(self.nodes[1]._install_certificate(forged))
        self.assertEqual(self.nodes[1].leader, 1)

    def test_stale_health_not_eligible(self):
        self.clock.now += 7
        self.assertIsNone(self.nodes[0].choose_candidate())

    def test_leader_heartbeat_timeout(self):
        self.elect_all()
        self.clock.now += 6
        self.assertTrue(self.nodes[1].leader_timed_out())
        self.clock.now -= 1.5
        self.assertFalse(self.nodes[1].leader_timed_out())

    def test_partition_expiry_revokes_quorum_command_authority(self):
        self.elect_all()
        # The leader may remain healthy locally; its peers have disappeared.
        self.clock.now += 6.0
        self.nodes[0].publish_health(HealthReport(90, 100, 90))
        self.assertFalse(self.nodes[0].has_fresh_quorum())
        with self.assertRaises(PermissionError):
            self.nodes[0].issue_command({"kind": "formation", "pattern": "v"})

    def test_delayed_old_command_is_rejected_after_authority_fenced(self):
        self.elect_all()
        delayed = self.nodes[0].issue_command({"kind": "goto", "target_xyz": [5, 5, 10]})
        self.clock.now += 6.0
        follower = self.nodes[1]
        follower.expire_leader()
        self.assertIsNone(follower.leader)
        follower.receive(delayed)
        self.assertEqual(follower.delivered_commands, [])
        self.assertIsNone(follower.leader)

    def test_failed_leader_cannot_reenter_recovery_vote_from_late_telemetry(self):
        self.elect_all()
        self.clock.now += 7.0
        follower = self.nodes[1]
        follower.expire_leader()
        self.assertIn(1, follower._suspected_failed_leaders)
        # A delayed or replayed signed health report must not re-enable a
        # previously expired leader as candidate in the recovery view.
        packet = self.nodes[0].publish_health(HealthReport(99, 100, 100))
        follower.receive(packet)
        follower.publish_health(HealthReport(80, 90, 80))
        self.assertEqual(follower.choose_candidate(), 2)
        with self.assertRaises(ValueError):
            follower.begin_election(candidate=1)

    def test_equivocation_is_detected(self):
        voter = self.nodes[3]
        first = voter.begin_election(candidate=1)
        proof = base64.b64encode(voter.identity.private_key.sign(_vote_payload(1, 2))).decode("ascii")
        alternate = voter.channel.seal("vote", 1, {"candidate": 2, "proof": proof})
        self.nodes[0].begin_election()
        self.nodes[0].receive(first)
        self.nodes[0].receive(alternate)
        self.assertIn(4, self.nodes[0].equivocators[1])
        self.assertNotIn(4, self.nodes[0].votes[1])


class ElectionConvergenceTests(unittest.TestCase):
    def test_late_certificate_converges_after_tentative_view_advance(self):
        # Simulate an election certificate arriving only after a lagging node
        # tentatively moves to the next epoch (common under packet reordering).
        clock = FakeClock()
        identities = [SwarmIdentity(i) for i in range(1, 5)]
        roster = {ident.node_id: ident.public_bytes() for ident in identities}
        key = os.urandom(32)
        nodes = [MeshNode(ident, roster, key, clock=clock) for ident in identities]
        network = InMemoryMesh(nodes)
        for index, node in enumerate(nodes):
            network.broadcast(node.node_id, node.publish_health(HealthReport(95 - 10*index, 90, 90)))
        election = [(n.node_id, n.begin_election(candidate=1)) for n in nodes]
        for source, packet in election:
            network.broadcast(source, packet)
        self.assertEqual([node.leader for node in nodes], [1] * 4)

        clock.now += 7.0
        for node in nodes:
            node.expire_leader()
        for node in nodes[1:]:
            network.broadcast(node.node_id, node.publish_health(HealthReport(80, 90, 90)))
        election = [(n.node_id, n.begin_election(candidate=2)) for n in nodes[1:]]
        # Node 4 becomes impatient before seeing the committed epoch 2.
        nodes[3].begin_election(candidate=2)
        self.assertEqual(nodes[3].epoch, 3)
        for sender, packet in election:
            network.broadcast(sender, packet)
        self.assertEqual([node.leader for node in nodes[1:]], [2, 2, 2])
        self.assertTrue(all(n.certificate.epoch == 2 for n in nodes[1:]))


class AuthorityLeaseTests(unittest.TestCase):
    def make_nodes(self):
        clock = FakeClock()
        identities = [SwarmIdentity(i) for i in range(1, 5)]
        roster = {i.node_id: i.public_bytes() for i in identities}
        key = os.urandom(32)
        nodes = [MeshNode(i, roster, key, clock=clock) for i in identities]
        network = InMemoryMesh(nodes)
        for rank, node in enumerate(nodes):
            network.broadcast(node.node_id, node.publish_health(HealthReport(90 - rank*10, 80, 80)))
        packets = [(node.node_id, node.begin_election()) for node in nodes]
        for sender, packet in packets:
            network.broadcast(sender, packet)
        return clock, nodes, network

    def test_local_leader_heartbeat_renewal(self):
        clock, nodes, network = self.make_nodes()
        self.assertEqual(nodes[0].leader, 1)
        clock.now += 4.0
        nodes[0].publish_health(HealthReport(90, 80, 80))
        clock.now += 2.0
        self.assertFalse(nodes[0].leader_timed_out())

    def test_malicious_premature_epoch_vote_does_not_displace_live_leader(self):
        clock, nodes, network = self.make_nodes()
        self.assertEqual(nodes[1].leader, 1)
        compromised = nodes[3]
        proof = base64.b64encode(compromised.identity.private_key.sign(_vote_payload(2, 4))).decode("ascii")
        packet = compromised.channel.seal("vote", 2, {"candidate": 4, "proof": proof})
        nodes[1].receive(packet)
        self.assertEqual(nodes[1].leader, 1)
        self.assertEqual(nodes[1].epoch, 1)


class FormationTests(unittest.TestCase):
    def test_leader_remains_at_origin(self):
        self.assertEqual(formation_target(1, 1, [1, 2, 3, 4], [2, 3, 30], [1, 0]), (2, 3, 30))

    def test_v_is_symmetric(self):
        a = formation_target(2, 1, [1, 2, 3, 4], [0, 0, 10], [1, 0], "v", 15)
        b = formation_target(3, 1, [1, 2, 3, 4], [0, 0, 10], [1, 0], "v", 15)
        self.assertEqual(a[0], b[0])
        self.assertEqual(a[1], -b[1])
        self.assertGreaterEqual(math.dist(a, b), 15)

    def test_all_formation_types(self):
        for pattern in ("line", "v", "circle", "grid"):
            targets = [formation_target(i, 1, range(1, 10), [0, 0, 12], [0, 1], pattern, 14)
                       for i in range(1, 10)]
            self.assertEqual(len(set(targets)), len(targets))
            self.assertTrue(all(math.isfinite(v) for target in targets for v in target))

    def test_separation_corrects_near_collision(self):
        corrected = separate_from_neighbors(1, [20, 0, 10], {1: [0, 0, 10], 2: [1, 0, 10]})
        self.assertLess(corrected[0], 20)

    def test_coincident_nodes_separate_oppositely(self):
        positions = {1: [0, 0, 10], 2: [0, 0, 10]}
        self.assertLess(separate_from_neighbors(1, [0, 0, 10], positions)[0], 0)
        self.assertGreater(separate_from_neighbors(2, [0, 0, 10], positions)[0], 0)

    def test_far_neighbors_leave_target_unchanged(self):
        self.assertEqual(separate_from_neighbors(1, (3, 4, 5),
                         {1: (0, 0, 10), 2: (100, 0, 10)}), (3, 4, 5))


class TransportTests(unittest.TestCase):
    def test_udp_delivery(self):
        left = UdpPeerTransport(1, ("127.0.0.1", 0))
        right = UdpPeerTransport(2, ("127.0.0.1", 0))
        try:
            left.configure_peers({2: right.address})
            packet = os.urandom(128)
            left.send(packet)
            self.assertEqual(right.receive(1.0), packet)
        finally:
            left.close()
            right.close()

    def test_reject_unknown_destination(self):
        transport = UdpPeerTransport(1, ("127.0.0.1", 0))
        try:
            with self.assertRaises(ValueError):
                transport.send(b"x", recipient=2)
            with self.assertRaises(ValueError):
                transport.send(b"")
        finally:
            transport.close()


class RuntimeIntegrationTests(unittest.TestCase):
    def test_independent_udp_agents_elect_and_follow(self):
        identities = [SwarmIdentity(i) for i in range(1, 5)]
        roster = {i.node_id: i.public_bytes() for i in identities}
        group_key = os.urandom(32)
        transports = [UdpPeerTransport(i.node_id, ("127.0.0.1", 0)) for i in identities]
        received = [[] for _ in range(4)]
        runtimes = []
        try:
            for transport in transports:
                transport.configure_peers({t.node_id: t.address for t in transports if t != transport})
            for j, ident in enumerate(identities):
                node = MeshNode(ident, roster, group_key, heartbeat_timeout_s=2.0)
                report = HealthReport(95 - 10*j, 99, 90)
                position = (j * 20.0, 0.0, 10.0)
                runtime = MeshRuntime(node, transports[j],
                                      health_provider=lambda h=report, p=position: (h, p),
                                      command_handler=lambda a, idx=j: received[idx].append(a),
                                      heartbeat_interval_s=0.1, election_retry_s=0.7)
                runtimes.append(runtime)
            for runtime in runtimes:
                runtime.start()
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline and not all(rt.node.leader == 1 for rt in runtimes):
                time.sleep(0.05)
            self.assertEqual([rt.node.leader for rt in runtimes], [1, 1, 1, 1])
            runtimes[0].broadcast_action({"kind": "formation", "pattern": "v",
                                          "leader_position": [0.0, 0.0, 10.0],
                                          "heading": [1.0, 0.0], "spacing_m": 12.0})
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not all(received[j] for j in range(1, 4)):
                time.sleep(0.05)
            for j in range(1, 4):
                self.assertEqual(received[j][0]["kind"], "goto")
                self.assertEqual(len(received[j][0]["target_xyz"]), 3)
        finally:
            for runtime in runtimes:
                runtime.stop()
            for transport in transports:
                transport.close()


class RecoveryTests(unittest.TestCase):
    def test_crashed_leader_is_replaced_by_three_survivors(self):
        identities = [SwarmIdentity(i) for i in range(1, 5)]
        roster = {i.node_id: i.public_bytes() for i in identities}
        key = os.urandom(32)
        transports = [UdpPeerTransport(i.node_id, ("127.0.0.1", 0)) for i in identities]
        runtimes = []
        try:
            for transport in transports:
                transport.configure_peers({p.node_id: p.address for p in transports if p != transport})
            for j, ident in enumerate(identities):
                report = HealthReport(99 - 10*j, 90, 90)
                node = MeshNode(ident, roster, key, heartbeat_timeout_s=1.0)
                runtime = MeshRuntime(node, transports[j],
                                      health_provider=lambda h=report: (h, (0.0, 0.0, 10.0)),
                                      heartbeat_interval_s=0.12, election_retry_s=0.5)
                runtimes.append(runtime)
                runtime.start()
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline and not all(rt.node.leader == 1 for rt in runtimes):
                time.sleep(0.05)
            self.assertTrue(all(rt.node.leader == 1 for rt in runtimes))
            runtimes[0].stop()
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not all(rt.node.leader == 2 for rt in runtimes[1:]):
                time.sleep(0.05)
            self.assertEqual([rt.node.leader for rt in runtimes[1:]], [2, 2, 2])
        finally:
            for runtime in runtimes:
                runtime.stop()
            for transport in transports:
                transport.close()


if __name__ == "__main__":
    unittest.main()
