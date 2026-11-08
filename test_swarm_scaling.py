"""Deterministic fixed-membership election and partition scaling regressions.

These tests verify quorum certificate mechanics under synthetic timing,
not full Byzantine view-change proofs or physical UAV convergence times.
"""
import os
import unittest

from swarm_mesh import HealthReport, InMemoryMesh, MeshNode, SwarmIdentity


def make_mesh(count):
    identities = [SwarmIdentity(i) for i in range(1, count + 1)]
    roster = {ident.node_id: ident.public_bytes() for ident in identities}
    group_key = os.urandom(32)
    nodes = [MeshNode(ident, roster, group_key) for ident in identities]
    network = InMemoryMesh(nodes)
    for rank, node in enumerate(nodes):
        network.broadcast(node.node_id, node.publish_health(
            HealthReport(100 - rank * 0.1, 100, 100)))
    return nodes, network


class ElectionScaleTests(unittest.TestCase):
    def test_mixed_healthy_and_dissenting_ballots_preserve_quorum(self):
        for count in (4, 7, 10):
            with self.subTest(nodes=count):
                nodes, network = make_mesh(count)
                f = (count - 1) // 3
                self.assertEqual(nodes[0].quorum, count - f)
                ballots = [
                    (node.node_id, node.begin_election(candidate=(2 if index < f else 1)))
                    for index, node in enumerate(nodes)
                ]
                for source, packet in ballots:
                    network.broadcast(source, packet)
                for node in nodes:
                    self.assertEqual(node.leader, 1)
                    self.assertGreaterEqual(len(node.certificate.proofs), count - f)
                    self.assertTrue(node._verify_certificate(node.certificate))

    def test_subquorum_partition_cannot_elect(self):
        count = 7
        nodes, network = make_mesh(count)
        cohort_a = set(range(1, 4))
        cohort_b = set(range(4, 8))
        network.blocked = {(a, b) for a in cohort_a for b in cohort_b} | {
            (b, a) for a in cohort_a for b in cohort_b
        }
        ballots = [(node.node_id, node.begin_election(candidate=1)) for node in nodes]
        for source, packet in ballots:
            network.broadcast(source, packet)
        self.assertTrue(all(node.certificate is None for node in nodes))
        self.assertTrue(all(node.leader is None for node in nodes))

    def test_twenty_member_known_peer_election(self):
        nodes, network = make_mesh(20)
        ballots = [(n.node_id, n.begin_election(candidate=1)) for n in nodes]
        for source, packet in ballots:
            network.broadcast(source, packet)
        self.assertTrue(all(n.leader == 1 for n in nodes))
        self.assertTrue(all(n._verify_certificate(n.certificate) for n in nodes))


if __name__ == "__main__":
    unittest.main()
