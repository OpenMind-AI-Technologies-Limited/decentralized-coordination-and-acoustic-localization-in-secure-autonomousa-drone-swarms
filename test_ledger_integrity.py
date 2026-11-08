"""Legacy FlyingLedger signature/fork/concurrency regression tests."""
from concurrent.futures import ThreadPoolExecutor
import unittest

from flying_ledger import Ed25519SignatureProvider, FlyingLedger


class LegacyLedgerIntegrityTests(unittest.TestCase):
    def setUp(self):
        a, b = Ed25519SignatureProvider(), Ed25519SignatureProvider()
        keys = {"1": a.public_key_bytes(), "2": b.public_key_bytes()}
        self.origin = FlyingLedger("1", a, peer_public_keys=keys)
        self.replica = FlyingLedger("2", b, peer_public_keys=keys)

    def test_valid_replication_and_signature_mutation_detection(self):
        block = self.origin.append_local_event({"battery": 88}, {"kind": "telemetry"})
        self.assertTrue(self.replica.append_replicated_block(block.to_dict()))
        self.assertTrue(self.replica.integrity_ok())
        self.replica.chain[1].signature = "ed25519:AAAAAAAA"
        self.assertFalse(self.replica.integrity_ok())

    def test_concurrent_replication_cannot_extend_same_parent_twice(self):
        block = self.origin.append_local_event({"signal": 91}, {"kind": "status"}).to_dict()
        with ThreadPoolExecutor(max_workers=8) as pool:
            successes = list(pool.map(self.replica.append_replicated_block, [block] * 16))
        self.assertEqual(sum(successes), 1)
        self.assertEqual(self.replica.block_height(), 1)
        self.assertTrue(self.replica.integrity_ok())

    def test_tampered_signature_and_competing_child_rejected(self):
        block = self.origin.append_local_event({"x": 1}, {"kind": "capture"}).to_dict()
        tampered = dict(block)
        tampered["signature"] = "ed25519:AAAA"
        self.assertFalse(self.replica.append_replicated_block(tampered))
        self.assertTrue(self.replica.append_replicated_block(block))
        self.assertFalse(self.replica.append_replicated_block(block))


if __name__ == "__main__":
    unittest.main()
