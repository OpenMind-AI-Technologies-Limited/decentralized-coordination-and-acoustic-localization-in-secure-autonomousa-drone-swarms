# Step 10 — Evidence, Reference, Reproduction and Overlap Index

**Compiled:** 2026-11-16. This index accompanies [the Step 10 manuscript](CONSISTENCY_GATED_STEP10_MANUSCRIPT.md). All data provenance below refers to **simulated software results**, not UAV field tests. Raw research artifacts may expire under GitHub Actions retention; no permanent DOI deposit has been verified.

## 1. Primary evidence: Step 8 internally frozen heldout

- Source revision that produced the verified observed results: `7ada98ec78c966efc78c2a446ddfb0eb67d7c8cf`.
- [CI evidence run 43766097557](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43766097557), [archived Step 8 dev + heldout artifact 14181798087](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43766097557/artifacts/14181798087).
- Frozen protocol: [Step 8 experimental design](CONSISTENCY_GATED_STEP8_FROZEN_PROTOCOL.md). Findings: [Step 8 observed negative and positive results](CONSISTENCY_GATED_STEP8_HELDOUT_FINDINGS.md).
- Dataset role: **development: 288 independent source episodes / 1,728 correlated method rows**; **heldout: 720 source episodes / 4,320 correlated method rows / 216 strata summaries**.
- Fleet sizes 5, 10, 20, 50; nine controlled scenario labels; 20 heldout seeds per size/condition.
- Core result (Step 8 heldout): Conservative veto 0/720 resource-ineligible-episode observations at 83.24% mean requested-task coverage; three-witness median + motion 30/720 at 83.48%. **These proportions are not field incident prevalence, and more coverage is not automatically safer.**

**Original verified SHA-256 values for archived heldout members (relative to `heldout/`):**

| File | SHA-256 |
|---|---|
| `episodes.json` | `4481e74616cd0225de749bb8328fb2fd8d12103d36b34f869bb4fa1b1cd405e2` |
| `paired_policies.json` | `7192ce40f3fa5f00617203b77a03ac1e62b8ee69bc67d9bd8edbc774bd79029d` |
| `paired_metrics.csv` | `3077c7f4fb46dce06ad44f217d111db9b3ab25bb900c094083e88e1739113e72` |
| `stratum_summaries.json` | `402e4c2f97d83d8748c42892c179f9dde1f34909b40370d10cb9f7e62a258161` |

Keep original file hashes in any final supplementary archive. A fresh CI run may use another `GITHUB_SHA` but must preserve the frozen sample design and per-record outcomes to be described as a replication.

## 2. Independent Step 9 metric audit

- Baseline merged audit commit: `311f1f72e38cb8d1d2fa8e6a04217212c3e6b4f8`.
- [Verified merged-main run 43769505624](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43769505624) and [independent audit artifact 14183631737](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43769505624/artifacts/14183631737).
- Auditor: `research_step9_evidence_audit.py`; adversarial and tamper-detection tests: `test_research_step9_evidence_audit.py`.
- Checks all 4,320 heldout paired rows for source episode linkage, duplicate task owner/job, offline resource feasibility, true-space distance, CSV↔JSON parity, all 216 reported stratum summaries, original stratum bootstrap intervals, unique roots/seeds and exact source SHA-256 hashes.
- Independent audit has **no raw signed witness-envelope record** and therefore cannot validate every original signature from archive bytes. Fresh simulator re-execution tests Ed25519/AES-GCM code, a different evidence category.
- Original Step 9 review: [scientific readiness](CONSISTENCY_GATED_STEP9_SCIENTIFIC_READINESS.md), [claim register](CONSISTENCY_GATED_STEP9_CLAIM_REGISTER.md).

## 3. Earlier pilot and supporting diagnostics (NOT pooled)

- Exploratory Step 7 different-policy pilot: **960 episodes and 5,760 correlated method rows**; [Step 7 artifact](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43763763709/artifacts/14181059661) and [Step 7 findings](CONSISTENCY_GATED_STEP7_PILOT_FINDINGS.md). Development-only background; **do not add** these rows to Step 8 heldout denominators.
- Step 5 comparator diagnostic: 52 signed-fault episodes, 624 matched information-policy/optimizer rows; **not** 624 independent trials; static auction specialization is **not full CBBA**.
- Step 6 simulated task recovery diagnostic: 40 hand-selected episodes; signed STOPPED is **not proof of physical stop**.
- Legacy `research_paper.md` and 378 observation supplementary archive concern **previous authenticated swarm coordination, formation, and acoustic modules**. They are separate scientific outputs and cannot be presented as independent evidence for the new Step 8 witness experiment.
- The older simultaneous/prior papers described in [Step 1 research gap audit](CONSISTENCY_GATED_STEP1_RESEARCH_GAP_AUDIT.md) require editorial disclosure and overlap review. **Do not combine text, figures, or repeated results without attribution and permission.**

## 4. Literature search and claim restrictions

A targeted (not exhaustive) publisher-level review on 2026-11-16 confirms six works listed in the manuscript and in `CONSISTENCY_GATED_STEP10_REFERENCES.json`. Particularly important:

- Zhao et al., July 2026, *Drones*, DOI `10.3390/drones10070523`: assignment-consistency certificates, interval bids and stale/asymmetric information. **High topical overlap with the phrase 'consistency-gated allocation'**; do not assert first invention.
- Choi, Brunet and How, *IEEE Transactions on Robotics* (2009), DOI `10.1109/TRO.2009.2022423`: actual CBAA and CBBA definitions and conditions. Simplified additive auction diagnostics are not the paper's CBBA.
- Raja, Habibi and How, *IEEE Access* (2022), DOI `10.1109/ACCESS.2021.3138857`: communication-aware CBBA and constrained links.
- Liu et al., *Reliability Engineering & System Safety* (2026), DOI `10.1016/j.ress.2026.112442`: resilient local-information swarm allocation.
- Gerkey and Matarić, *International Journal of Robotics Research* (2004), DOI `10.1177/0278364904045564`: MRTA taxonomy.
- Lamport, Shostak and Pease, *ACM TOPLAS* (1982), DOI `10.1145/357172.357176`: historical Byzantine agreement model, not a proof of this repo's protocol.

A systematic novelty search across recent UAV scheduling, resilient median aggregation, multi-sensor trust, Byzantine sensing and network constraints remains uncompleted. A **six-reference draft** is not necessarily an acceptable journal literature review; no journal has been selected.

## 5. Reproduction and preservation

```bash
python -m pip install cryptography pytest
python -m pytest -q test_swarm_robust_holdout.py test_research_step9_evidence_audit.py

python swarm_robust_holdout.py --sample development --sizes 5 10 20 50 \
  --out experiment_outputs/consistency-gated-step8/development
python swarm_robust_holdout.py --sample heldout --sizes 5 10 20 50 \
  --out experiment_outputs/consistency-gated-step8/heldout
python research_step9_evidence_audit.py \
  --development experiment_outputs/consistency-gated-step8/development \
  --heldout experiment_outputs/consistency-gated-step8/heldout \
  --out experiment_outputs/consistency-gated-step9-audit

# Step 10 manuscript consistency and evidence verification:
python research_step10_submission_audit.py \
  --manuscript Docs/CONSISTENCY_GATED_STEP10_MANUSCRIPT.md \
  --references Docs/CONSISTENCY_GATED_STEP10_REFERENCES.json \
  --audit experiment_outputs/consistency-gated-step9-audit/scientific_evidence_audit.json \
  --out experiment_outputs/consistency-gated-step10-submission-audit
```

If publishing the data independently, create an immutable dated release or Zenodo DOI from **the exact verified source archive**, attach the full manifest and method/version notes, and ensure author approval. Do not republish original signed packet secrets. For independent cryptographic replay, future runs must log sanitized full signed claim envelopes, public key mappings and verifier outcomes without secret keys or personally identifying information.

## 6. Scientific final gate

**Engineering manuscript package:** assembled with automated claim/evidence checks.  
**Original superior allocation algorithm:** **NO-GO** (median did not dominate equally observed veto).  
**Empirical negative-results article:** a **candidate framing**, not an established novelty acceptance.  
**Submission:** **HOLD** pending author/declarations, literature completeness, related-manuscript overlap, permanent evidence deposit and venue fit. Publishing/reviewing the software results under precise limitations may be scientifically valuable, but it is not equivalent to a ready-to-submit original-algorithm paper.
