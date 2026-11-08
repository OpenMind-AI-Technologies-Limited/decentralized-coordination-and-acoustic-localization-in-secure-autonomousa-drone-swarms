"""Quorum audit log: signed commits, equivocation, crash-safe locks, catch-up."""
import copy
import os
import tempfile
import unittest
from unittest import mock

from quorum_audit import QuorumAuditLedger
from swarm_mesh import ElectionCertificate, SwarmIdentity, _vote_payload, _b64


class AuditLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ids = [SwarmIdentity(i) for i in range(1, 5)]
        self.roster = {identity.node_id: identity.public_bytes() for identity in self.ids}
        self.logs = [QuorumAuditLedger(identity, self.roster) for identity in self.ids]

    def certificate(self, epoch=1, candidate=1):
        signed = {
            ident.node_id: _b64(ident.private_key.sign(_vote_payload(epoch, candidate)))
            for ident in self.ids[:3]
        }
        return ElectionCertificate(epoch, candidate, signed).to_dict()

    def create_record(self, event=None):
        proposal = self.logs[0].propose(event or {"kind": "formation", "x": 2}, self.certificate())
        votes = [ledger.vote(proposal) for ledger in self.logs[:3]]
        return proposal, votes

    def test_majority_commit_matches_tip_on_all_replicas(self):
        proposal, votes = self.create_record()
        self.assertEqual(self.logs[0].height, 0)  # Voting is not a commit.
        for log in self.logs:
            self.assertTrue(log.commit(proposal, votes))
        self.assertTrue(all(x.height == 1 for x in self.logs))
        self.assertTrue(all(x.consistent_with(self.logs[0]) for x in self.logs))
        self.assertTrue(self.logs[1].commit(proposal, votes))  # Idempotent replay.
        forged = copy.deepcopy(votes)
        forged[0]["signature_hex"] = "00" * 64
        self.assertFalse(self.logs[1].commit(proposal, forged))

    def test_no_quorum_and_forged_vote_rejected(self):
        proposal, votes = self.create_record()
        self.assertFalse(self.logs[0].commit(proposal, votes[:2]))
        tampered = copy.deepcopy(votes)
        tampered[0]["signature_hex"] = "00" * 64
        self.assertFalse(self.logs[0].commit(proposal, tampered))
        self.assertEqual(self.logs[0].height, 0)

    def test_conflicting_proposal_rejected_at_same_height_across_epochs(self):
        first, _ = self.create_record()
        alternative = self.logs[0].propose({"kind": "different"}, self.certificate(2, 1))
        with self.assertRaises(PermissionError):
            self.logs[1].vote(alternative)
        self.assertNotEqual(first["hash"], alternative["hash"])

    def test_invalid_author_signature_and_wrong_parent_rejected(self):
        proposal, _ = self.create_record()
        tampered = copy.deepcopy(proposal)
        tampered["event"]["x"] = 999
        with self.assertRaises(ValueError):
            self.logs[3].vote(tampered)
        tampered = copy.deepcopy(proposal)
        tampered["parent"] = "0" * 64
        with self.assertRaises(ValueError):
            self.logs[3].vote(tampered)

    def test_offline_replica_catches_up_only_from_certified_records(self):
        proposal, votes = self.create_record()
        for log in self.logs[:3]:
            self.assertTrue(log.commit(proposal, votes))
        self.assertEqual(self.logs[3].height, 0)
        self.assertEqual(self.logs[3].synchronize(self.logs[0].commits), 1)
        self.assertTrue(self.logs[3].consistent_with(self.logs[0]))

    def test_durable_votes_and_commit_recover_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = QuorumAuditLedger(self.ids[0], self.roster, store_directory=tmp)
            proposal = first.propose({"inspection": "A"}, self.certificate())
            first.vote(proposal)
            reopened = QuorumAuditLedger(self.ids[0], self.roster, store_directory=tmp)
            self.assertEqual(reopened.locked_height[1], proposal["hash"])
            invalid = first.propose({"inspection": "B"}, self.certificate(2))
            with self.assertRaises(PermissionError):
                reopened.vote(invalid)
            votes = [
                first.vote(proposal),
                self.logs[1].vote(proposal),
                self.logs[2].vote(proposal),
            ]
            self.assertTrue(first.commit(proposal, votes))
            recovered = QuorumAuditLedger(self.ids[0], self.roster, store_directory=tmp)
            self.assertEqual(recovered.height, 1)
            self.assertEqual(recovered.tip, proposal["hash"])

    def test_fail_closed_on_vote_journal_write_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = QuorumAuditLedger(self.ids[0], self.roster, store_directory=tmp)
            proposal = ledger.propose({"kind": "audit"}, self.certificate())
            with mock.patch("quorum_audit._atomic_json", side_effect=OSError("disk unavailable")):
                with self.assertRaises(OSError):
                    ledger.vote(proposal)
            self.assertEqual(ledger.locked_height, {})

    def test_static_membership_requires_certified_leader(self):
        invalid_cert = self.certificate(candidate=2)
        with self.assertRaises(PermissionError):
            self.logs[0].propose({"kind": "audit"}, invalid_cert)


if __name__ == "__main__":
    unittest.main()
