"""Step 9 evidence-audit regression tests: independent data recomputation.

All tests use genuine cryptographically verified small Step 8 samples, never
fabricated results. Tampering is tested both with stale and recomputed hashes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research_step9_evidence_audit import (
    EvidenceAuditError, METHODS, audit_dir, report, write_audit,
    seed_for, wilson95,
)
from swarm_robust_holdout import (
    DEV_ROOT, HOLDOUT_ROOT, SCENARIOS, run_study, summarize, write_evidence,
)


class ResearchEvidenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temp.name)
        cls.dev = cls.root / "dev"
        cls.held = cls.root / "heldout"
        cls.audit_output = cls.root / "audit"
        # Exactly one genuine signed-receiver episode per stratum for a fast
        # integrated fixture: 4 sizes × 9 scenarios × 6 policies = 216 rows.
        for sample_type, folder, seed in (
            ("development", cls.dev, DEV_ROOT),
            ("heldout", cls.held, HOLDOUT_ROOT),
        ):
            episodes, policies = run_study(trials=1, root=seed)
            write_evidence(
                folder, episodes, policies, summarize(policies),
                sample_type=sample_type, root=seed,
            )

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def test_independent_full_strata_and_seed_audit(self):
        dev = audit_dir(
            self.dev, sample_type="development", root=DEV_ROOT, trials=1)
        held = audit_dir(
            self.held, sample_type="heldout", root=HOLDOUT_ROOT, trials=1)
        self.assertEqual(dev["episodes"],36)
        self.assertEqual(held["policy_rows"],36*len(METHODS))
        self.assertFalse(set(dev["episode_seed_set"]) &
                         set(held["episode_seed_set"]))
        outcome=report(dev,held)
        self.assertEqual(outcome["audit_status"],"PASS")
        self.assertEqual(outcome["scientific_readiness"],
                         "NO_GO_FOR_ALGORITHMIC_SUPERIORITY")
        m=write_audit(self.audit_output,outcome)
        self.assertEqual(m["novelty_submission_gate"],"NO_GO")
        for name,digest in m["audited_files_sha256"].items():
            self.assertEqual(
                hashlib.sha256((self.audit_output/name).read_bytes()).hexdigest(),
                digest)

    def test_unmodified_frozen_study_seeds_agree(self):
        expected=seed_for(DEV_ROOT,5,SCENARIOS[0],0)
        obs=json.loads((self.dev/"episodes.json").read_text())
        self.assertEqual(next(x["seed"] for x in obs
                              if x["n"]==5 and x["scenario"]==SCENARIOS[0]),
                         expected)

    def test_manifest_checksum_rejects_byte_corruption(self):
        with tempfile.TemporaryDirectory() as name:
            target=Path(name)
            for file in ("manifest.json","episodes.json",
                         "paired_policies.json","stratum_summaries.json",
                         "paired_metrics.csv"):
                (target/file).write_bytes((self.dev/file).read_bytes())
            with (target/"paired_metrics.csv").open("a",encoding="utf-8") as f:
                f.write("forged record\n")
            with self.assertRaisesRegex(EvidenceAuditError,"SHA-256"):
                audit_dir(target,sample_type="development",
                          root=DEV_ROOT,trials=1)

    def test_renamed_sha_does_not_hide_wrong_ground_truth_labels(self):
        with tempfile.TemporaryDirectory() as name:
            target=Path(name)
            for file in ("manifest.json","episodes.json",
                         "paired_policies.json","stratum_summaries.json",
                         "paired_metrics.csv"):
                (target/file).write_bytes((self.dev/file).read_bytes())
            rows=json.loads((target/"paired_policies.json").read_text())
            # Change an offline label and then update the hash: ground-truth
            # recalculation, not checksum only, must still detect the forgery.
            rows[0]["truth_ineligible_assignment_count"] = 999
            path=target/"paired_policies.json"
            path.write_text(json.dumps(rows),encoding="utf-8")
            m=json.loads((target/"manifest.json").read_text())
            m["sha256"]["paired_policies.json"] = hashlib.sha256(
                path.read_bytes()).hexdigest()
            (target/"manifest.json").write_text(json.dumps(m),encoding="utf-8")
            with self.assertRaisesRegex(EvidenceAuditError,
                                        "Ground-truth ineligible"):
                audit_dir(target,sample_type="development",
                          root=DEV_ROOT,trials=1)

    def test_rehashed_bootstrap_summary_fabrication_is_detected(self):
        with tempfile.TemporaryDirectory() as name:
            target=Path(name)
            for file in ("manifest.json","episodes.json",
                         "paired_policies.json","stratum_summaries.json",
                         "paired_metrics.csv"):
                (target/file).write_bytes((self.dev/file).read_bytes())
            summaries=json.loads((target/"stratum_summaries.json").read_text())
            summaries[0]["paired_exploratory_contrasts"][
                "median_minus_veto_task_coverage"]["percentile_95_high"] += 0.20
            p=target/"stratum_summaries.json"
            p.write_text(json.dumps(summaries),encoding="utf-8")
            manifest=json.loads((target/"manifest.json").read_text())
            manifest["sha256"]["stratum_summaries.json"] = hashlib.sha256(
                p.read_bytes()).hexdigest()
            (target/"manifest.json").write_text(
                json.dumps(manifest),encoding="utf-8")
            with self.assertRaisesRegex(
                    EvidenceAuditError,"archived paired contrast upper bound"):
                audit_dir(target,sample_type="development",
                          root=DEV_ROOT,trials=1)

    def test_wrong_source_root_is_denied(self):
        with self.assertRaisesRegex(EvidenceAuditError,"Wrong frozen root"):
            audit_dir(self.dev,sample_type="development",
                      root=HOLDOUT_ROOT,trials=1)

    def test_zero_observed_harms_does_not_mean_zero_risk(self):
        interval=wilson95(0,720)
        self.assertEqual(interval["rate"],0)
        self.assertGreater(interval["upper"],0.005)
        self.assertLess(interval["upper"],0.006)


if __name__ == "__main__":
    unittest.main()
