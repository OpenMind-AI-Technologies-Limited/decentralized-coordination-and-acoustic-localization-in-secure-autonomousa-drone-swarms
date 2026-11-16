"""Step 10 manuscript guardrail tests (source numbers from verified Step 9).

This is an isolated validator *test fixture*, NOT a new experimental dataset.
The true submission CI consumes an independently recomputed live Step 9
audit JSON and does not use this fixture as research evidence.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_step10_submission_audit import (
    POLICIES, SubmissionAuditError, check_sources_and_manuscript,
    primary_table, read_json, write_report,
)


ROOT = Path(__file__).resolve().parent
MANUSCRIPT = ROOT/"Docs/CONSISTENCY_GATED_STEP10_MANUSCRIPT.md"
REFERENCE_FILE = ROOT/"Docs/CONSISTENCY_GATED_STEP10_REFERENCES.json"
INDEX = ROOT/"Docs/CONSISTENCY_GATED_STEP10_EVIDENCE_INDEX.md"

# FIXTURE ONLY: These six row counts and coverages match the previously
# independently verified Step 9 scientific_evidence_audit.json. This test
# does NOT claim that it generated or independently replicated those episodes.
SOURCE_REVIEW_FIXTURE = {
    "greedy_signed": (63,0.8888888888888888),
    "age_only": (59,0.8825231481481481),
    "motion_age": (59,0.8816203703703703),
    "veto_3": (0,0.8324305555555556),
    "median_3_age": (30,0.8366666666666667),
    "median_3_motion": (30,0.834837962962963),
}


def audit_fixture():
    return {
        "audit_status":"PASS",
        "scientific_readiness":"NO_GO_FOR_ALGORITHMIC_SUPERIORITY",
        "source_revision":"f47bc6fc60798e499f0cf53de81abb20686f0b93",
        "heldout_episodes":720,
        "heldout_policy_rows":4320,
        "heldout_summaries":216,
        "development_episodes":288,
        "synthetic_safety_coverage":{
            key:{
                "harmful_episodes": SOURCE_REVIEW_FIXTURE[key][0],
                "episode_count":720,
                "mean_task_coverage":SOURCE_REVIEW_FIXTURE[key][1],
            } for key in POLICIES
        },
    }


class Step10ManuscriptAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manuscript = MANUSCRIPT.read_text(encoding="utf-8")
        cls.references = read_json(REFERENCE_FILE)
        cls.evidence_index = INDEX.read_text(encoding="utf-8")

    def validate(self, *, manuscript=None, refs=None, audit=None, index=None):
        return check_sources_and_manuscript(
            self.manuscript if manuscript is None else manuscript,
            self.references if refs is None else refs,
            audit_fixture() if audit is None else audit,
            self.evidence_index if index is None else index,
        )

    def test_full_manuscript_and_references_pass_but_submission_remains_hold(self):
        result=self.validate()
        self.assertEqual(result["structural_consistency"],"PASS")
        self.assertEqual(result["scientific_novelty_superiority"],"NO_GO")
        self.assertEqual(result["journal_submission"],"HOLD")
        self.assertFalse(result["submission_authorized"])
        self.assertFalse(result["manual_gates_resolved"])
        self.assertEqual(result["verified_reference_count"],6)
        self.assertEqual(len(result["unresolved_manual_gates"]),8)
        self.assertEqual(result["verified_heldout_episodes"],720)
        self.assertEqual(set(result["verified_methods"]),set(POLICIES))

    def test_primary_table_is_complete_with_720_source_episodes(self):
        table=primary_table(self.manuscript)
        self.assertEqual(set(table),set(POLICIES))
        self.assertEqual(table["veto_3"]["harmful_episodes"],0)
        self.assertEqual(table["median_3_motion"]["harmful_episodes"],30)
        self.assertTrue(all(row["episode_count"]==720 for row in table.values()))

    def test_one_false_result_is_rejected_not_merely_logged(self):
        bad=self.manuscript.replace("**30/720** | **83.48%**",
                                     "**29/720** | **83.48%**",1)
        self.assertNotEqual(bad,self.manuscript)
        with self.assertRaisesRegex(SubmissionAuditError,
                                    "Changed source-truth safety result"):
            self.validate(manuscript=bad)

    def test_wrong_coverage_is_rejected(self):
        bad=self.manuscript.replace(
            "30/720 | 83.67%", "30/720 | 94.67%",1)
        self.assertNotEqual(bad,self.manuscript)
        with self.assertRaisesRegex(SubmissionAuditError,
                                    "task coverage inconsistent"):
            self.validate(manuscript=bad)

    def test_unverified_removed_citation_is_rejected(self):
        bad=json.loads(json.dumps(self.references))
        bad["references"]=bad["references"][:-1]
        with self.assertRaisesRegex(SubmissionAuditError,
                                    "Insufficient minimum verified citations"):
            self.validate(refs=bad)

    def test_changed_doi_in_manuscript_is_rejected(self):
        bad=self.manuscript.replace(
            "https://doi.org/10.3390/drones10070523",
            "https://doi.org/10.3390/drones10070999",1)
        self.assertNotEqual(bad,self.manuscript)
        with self.assertRaisesRegex(SubmissionAuditError,
                                    "missing a verified publisher DOI"):
            self.validate(manuscript=bad)

    def test_unaudited_or_superiority_label_is_refused(self):
        broken=audit_fixture()
        broken["scientific_readiness"]="PAPER_IS_SUPERIOR"
        with self.assertRaisesRegex(SubmissionAuditError,"novelty gate"):
            self.validate(audit=broken)
        broken=audit_fixture()
        broken["audit_status"]="FAIL"
        with self.assertRaisesRegex(SubmissionAuditError,
                                    "evidence audit did not pass"):
            self.validate(audit=broken)

    def test_removed_author_declarations_rejected(self):
        bad=self.manuscript.replace("AUTHOR CONFIRMATION REQUIRED",
                                    "CONFIRMED WITHOUT AUTHOR",100)
        self.assertNotEqual(bad,self.manuscript)
        with self.assertRaisesRegex(SubmissionAuditError,
                                    "critical caution or author declaration"):
            self.validate(manuscript=bad)

    def test_report_manifest_is_integrity_bound_and_not_submit_green(self):
        result=self.validate()
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            manifest=write_report(out,result,MANUSCRIPT,
                                  REFERENCE_FILE,MANUSCRIPT,INDEX)
            self.assertEqual(manifest["journal_submission"],"HOLD")
            self.assertFalse(manifest["human_declarations_confirmed"])
            self.assertIn("step10_submission_readiness.json",
                          manifest["source_and_report_sha256"])
            report=json.loads(
                (out/"step10_submission_readiness.json").read_text())
            self.assertFalse(report["submission_authorized"])


if __name__=="__main__":
    unittest.main()
