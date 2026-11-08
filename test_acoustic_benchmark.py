"""The acoustic benchmark must expose true synthetic position error."""
import csv
import json
import tempfile
import unittest

from acoustic_benchmark import benchmark, write_results


class BenchmarkTests(unittest.TestCase):
    def test_deterministic_sweep_reports_real_position_error_separately(self):
        rows, summary = benchmark(trials=2, seed=17, noise_levels=(0., 0.02))
        replay, again = benchmark(trials=2, seed=17, noise_levels=(0., 0.02))
        self.assertEqual(rows, replay)
        self.assertEqual(summary, again)
        self.assertEqual(len(rows), 4)
        self.assertFalse(summary["source_is_drone_position"])
        self.assertFalse(summary["hardware_verified"])
        for item in rows:
            self.assertTrue(item["source_only"])
            if item["detected"]:
                self.assertIsInstance(item["position_error_m"], float)
                self.assertIsInstance(item["tdoa_residual_rmse_m"], float)

    def test_csv_and_summary_are_readable(self):
        rows, summary = benchmark(trials=1, seed=11, noise_levels=(0.,))
        with tempfile.TemporaryDirectory() as root:
            csv_path, json_path = write_results(rows, summary, root)
            with csv_path.open(encoding="utf-8", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)
            self.assertFalse(json.loads(json_path.read_text(encoding="utf-8"))["hardware_verified"])


if __name__ == "__main__":
    unittest.main()
