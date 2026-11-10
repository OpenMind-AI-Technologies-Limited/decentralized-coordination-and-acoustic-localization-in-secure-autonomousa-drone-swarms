#!/usr/bin/env python3
"""Archive the original CI evidence as versioned supplementary research data.

Every numerical value is copied from GitHub Actions run 42455738522.
Do not substitute invented rows or alternate manuscript datasets.
"""
import csv
import hashlib
import json
from pathlib import Path
import shutil

RUN_ID = 42455738522
EXPECTED_TRIAL_SHA256 = "d35cb10e2f6e1c2d7fbad4c08f20b6584930949c70b84bb5f7eb05089fa6e7c6"
EXPECTED_SOURCE_REVISION = "78cce082c5acabe68ebc5f76a32872b210308af5"
EXPECTED_ROWS = 378
EXPECTED_SETTINGS = 63
REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "evidence_download"
DEST = REPO / "supplementary" / "uav-swarm-authority-v1.0.0"

def copy_file(source, target):
    if not source.is_file():
        raise FileNotFoundError(f"Missing evidence: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

def main():
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    raw = (SOURCE / "trials.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    trials = json.loads(raw)
    settings = json.loads((SOURCE / "summary.json").read_text(encoding="utf-8"))
    if len(trials) != EXPECTED_ROWS or manifest["raw_rows"] != EXPECTED_ROWS:
        raise RuntimeError("S1 trial count mismatch")
    if len(settings) != EXPECTED_SETTINGS:
        raise RuntimeError("S2 setting count mismatch")
    if digest != manifest["trials_json_sha256"] or digest != EXPECTED_TRIAL_SHA256:
        raise RuntimeError("Raw trial SHA-256 mismatch")
    if manifest["source_revision"] != EXPECTED_SOURCE_REVISION:
        raise RuntimeError("Source revision mismatch")
    if sum(item.get("trials", 0) for item in settings) != EXPECTED_ROWS:
        raise RuntimeError("Setting counts do not match raw trial count")
    if any(item.get("trials") != 6 for item in settings):
        raise RuntimeError("Unexpected repetitions in archive")
    if any(row.get("family") not in manifest["families"] for row in trials):
        raise RuntimeError("Unrecognized trial family")
    for old, new in [
        ("trials.csv", "S1_Trial_Observations/Supplementary_Data_S1_Trial_Observations.csv"),
        ("trials.json", "S1_Trial_Observations/Supplementary_Data_S1_Trial_Observations.json"),
        ("summary.json", "S2_Setting_Summaries/Supplementary_Data_S2_Setting_Summaries.json"),
        ("REPORT.md", "Methods_and_Integrity/Experimental_Results_Report.md"),
        ("manifest.json", "Methods_and_Integrity/Original_Execution_Manifest.json"),
    ]:
        copy_file(SOURCE / old, DEST / new)
    # A readable CSV with exactly one row per setting; complete statistics remain
    # losslessly available in the associated S2 JSON.
    s2csv = DEST / "S2_Setting_Summaries" / "Supplementary_Data_S2_Setting_Summaries.csv"
    s2csv.parent.mkdir(parents=True, exist_ok=True)
    with s2csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["family", "scenario", "nodes", "trials", "metrics_json"])
        writer.writeheader()
        for item in settings:
            writer.writerow({key: item[key] for key in ["family", "scenario", "nodes", "trials"]} |
                            {"metrics_json": json.dumps(item["metrics"], sort_keys=True, separators=(",", ":"))})
    for ext in ["png", "svg"]:
        for name in ["election_convergence", "synthetic_localization_error",
                     "task_eligibility_comparison", "v_formation_spacing"]:
            copy_file(SOURCE / "figures" / (name+"."+ext), DEST / "S3_Supplementary_Figures" / (name+"."+ext))
    copy_file(REPO / "Docs" / "SWARM_EXPERIMENT_PROTOCOL.md",
              DEST / "Methods_and_Integrity" / "Supplementary_Experimental_Methods.md")
    copy_file(REPO / "Docs" / "EVIDENCE_CLAIM_TRACEABILITY.csv",
              DEST / "Methods_and_Integrity" / "Claim_to_Evidence_Traceability.csv")
    description = f"""# Supplementary Material: Quorum-Gated Authority in Decentralized UAV Swarms

**Version:** v1.0.0 (2026-11-10)  
**Manuscript:** *Quorum-Gated Authority and Safety–Availability Trade-offs in Decentralized UAV Swarms under Communication Faults*  
**Evidence type:** software-only, seeded simulations; no physical UAV data.

## File labels

- **S1 — Trial Observations:** \`S1_Trial_Observations/\` contains the complete
  **378** observed trial records, in CSV and JSON formats.
- **S2 — Setting Summaries:** \`S2_Setting_Summaries/\` contains the **63**
  experiment-setting summaries, including confidence intervals, in JSON and CSV.
- **S3 — Supplementary Figures:** \`S3_Supplementary_Figures/\` contains **four**
  data-grounded figures, each in PNG and SVG.
- **S4 — Methods and Integrity:** \`Methods_and_Integrity/\` contains the
  experimental protocol, original full report, source execution manifest,
  and claim-to-evidence traceability CSV.
- \`SHA256SUMS.txt\` provides file-level checksums.

## Source verification

- Archived original: GitHub Actions [run 42455738522](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/42455738522)
- Original artifact: \`seeded-swarm-experiment-evidence\`
- Evidence source revision: \`{EXPECTED_SOURCE_REVISION}\`
- Original \`trials.json\` SHA-256: \`{digest}\`
- Repetitions per setting: **6**
- Observations: **378** across **63** settings

This archive was copied and renamed only after its trial counts, source revision,
setting totals and the original SHA-256 were verified. S2 CSV is a lossless
transcription of the setting metadata and each setting's \`metrics\` object into
\`metrics_json\`. For exact structure, use S2 JSON.

**Scientific scope:** certified-leadership simulations, static geometry and
allocation, and synthetic known-reference acoustic estimation. This dataset does
not establish unrestricted Byzantine consensus, RF latency, aircraft collision
avoidance, or GNSS-denied autonomous flight.

**Note about earlier PDFs:** A previously described 150-page compiled
supplementary PDF is not part of the archived Actions artifact. These
verified dataset files are not a claim that those PDF copies were recovered.
"""
    (DEST / "README.md").write_text(description, encoding="utf-8")
    hashes = []
    for path in sorted(DEST.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            hashes.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(DEST).as_posix()}")
    (DEST / "SHA256SUMS.txt").write_text("\n".join(hashes)+"\n", encoding="utf-8")
    print(json.dumps({"destination":str(DEST),"raw_trials":len(trials),"settings":len(settings),
                      "files":len(hashes)+1,"trials_sha256":digest},sort_keys=True))

if __name__ == "__main__":
    main()
