"""Deterministic Step 2 baseline probes against signed MeshNode and command_tasks.

These are intentional demonstrations of the CURRENT unmodified decision logic.
Do not interpret them as prevalence estimates or physical attack outcomes.
"""
import hashlib
import json
import tempfile
from pathlib import Path
import unittest

from consistency_gated_step2_probe import run_all, run_case, write_evidence


class SignedTelemetryAllocationBaselineTests(unittest.TestCase):
    def test_healthy_control_matches_offline_oracle(self):
        row = run_case("healthy_control")
        self.assertEqual(row["signed_quorum_leader"], 1)
        self.assertTrue(row["registered_member_signed"])
        self.assertTrue(row["recorded_audit_intent"])
        self.assertEqual(row["actual_assignee"], 2)
        self.assertEqual(row["offline_oracle_assignee"], 2)
        self.assertFalse(row["assignment_disagreement"])
        self.assertFalse(row["actual_assignee_truth_ineligible"])
        self.assertFalse(row["physical_flight_performed"])

    def test_signed_fresh_health_with_old_xyz_changes_allocation(self):
        row = run_case("stale_position")
        self.assertEqual(row["signed_quorum_leader"], 1)
        self.assertEqual(row["health_age_s_member_2"], 0.0)
        self.assertEqual(row["position_age_s_member_2_harness_only"], 7.0)
        self.assertFalse(row["position_age_available_to_allocator"])
        self.assertEqual(row["coordinator_cached_xyz_member_2"], [0.0, 0.0, 10.0])
        self.assertEqual(row["true_xyz_member_2_offline_only"], [220.0, 0.0, 10.0])
        self.assertEqual(row["actual_assignee"], 2)
        self.assertEqual(row["offline_oracle_assignee"], 1)
        self.assertTrue(row["assignment_disagreement"])
        # The discrepancy is distance/optimality, not proved airframe danger:
        self.assertFalse(row["actual_assignee_truth_ineligible"])
        self.assertGreater(row["actual_assignee_truth_distance_m"],
                           row["oracle_assignee_truth_distance_m"])

    def test_validly_signed_inflated_health_changes_eligibility(self):
        row = run_case("signed_false_health")
        self.assertEqual(row["signed_quorum_leader"], 1)
        self.assertEqual(row["position_age_s_member_2_harness_only"], 0.0)
        self.assertEqual(row["actual_assignee"], 2)
        self.assertEqual(row["offline_oracle_assignee"], 1)
        self.assertTrue(row["assignment_disagreement"])
        self.assertTrue(row["actual_assignee_truth_ineligible"])
        self.assertLess(row["true_health_member_2_offline_only"]["battery"], 30)
        self.assertGreater(row["reported_health_member_2"]["battery"], 30)

    def test_probe_rejects_unsupported_scenario(self):
        with self.assertRaises(ValueError):
            run_case("physical_drone_in_the_loop")

    def test_manifests_bind_raw_rows_without_inventing_samples(self):
        records = run_all()
        self.assertEqual([x["scenario"] for x in records], [
            "healthy_control", "stale_position", "signed_false_health"
        ])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            manifest = write_evidence(out, records)
            payload = (out / "incidents.json").read_bytes()
            self.assertEqual(manifest["incidents_json_sha256"],
                             hashlib.sha256(payload).hexdigest())
            self.assertEqual(json.loads(payload), records)
            self.assertEqual(manifest["result_rows"], 3)
            self.assertEqual(manifest["independent_episodes"], 0)
            self.assertFalse(manifest["proposed_method_implemented"])
            self.assertFalse(manifest["physical_flight_performed"])


if __name__ == "__main__":
    unittest.main()
