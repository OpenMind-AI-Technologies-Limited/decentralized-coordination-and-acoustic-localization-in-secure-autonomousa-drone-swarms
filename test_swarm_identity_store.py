"""Persistence, crash recovery, journal fencing, and local secret file tests."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from swarm_identity_store import IdentityStore, VoteJournal
from swarm_mesh import HealthReport, MeshNode


class IdentityPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "mesh-state"
        self.store = IdentityStore(self.directory)

    def test_identity_is_stable_across_restarts(self):
        first = self.store.load_or_create(5)
        second = IdentityStore(self.directory).load_or_create(5)
        self.assertEqual(first.public_bytes(), second.public_bytes())
        self.assertNotEqual(first.public_bytes(), self.store.load_or_create(6).public_bytes())

    def test_identity_rejects_tampering_and_cross_node_file(self):
        identity = self.store.load_or_create(5)
        path = self.directory / "node-5.json"
        body = json.loads(path.read_text(encoding="utf-8"))
        body["node_id"] = 6
        path.write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.store.load_or_create(5)

    @unittest.skipUnless(os.name == "posix", "POSIX filesystem mode check")
    def test_identity_files_restrict_group_read(self):
        self.store.load_or_create(1)
        file_path = self.directory / "node-1.json"
        self.assertEqual(stat.S_IMODE(file_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        file_path.chmod(0o644)
        with self.assertRaises(PermissionError):
            self.store.load_or_create(1)

    def test_rejects_directory_symlink(self):
        target = Path(self.tmp.name) / "actual"
        target.mkdir()
        link = Path(self.tmp.name) / "shortcut"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("Platform cannot create symlinks")
        with self.assertRaises(ValueError):
            IdentityStore(link)


class BallotJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.identity = IdentityStore(self.root).load_or_create(1)

    def test_ballot_choice_survives_restart_and_rejects_equivocation(self):
        journal = VoteJournal(self.root, self.identity)
        journal.cast(1, 2)
        reopened = VoteJournal(self.root, self.identity)
        reopened.cast(1, 2)  # Identical vote may be retransmitted
        with self.assertRaises(PermissionError):
            reopened.cast(1, 3)
        with self.assertRaises(PermissionError):
            reopened.cast(0, 2)
        reopened.cast(2, 3)
        with self.assertRaises(PermissionError):
            reopened.cast(1, 2)  # Old view cannot be re-signed

    def test_write_failure_does_not_mark_vote_cast(self):
        journal = VoteJournal(self.root, self.identity)
        with patch("swarm_identity_store._atomic_json", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                journal.cast(1, 2)
        self.assertEqual(journal.votes, {})

    def test_journal_pinned_to_identity(self):
        journal = VoteJournal(self.root, self.identity)
        journal.cast(1, 2)
        different = IdentityStore(self.root).load_or_create(2)
        with self.assertRaises(ValueError):
            # Deliberately loading node-1's vote record with node-2 identity.
            moved = self.root / "votes-2.json"
            moved.write_bytes((self.root / "votes-1.json").read_bytes())
            VoteJournal(self.root, different)

    def test_restart_preserves_vote_epoch_fence(self):
        journal = VoteJournal(self.root, self.identity)
        roster_identities = {1: self.identity}
        for node_id in (2, 3, 4):
            roster_identities[node_id] = IdentityStore(self.root).load_or_create(node_id)
        roster = {node_id: identity.public_bytes() for node_id, identity in roster_identities.items()}
        first = MeshNode(self.identity, roster, os.urandom(32), vote_journal=journal)
        first.publish_health(HealthReport(95, 100, 99))
        first.begin_election(candidate=2)
        resumed = MeshNode(self.identity, roster, os.urandom(32),
                           vote_journal=VoteJournal(self.root, self.identity))
        self.assertEqual(resumed.epoch, 1)
        self.assertEqual(resumed._min_authority_epoch, 1)
        self.assertEqual(resumed.voted_epochs[1], 2)
        resumed.publish_health(HealthReport(95, 100, 99))
        resumed.begin_election(candidate=3)
        self.assertEqual(VoteJournal(self.root, self.identity).votes, {1: 2, 2: 3})

    def test_unwritable_vote_cannot_produce_ballot(self):
        journal = VoteJournal(self.root, self.identity)
        roster_identities = {i: IdentityStore(self.root).load_or_create(i) for i in range(1, 5)}
        roster = {i: ident.public_bytes() for i, ident in roster_identities.items()}
        node = MeshNode(self.identity, roster, os.urandom(32), vote_journal=journal)
        node.publish_health(HealthReport(90, 90, 90))
        with patch.object(journal, "cast", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                node.begin_election()
        self.assertEqual(node.epoch, 0)
        self.assertEqual(node.voted_epochs, {})


if __name__ == "__main__":
    unittest.main()
