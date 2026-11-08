"""Scientific experiment harness regression tests; no fabricated observations."""
import csv
import json
import math
import tempfile
import unittest

from experiment_statistics import bootstrap_interval, summarize_trials, wilson_interval
from swarm_acoustic_experiments import beacon_trial, source_trials
from swarm_experiment_runner import run_suite, write_evidence
from swarm_geometry_experiments import allocation_trial, formation_trial
from swarm_network_experiments import SCENARIOS, run_election_trial


class ElectionExperiments(unittest.TestCase):
    def test_real_signed_election_scaling(self):
        for size in (5, 10, 20, 50):
            with self.subTest(nodes=size):
                result = run_election_trial(size, 17, "healthy")
                self.assertTrue(result["converged"])
                self.assertFalse(result["same_epoch_conflict"])
                self.assertEqual(result["certified_honest_nodes"], size)
                self.assertEqual(result["quorum"], size-(size-1)//3)
                self.assertGreater(result["wire_bytes_sent"], 0)

    def test_packet_loss_is_counted_not_interpreted_as_radio(self):
        result = run_election_trial(10, 42, "packet_loss", loss_rate=0.25)
        self.assertGreater(result["packets_dropped"], 0)
        self.assertFalse(result["same_epoch_conflict"])
        self.assertGreaterEqual(result["virtual_time_ms"], 0)

    def test_under_quorum_partition_cannot_certify(self):
        result = run_election_trial(10, 18, "minority_partition")
        self.assertTrue(result["converged"])
        self.assertEqual(result["certified_honest_nodes"], 0)
        self.assertFalse(result["same_epoch_conflict"])

    def test_quorum_side_of_partition_can_elect(self):
        result = run_election_trial(10, 29, "quorum_partition")
        self.assertTrue(result["converged"])
        self.assertEqual(result["certified_honest_nodes"], 7)

    def test_byzantine_withholding_does_not_break_quorum(self):
        result = run_election_trial(10, 33, "byzantine_withholding")
        self.assertEqual(result["faults_injected"], 3)
        self.assertTrue(result["converged"])
        self.assertFalse(result["same_epoch_conflict"])

    def test_equivocation_and_tampered_packets_are_observed(self):
        equivocation = run_election_trial(7, 50, "byzantine_equivocation")
        self.assertGreater(equivocation["detected_equivocations"], 0)
        self.assertFalse(equivocation["same_epoch_conflict"])
        tampered = run_election_trial(5, 61, "tampered_packets")
        self.assertGreater(tampered["packets_rejected"], 0)

    def test_crashed_leader_recovery(self):
        result = run_election_trial(5, 99, "leader_failure")
        self.assertTrue(result["converged"])
        self.assertEqual(result["certified_honest_nodes"], 4)

    def test_invalid_inputs_refused(self):
        with self.assertRaises(ValueError):
            run_election_trial(3, 2, "healthy")
        with self.assertRaises(ValueError):
            run_election_trial(5, 2, "unlisted_attack")
        with self.assertRaises(ValueError):
            run_election_trial(5, 2, "packet_loss", loss_rate=1.2)


class GeometryExperiments(unittest.TestCase):
    def test_geometry_reports_actual_paired_waypoint_metrics(self):
        for size in (5, 10, 20, 50):
            for pattern in ("v", "line", "circle", "grid"):
                result = formation_trial(size, 19, pattern)
                self.assertTrue(all(math.isfinite(float(value))
                                    for key, value in result.items()
                                    if key not in ("family", "scenario")))
                self.assertEqual(
                    result["pair_violation_reduction"],
                    result["baseline_pair_violations"] -
                    result["adjusted_waypoint_violations"],
                )
                self.assertGreaterEqual(result["suggested_displacement_m"], 0)

    def test_health_aware_assignment_excludes_degraded_nodes(self):
        result = allocation_trial(20, 98, degraded=True)
        self.assertEqual(result["ineligible_assignments"], 0)
        self.assertGreater(result["tasks_assigned"], 0)
        self.assertLessEqual(result["tasks_assigned"], result["tasks_requested"])
        self.assertGreaterEqual(result["ineligible_assignment_reduction"], 0)


class AcousticExperiments(unittest.TestCase):
    def test_known_beacon_receiver_has_distinct_gps_off_reference(self):
        clean = beacon_trial(111, jitter_us=0, reference_available=True)
        absent = beacon_trial(111, jitter_us=0, reference_available=False)
        self.assertTrue(clean["localized"])
        self.assertLess(clean["position_error_m"], 0.01)
        self.assertFalse(absent["localized"])
        self.assertIsNone(absent["position_error_m"])

    def test_source_noise_evidence_uses_existing_tracker(self):
        data = source_trials(2, 49, noises=(0.0, 0.02))
        self.assertEqual(len(data), 4)
        self.assertTrue(all(item["family"] == "acoustic_source" for item in data))


class StatisticalReporting(unittest.TestCase):
    def test_wilson_intervals_do_not_collapse_at_extremes(self):
        self.assertGreater(wilson_interval(0, 5)["upper"], 0)
        self.assertLess(wilson_interval(5, 5)["lower"], 1)
        self.assertEqual(wilson_interval(5, 5)["rate"], 1)

    def test_bootstrap_is_reproducible(self):
        self.assertEqual(bootstrap_interval([1, 2, 4, 8], seed=5),
                         bootstrap_interval([1, 2, 4, 8], seed=5))
        self.assertIsNone(bootstrap_interval([5])["lower"])

    def test_failed_localization_not_imputed_as_zero(self):
        rows = [
            {"family": "beacon_receiver", "scenario": "known", "nodes": 4,
             "seed": 1, "localized": True, "position_error_m": 3.0},
            {"family": "beacon_receiver", "scenario": "known", "nodes": 4,
             "seed": 2, "localized": False, "position_error_m": None},
        ]
        stats = summarize_trials(rows, resamples=100)
        error = stats[0]["metrics"]["position_error_m"]
        self.assertEqual(error["mean"], 3.0)
        self.assertEqual(error["observed"], 1)
        self.assertEqual(error["missing"], 1)
        self.assertEqual(stats[0]["metrics"]["localized"]["rate"], 0.5)

    def test_unsupported_nonfinite_statistic_refused(self):
        with self.assertRaises(ValueError):
            bootstrap_interval([1, float("nan")])


class EvidenceExport(unittest.TestCase):
    def test_seeded_run_and_evidence_files(self):
        families = ("election", "formation", "allocation", "beacon_receiver")
        scenarios = ("healthy", "minority_partition")
        kwargs = dict(sizes=(5,), trials=2, seed=17, families=families,
                      network_scenarios=scenarios, bootstrap_samples=100)
        rows, summary = run_suite(**kwargs)
        self.assertEqual(len(rows), 24)
        self.assertEqual(len(summary), 12)
        with tempfile.TemporaryDirectory() as temp:
            files = write_evidence(rows, summary, temp,
                                   sizes=[5], trials=2, seed=17,
                                   families=families, network_scenarios=scenarios,
                                   loss_rate=0.15, bootstrap_samples=100)
            with open(files["csv"], newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 24)
            with open(files["manifest"], encoding="utf-8") as handle:
                manifest = json.load(handle)
            self.assertFalse(manifest["real_uav_hardware"])
            self.assertEqual(manifest["raw_rows"], 24)
            with open(files["report"], encoding="utf-8") as handle:
                self.assertIn("NO physical UAV", handle.read())


if __name__ == "__main__":
    unittest.main()
