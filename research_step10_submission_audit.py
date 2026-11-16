"""Step 10 reproducible manuscript-to-audited-evidence validation.

This checks the manuscript's primary data, exact DOI references, section
coverage, provenance and unresolved submission requirements against Step 9's
independent audit result. It CANNOT independently judge scientific novelty,
text similarity, author approval or editorial fit.

Exit 0 means the DRAFT PACKAGE is INTERNALLY CONSISTENT, NOT submission-ready.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys


class SubmissionAuditError(ValueError):
    pass


POLICIES = (
    "greedy_signed", "age_only", "motion_age",
    "veto_3", "median_3_age", "median_3_motion",
)
MANUAL_BLOCKERS = {
    "authorship_and_author_order": "Author and all coauthor approvals unresolved",
    "institution_affiliation_orcid_email": "Affiliation, ORCID and contact details require author confirmation",
    "funding_competing_interests_and_credit": "Funding, competing interests and individual contributions require declarations",
    "prior_related_work_and_similarity": "Text/evidence overlap with related swarm articles needs editorial review",
    "permanent_evidence_deposit": "Preservation-grade reproducible artifact DOI/release has not been verified",
    "bibliography_depth_and_current_novelty": "Six-source targeted bibliography is not an exhaustive systematic novelty assessment",
    "venue_specific_eligibility": "Journal, article type and instructions have not been approved or checked",
    "physical_validation_if_claimed": "Any field, flight or certified hardware claim would require new evidence",
}


def require(condition, msg):
    if not condition:
        raise SubmissionAuditError(msg)


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def primary_table(manuscript: str):
    require("### 5.1 " in manuscript and "### 5.2 " in manuscript,
            "Missing or changed empirical primary-results section")
    segment = manuscript.split("### 5.1 ", 1)[1].split("### 5.2 ", 1)[0]
    extracted = {}
    for row in segment.splitlines():
        if not row.startswith("|") or row.count("|") < 4:
            continue
        cells = [item.replace("*", "").strip()
                 for item in row.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        method = re.search(r"`([a-z][a-z0-9_]*)`", cells[0])
        if not method:
            continue
        label = method.group(1)
        require(label not in extracted, "Duplicate primary-results method " + label)
        fraction = re.fullmatch(r"(\d+)\s*/\s*(\d+)", cells[1])
        pct = re.fullmatch(r"(\d+(?:\.\d+)?)%", cells[2])
        require(fraction is not None and pct is not None,
                "Malformed primary-results cell for " + label)
        extracted[label] = {
            "harmful_episodes": int(fraction.group(1)),
            "episode_count": int(fraction.group(2)),
            "mean_coverage_pct": float(pct.group(1)),
        }
    require(set(extracted) == set(POLICIES),
            "Missing, unexpected or renamed primary-results policy")
    return extracted


def check_sources_and_manuscript(manuscript: str,
                                 references: dict,
                                 audit: dict,
                                 evidence_index: str) -> dict:
    require(audit.get("audit_status") == "PASS",
            "Independent Step 9 evidence audit did not pass")
    require(audit.get("scientific_readiness") ==
            "NO_GO_FOR_ALGORITHMIC_SUPERIORITY",
            "Scientific novelty gate must remain NO-GO")
    require(audit.get("heldout_episodes") == 720 and
            audit.get("heldout_policy_rows") == 4320 and
            audit.get("heldout_summaries") == 216 and
            audit.get("development_episodes") == 288,
            "Audited sample sizes changed")
    require(re.fullmatch(r"[0-9a-f]{40}", audit.get("source_revision", "")),
            "Step 9 source revision is invalid")
    counts = audit.get("synthetic_safety_coverage", {})
    require(set(counts) == set(POLICIES), "Auditor policy definitions changed")
    table = primary_table(manuscript)
    for method in POLICIES:
        data = counts[method]
        row = table[method]
        require(row["episode_count"] == data["episode_count"] == 720,
                "Wrong source episode denominator for " + method)
        require(row["harmful_episodes"] == data["harmful_episodes"],
                "Changed source-truth safety result for " + method)
        require(math.isclose(row["mean_coverage_pct"],
                             100. * data["mean_task_coverage"],
                             abs_tol=0.00501),
                "Reported task coverage inconsistent with raw audit: " + method)

    # Abstract must remain equally cautious with both harm and availability.
    require("## Abstract" in manuscript and "## 1. Introduction" in manuscript,
            "Abstract or introduction missing")
    abstract = manuscript.split("## Abstract", 1)[1].split(
        "## 1. Introduction", 1)[0]
    for detail in ("720", "288", "63/720", "59/720", "0/720", "30/720",
                   "83.24%", "83.48%", "synthetic", "not a universally"):
        require(detail.lower() in abstract.lower(),
                "Abstract missing required bounded evidence or caveat: " + detail)

    # Verify all real, individually used DOI references exactly once.
    require(references.get("verification_date") == "2026-11-16",
            "Reference verification record not date-stamped")
    records = references.get("references")
    require(isinstance(records, list) and len(records) >= 6,
            "Insufficient minimum verified citations")
    numbers = [record["number"] for record in records]
    require(numbers == list(range(1, len(records)+1)),
            "References are noncontiguous or unordered")
    doi_set = set()
    for record in records:
        doi = record["doi"].strip().lower()
        require(re.fullmatch(r"10\.\d{4,9}/[^\s]+", doi) is not None,
                "Invalid DOI metadata syntax")
        require(doi not in doi_set, "Duplicate DOI in literature metadata")
        doi_set.add(doi)
        require(record["year"] <= 2026 and record["year"] >= 1980,
                "Future or invalid reference year")
        require("https://doi.org/" + doi in manuscript.lower(),
                "Manuscript is missing a verified publisher DOI: "+doi)
        require(record["title"].strip() and record["publisher_url"].startswith("https://"),
                "Reference lacks verified bibliographic metadata")
    before_refs = manuscript.split("## References", 1)[0]
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", before_refs)}
    require(cited == set(numbers),
            "Body text does not use every verified numbered reference")

    required_sections = (
        "## 1. Introduction", "## 2. Prior work and positioning",
        "## 3. System and threat model",
        "## 4. Experimental design and reproducibility",
        "## 5. Heldout results", "## 6. Discussion",
        "## 7. Limitations and threats to validity",
        "## 8. Conclusion", "## 9. Reproducibility and data/code availability",
        "## 10. Declarations and author sign-off",
        "## References",
    )
    for part in required_sections:
        require(part in manuscript, "Required scientific section missing: " + part)
    for phrase in (
        "journal submission NOT AUTHORIZED",
        "AUTHOR CONFIRMATION REQUIRED",
        "NOT RECEIVED", "not a novel",
        "0/720", "30/720", "single-conflict", "collud",
        "Step 7", "Step 8", "Step 9",
    ):
        require(phrase.lower() in manuscript.lower(),
                "A critical caution or author declaration is missing: " + phrase)
    require("When Signed Witnesses Disagree" in manuscript,
            "Working paper scope changed unexpectedly")
    for phrase in (
        "CONSISTENCY_GATED_STEP8_FROZEN_PROTOCOL.md",
        "CONSISTENCY_GATED_STEP8_HELDOUT_FINDINGS.md",
        "CONSISTENCY_GATED_STEP9_SCIENTIFIC_READINESS.md",
        "CONSISTENCY_GATED_STEP10_MANUSCRIPT.md",
        "4481e74616cd0225de749bb8328fb2fd8d12103d36b34f869bb4fa1b1cd405e2",
        "NO-GO", "2026",
    ):
        require(phrase in evidence_index,
                "Evidence lineage or publication caution missing: " + phrase)
    require("original strictly dominant" not in abstract.lower(),
            "Unsupported novelty claim in abstract")

    return {
        "structural_consistency": "PASS",
        "scientific_novelty_superiority": "NO_GO",
        "journal_submission": "HOLD",
        "audited_step9_source_revision": audit["source_revision"],
        "verified_heldout_episodes": 720,
        "verified_correlated_policy_rows": 4320,
        "verified_reference_count": len(records),
        "verified_methods": {name: table[name] for name in POLICIES},
        "unresolved_manual_gates": dict(MANUAL_BLOCKERS),
        "manual_gates_resolved": False,
        "claims_of_real_flight": False,
        "submission_authorized": False,
        "review_scope": (
            "Manuscript statistics, DOI-presence metadata and declared limitations "
            "only; NOT a new independent literature search, text-similarity check "
            "or editor/author approval."
        ),
    }


def write_report(out: Path, summary: dict,
                 manuscript: Path, refs: Path,
                 audit_path: Path, index_path: Path):
    out.mkdir(parents=True, exist_ok=True)
    report = out / "step10_submission_readiness.json"
    report.write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n",
                      encoding="utf-8")
    md = [
        "# Step 10 — Automated Manuscript Readiness Report",
        "",
        "**Data/manuscript consistency: PASS.**",
        "**Novel algorithm superiority: NO-GO. Journal submission: HOLD.**",
        "",
        "Primary outcome checked against a separately generated Step 9 "
        "audit JSON for all 720 heldout episodes and six policies.",
        "",
        "| Policy | Verified resource-ineligible episodes | Mean task coverage |",
        "|---|---:|---:|",
    ]
    for method in POLICIES:
        row = summary["verified_methods"][method]
        md.append(
            f"| `{method}` | {row['harmful_episodes']}/"
            f"{row['episode_count']} | {row['mean_coverage_pct']:.2f}% |")
    md.extend([
        "",
        "## Manual blockers remaining before journal submission",
        "",
    ])
    md.extend("- "+value for value in summary["unresolved_manual_gates"].values())
    md.extend([
        "",
        "Six references were checked at the publisher-metadata level before "
        "the source record was written; this script verifies their DOI "
        "presence/structure but does **not** perform another live web query.",
        "",
        "CI status and SHA-256 are evidence-quality checks; they do not "
        "establish scientific novelty, physical flight validity, reviewer "
        "acceptance, author contributions or editorial permission.",
        "",
    ])
    rendered = out/"step10_submission_readiness.md"
    rendered.write_text("\n".join(md), encoding="utf-8")
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (manuscript, refs, audit_path, index_path,
                        report, rendered)}
    manifest = {
        "schema_version":1,
        "structural_consistency":"PASS",
        "journal_submission":"HOLD",
        "source_and_report_sha256":hashes,
        "human_declarations_confirmed":False,
    }
    (out/"manifest.json").write_text(
        json.dumps(manifest,indent=2,sort_keys=True)+"\n",
        encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manuscript",required=True,type=Path)
    p.add_argument("--references",required=True,type=Path)
    p.add_argument("--audit",required=True,type=Path)
    p.add_argument("--index",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    summary=check_sources_and_manuscript(
        args.manuscript.read_text(encoding="utf-8"),
        read_json(args.references),read_json(args.audit),
        args.index.read_text(encoding="utf-8"))
    manifest=write_report(
        args.out, summary, args.manuscript, args.references,
        args.audit, args.index)
    print(json.dumps({
        "structure":summary["structural_consistency"],
        "submission":summary["journal_submission"],
        "heldout_episodes":summary["verified_heldout_episodes"],
        "references":summary["verified_reference_count"],
        "output_hashes":manifest["source_and_report_sha256"],
    },indent=2,sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (SubmissionAuditError, ValueError, KeyError, OSError) as exc:
        print("STEP10 MANUSCRIPT AUDIT FAILED: "+str(exc),file=sys.stderr)
        sys.exit(1)
