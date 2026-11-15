"""Reproducible diagnostic checks for Step 6 dynamic recovery evidence."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from swarm_recovery_experiments import (
    SCENARIOS, run_recovery_case, run_recovery_suite, write_recovery_evidence,
)


class RecoveryExperimentTests(unittest.TestCase):
    def case(self, name: str, size: int = 5):
        return run_recovery_case(scenario=name,size=size,seed=78)

    def test_truthful_stop_allows_single_versioned_reassignment(self):
        row=self.case("signed_stop_reassign")
        self.assertEqual(row["task_versions_issued"],2)
        self.assertEqual(row["current_outstanding_leases"],1)
        self.assertEqual(row["accepted_owner_receipts"],1)
        self.assertEqual(row["rejected_receipts"],0)
        self.assertTrue(row["local_audit_chain_valid"])
        self.assertEqual(row["all_steps"][-1]["tasks"]["inspection-001"]["owner_id"],1)

    def test_unconfirmed_failure_and_partition_do_not_reassign(self):
        for name in ("unconfirmed_failure","quorum_partition"):
            with self.subTest(name=name):
                row=self.case(name)
                self.assertEqual(row["task_versions_issued"],1)
                self.assertEqual(row["expired_unconfirmed"],1)
                self.assertEqual(row["current_outstanding_leases"],1)
                self.assertFalse(any(event["event"] == "receipt_accepted"
                                     for event in row["all_steps"]))
        partition=self.case("quorum_partition")
        self.assertIn("plan_denied",
                      [event["event"] for event in partition["all_steps"]])

    def test_late_signed_stop_recovery_and_new_epoch_fencing(self):
        late=self.case("late_stop_after_expiry",10)
        self.assertEqual(late["task_versions_issued"],2)
        self.assertGreater(late["accepted_owner_receipts"],0)
        self.assertTrue(any(event["held"]==["inspection-001"]
                            for event in late["all_steps"]))
        switched=self.case("epoch_failover",10)
        self.assertEqual(switched["task_versions_issued"],2)
        self.assertGreaterEqual(switched["rejected_receipts"],1)
        self.assertTrue(any(event["event"]=="plan_denied"
                            for event in switched["all_steps"]))

    def test_completion_terminal_and_dynamic_arrival(self):
        complete=self.case("normal_completion")
        self.assertEqual(complete["task_versions_issued"],1)
        self.assertEqual(complete["current_outstanding_leases"],0)
        self.assertEqual(complete["all_steps"][-1]["tasks"]["inspection-001"]["status"],
                         "COMPLETED")
        added=self.case("new_task_arrival")
        self.assertEqual(added["task_count"],2)
        self.assertEqual(added["current_outstanding_leases"],2)
        self.assertEqual(added["all_steps"][-1]["tasks"]["inspection-002"]["owner_id"],1)

    def test_missing_eligible_and_forged_stop_fail_closed(self):
        missing=self.case("no_eligible_recovery")
        self.assertEqual(missing["task_versions_issued"],1)
        self.assertEqual(missing["current_outstanding_leases"],0)
        self.assertEqual(missing["all_steps"][-1]["tasks"]["inspection-001"]["status"],
                         "PENDING")
        forged=self.case("forged_stop_attempt")
        self.assertEqual(forged["task_versions_issued"],1)
        self.assertEqual(forged["rejected_receipts"],1)
        self.assertEqual(forged["expired_unconfirmed"],1)

    def test_malicious_but_signed_stop_can_break_physical_safety_assumption(self):
        bad=self.case("false_signed_stop")
        self.assertTrue(bad["false_stop_claim_injected"])
        self.assertFalse(bad["simulated_truthful_stop_confirmed"])
        self.assertEqual(bad["task_versions_issued"],2)
        self.assertFalse(bad["global_exactly_once_execution_verified"])
        self.assertTrue(bad["signed_owner_ack_does_not_attest_hardware"])

    def test_reproducibility_hashes_and_no_prior_research_reuse(self):
        args=dict(sizes=(5,),trials=2,seed=35)
        first=run_recovery_suite(**args)
        second=run_recovery_suite(**args)
        self.assertEqual(first,second)
        self.assertEqual(len(first),len(SCENARIOS)*2)
        self.assertEqual(len({(x["size"],x["seed"],x["scenario"])
                              for x in first}),len(first))
        self.assertTrue(all(x["local_audit_chain_valid"] for x in first))
        with tempfile.TemporaryDirectory() as folder:
            where=Path(folder)
            manifest=write_recovery_evidence(where,first)
            self.assertEqual(manifest["episode_rows"],len(first))
            self.assertFalse(manifest["independent_publication_scale_evidence"])
            self.assertTrue(manifest["prior_supplementary_378_trials_untouched"])
            for name,digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((where/name).read_bytes()).hexdigest(),
                                 digest)
            rows=json.loads((where/"recovery_episodes.json").read_text())
            self.assertEqual(first,rows)
            with (where/"recovery_metrics.csv").open(newline="",encoding="utf-8") as f:
                self.assertEqual(len(list(csv.DictReader(f))),len(first))

    def test_bounded_runner_inputs(self):
        with self.assertRaises(ValueError):
            run_recovery_suite(sizes=(3,))
        with self.assertRaises(ValueError):
            run_recovery_suite(sizes=(5,5))
        with self.assertRaises(ValueError):
            run_recovery_suite(trials=0)
        with self.assertRaises(ValueError):
            run_recovery_case(scenario="invented_failure",size=5,seed=1)


if __name__=="__main__":
    unittest.main()
