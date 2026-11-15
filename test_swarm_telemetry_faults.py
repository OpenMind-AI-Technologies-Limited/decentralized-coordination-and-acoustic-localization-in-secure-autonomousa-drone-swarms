"""Step 4 attack injection: cryptographic receipt, negative controls, integrity.

These unit and regression scenarios are NOT independent publication data.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from swarm_fault_experiment_runner import run_suite, write_evidence
from swarm_telemetry_faults import FaultCase, FaultNetwork, ManualClock, SCENARIOS, run_fault_case
from swarm_mesh import MeshNode, SwarmIdentity


class TelemetryFaultScenarios(unittest.TestCase):
    def case(self, scenario, *, n=5, seed=55, loss=0.0):
        return run_fault_case(FaultCase(
            scenario=scenario, nodes=n, seed=seed, packet_loss=loss))

    def test_healthy_control_does_not_require_fabricated_truth(self):
        result = self.case("healthy_control")
        self.assertTrue(result["signed_authenticated_bootstrap"])
        self.assertTrue(result["signed_quorum_certified_before_attack"])
        self.assertTrue(result["quorum_fresh_at_decision"])
        self.assertEqual(result["baseline"]["assignee"], 2)
        self.assertEqual(result["age_only"]["assignee"], 2)
        self.assertEqual(result["oracle_assignee_offline"], 2)
        self.assertFalse(result["baseline"]["truth_ineligible"])
        self.assertEqual(result["witness_strict"]["unassigned_tasks"], 1)
        self.assertFalse(result["physical_uav_flight"])

    def test_health_only_refresh_stays_stale(self):
        result = self.case("stale_position")
        self.assertEqual(result["baseline"]["assignee"], 2)
        self.assertEqual(result["age_only"]["assignee"], 1)
        self.assertEqual(result["oracle_assignee_offline"], 1)
        self.assertGreater(result["coordinator_member_2_position_age_s"], 7.)
        self.assertEqual(result["age_only"]["reason_node_2"], "stale_health_or_position")

    def test_authenticated_false_health_without_witness_is_not_detected(self):
        result = self.case("signed_false_health")
        self.assertEqual(result["baseline"]["assignee"], 2)
        self.assertEqual(result["age_only"]["assignee"], 2)
        self.assertTrue(result["age_only"]["truth_ineligible"])
        self.assertIsNone(result["witness_strict"]["assignee"])
        self.assertEqual(result["oracle_assignee_offline"], 1)

    def test_signed_position_spoof_is_not_infallibly_detected(self):
        result = self.case("signed_position_spoof")
        self.assertEqual(result["baseline"]["assignee"], 2)
        self.assertEqual(result["age_only"]["assignee"], 2)
        self.assertEqual(result["oracle_assignee_offline"], 1)

    def test_slow_drift_remains_possible_without_independent_evidence(self):
        result = self.case("bounded_slow_drift")
        self.assertEqual(result["baseline"]["assignee"], 2)
        self.assertEqual(result["age_only"]["assignee"], 2)
        self.assertEqual(result["oracle_assignee_offline"], 1)
        self.assertEqual(result["age_only"]["reason_node_2"], "bounded_observations_pass")
        self.assertGreaterEqual(result["network"]["authenticated_delivered"], 3)

    def test_honest_witnesses_reject_signed_false_resource(self):
        result = self.case("honest_witnesses")
        self.assertEqual(result["baseline"]["assignee"], 2)
        self.assertEqual(result["age_only"]["assignee"], 2)
        self.assertEqual(result["witness_strict"]["assignee"], 1)
        self.assertEqual(result["witness_strict"]["reason_node_2"],
                         "signed_witness_conflict")

    def test_malicious_single_witness_causes_false_rejection(self):
        result = self.case("malicious_witness")
        self.assertEqual(result["oracle_assignee_offline"], 2)
        self.assertEqual(result["baseline"]["assignee"], 2)
        self.assertEqual(result["witness_strict"]["assignee"], 1)
        self.assertEqual(result["witness_strict"]["reason_node_2"],
                         "signed_witness_conflict")
        self.assertEqual(result["compromised_witness_count"], 1)

    def test_colluding_witnesses_can_subvert_consistency_claim(self):
        result = self.case("colluding_witnesses", n=10)
        self.assertEqual(result["witness_strict"]["assignee"], 2)
        self.assertTrue(result["witness_strict"]["truth_ineligible"])
        self.assertEqual(result["compromised_witness_count"], 2)
        self.assertGreaterEqual(result["declared_byzantine_fault_budget"], 2)

    def test_no_witness_availability_tradeoff(self):
        result = self.case("no_independent_witnesses")
        self.assertEqual(result["age_only"]["assignee"], 2)
        self.assertIsNone(result["witness_strict"]["assignee"])
        self.assertEqual(result["witness_strict"]["reason_node_2"],
                         "independent_evidence_insufficient")

    def test_packet_loss_partition_delay_and_corruption_are_distinct(self):
        for scenario in ("packet_loss", "partition",
                         "delayed_update", "tampered_packet"):
            with self.subTest(scenario=scenario):
                result = self.case(scenario, loss=0.15 if scenario == "packet_loss" else 0.)
                self.assertTrue(result["quorum_fresh_at_decision"])
                self.assertEqual(result["baseline"]["assignee"], 2)
                self.assertEqual(result["age_only"]["assignee"], 1)
                self.assertEqual(result["oracle_assignee_offline"], 1)
                self.assertGreater(result["coordinator_member_2_position_age_s"], 7.)
                stats = result["network"]
                key = {"packet_loss": "dropped",
                       "partition": "dropped",
                       "delayed_update": "pending_delay",
                       "tampered_packet": "rejected"}[scenario]
                self.assertGreater(stats[key], 0)
                # No keys or encrypted packet buffers leak to traces.
                self.assertTrue(all("ciphertext" not in row and "signature" not in row
                                    for row in result["network_events"]))

    def test_scenario_configuration_validation(self):
        for fields in (
            {"scenario":"unknown", "seed":7},
            {"scenario":"healthy_control", "seed":7,"nodes":3},
            {"scenario":"healthy_control", "seed":7,"packet_loss":1.0},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                FaultCase(**fields)


class FaultEvidenceIntegrity(unittest.TestCase):
    def test_runner_is_seed_reproducible_and_does_not_mix_old_data(self):
        parameters = dict(sizes=(5,), trials=2, seed=91,
                          scenarios=("healthy_control", "stale_position",
                                     "tampered_packet", "malicious_witness"))
        first = run_suite(**parameters)
        second = run_suite(**parameters)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        self.assertEqual(len({(x["nodes"],x["trial"],x["scenario"],x["seed"])
                              for x in first}), 8)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            manifest = write_evidence(out, first)
            self.assertEqual(manifest["run_count"], len(first))
            self.assertFalse(manifest["physical_uav_flight"])
            self.assertFalse(manifest["full_paper_comparative_evidence_available"])
            self.assertTrue(manifest["separate_from_previous_378_trial_archive"])
            for name, digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(json.loads((out/"fault_trials.json").read_text()),first)
            with (out/"fault_trial_metrics.csv").open(newline="",encoding="utf-8") as src:
                self.assertEqual(len(list(csv.DictReader(src))),8)

    def test_duplicate_or_empty_scenarios_are_rejected(self):
        with self.assertRaises(ValueError):
            run_suite(scenarios=("stale_position", "stale_position"), trials=1)
        with self.assertRaises(ValueError):
            run_suite(scenarios=(), trials=1)
        with self.assertRaises(ValueError):
            run_suite(sizes=(5,5), trials=1)


if __name__ == "__main__":
    unittest.main()
