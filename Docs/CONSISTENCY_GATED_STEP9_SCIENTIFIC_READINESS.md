# Step 9 — Independent Evidence, Research Integrity and Manuscript Readiness Review

**Review date:** 2026-11-16. **Source baseline:** merged Step 8 commit `f4e834ac73b0eba3cf6ce792d806d7d16620cade`.  
**Status:** reproducible diagnostic software evidence available; **novel-algorithm submission NO-GO**. This is not a journal acceptance or formal peer review.

## What has actually been validated

The independently recomputed Step 8 source artifact consists of 288 development and 720 separately seeded heldout software episodes; six policies on the same 720 heldout episodes produce 4,320 **paired, correlated** rows. Its source package is a real GitHub Actions archive, not a manuscript sample table. The static signed telemetry path exercises enrolled Ed25519, encrypted AES-GCM receiver code and certified quorum election, but is **not measured from flight hardware**.

The Step 9 script `research_step9_evidence_audit.py` reopens the **saved source files**, refuses omitted strata/episodes or changed SHA-256, independently derives the 64-bit SHA seed for every subject, checks trial and policy pairing, verifies reported task counts/capacity, recomputes resource-ineligible-assignment labels from **raw offline true health**, and recomputes three-dimensional true travel distance from archived XYZ. It also independently recalculates all 216 heldout descriptive strata, checks CSV ↔ JSON parity, and performs exploratory *paired episode-cluster* bootstrap contrasts. Every mismatch is fatal to the CI evidence job. Tampering and invalid-label regression tests specifically guard against merely changing the manifest hashes to hide changed data.

**New audit manifest** files produced by the Step 9 job: `scientific_evidence_audit.json`, `scientific_evidence_audit.md` and `audit_manifest.json`, bound to source hashes and archived alongside the Step 8 evidence in CI. A valid archive has neither proven manuscript novelty nor verified hardware outcomes.

## Observed heldout results, correct denominator

| Policy | Source episodes with ≥1 *true resource-ineligible* assignee | Mean task coverage |
|---|---:|---:|
| Authenticated-source Greedy | **63 / 720** | **88.89%** |
| Age-only | 59 / 720 | 88.25% |
| Age + motion | 59 / 720 | 88.16% |
| Conservative single-conflicting-witness veto, with three signed witnesses | **0 / 720** | 83.24% |
| Three-signer health-median only | **30 / 720** | 83.67% |
| Three-signer health-median plus motion | **30 / 720** | 83.48% |

**Interpretation:** Under balanced synthetic scenarios, median+motion has **4.17 percentage points more episodes with a resource-ineligible assignment** than conservative veto, with only **approximately 0.24 percentage points greater mean task coverage**. This does **not** favor a universal safety claim for the median. Compared with age-only, the median has lower harmful-assignment frequency but also lower coverage and receives additional idealized independently signed peer observations. Policies have the same *available* observation bundle in Step 8, not the same *used* evidence under their definitions.

The conservative veto’s **0/720** does not prove zero true error rate; even under an independent-binomial approximation, the 95% Wilson upper bound would be about **0.53%** for *this synthetic mixture only*. The balanced-scenario sampling is not a deployment frequency distribution, and the episodes are not real missions. Do not report this interval as a hardware failure-rate bound or Byzantine proof.

**One Byzantine signed witness:** the median reduces wrongful veto on honestly resource-capable subjects under the generator's two independently truthful observer assumption. **Two colluding signed witnesses:** the median may accept false member health; the witnessed f_w=1 assumption is violated even for larger fleets whose *overall* quorum fault bound may tolerate three compromised actors. **Kinematic jump:** the purposely impossible signed pose displacement is detectable with motion history, but this does not verify plausible signed position spoofing or physical sensor truth.

## Critical scientific gaps with publication impact

| Priority | Blocker / audit finding | Required next evidence or claim restriction |
|---|---|---|
| P0 | Median of three is an established statistic. The heldout data reject a claim of strict safety–availability superiority over the matched conservative veto. | Reframe as reproducible empirical negative-results/limits **or** develop an independently justified genuinely novel method and test it on *new* prospective data; do not retrofit existing heldout numbers |
| P0 | Offline resource ineligibility is **not** collision, navigation, command authenticity, mission completion or physical safety. | Restrict endpoints to reported software resource feasibility; formulate and independently evaluate trajectory/mission endpoints if needed |
| P0 | Archive does not contain full original signed peer-witness payloads, reporter signatures, encrypted packets or leader vote envelopes. | Audit confirms metrics, not independent cryptographic replay of all source messages. For future datasets log sanitized signed testimony with public keys and verification traces, without leaking secrets |
| P0 | Two colluding witnesses compromise the assumed local health-median bound. | Threat-model signer-specific f_w separately from overall fleet quorum; evaluate variable coalition sizes, sensor correlation and majority fault cases without sweeping failures into a general claim |
| P1 | Step 5's additive auction is **not** full CBBA; no faithful published CBBA implementation or equal network constraints. | Implement and validate a reference CBBA with path-dependent bundle insertion and realistic consensus, or remove full CBBA comparison/competitiveness claim entirely |
| P1 | Witness reports in simulation are generated from oracle truth as idealized independent observations; signatures authenticate issuer, not truth. | Source independence/provenance measurement or explicit simulations with correlated/biased sensors and verifiable witness information budgets |
| P1 | Quorum partition withholds coordinator telemetry after bootstrap; no split-brain network replay, durable consensus or physical lease enforcement. | For claims about eventual recovery under real partitions, implement recipient-side version/lease enforcement, remote receipt channel, replicated state and evaluate liveness |
| P1 | Motion-jump attacker is deliberately detectable; plausible false positions are not independently verified. | Test bounded slow drift, physically plausible forged trajectories, position witnesses and regret/travel penalties |
| P1 | `false_rejected_healthy_members` flags all resource-eligible rejected members, **including appropriate rejection of impossible-XYZ reports**. | Do not publish as global false-positive rate; construct separate truth label for honest and plausible position sources in a new dataset |
| P1 | 720 episodes use fixed synthetic per-scenario sampling; paired bootstrap is exploratory, no external preregistration, no multiplicity-adjusted claims. | Register prospectively defined primary effect and holdout outside examined source, sample-size justification, adjusted multiple comparisons and generalization limits before a confirmatory paper |
| P2 | No independent real CPU/network latency or energy/flight workload benchmarks for the new evidence fusion. | Report software cost, witness message budget, bounded memory and decision latency under reproducible systems if comparing operational overhead |
| P2 | The published code retains earlier Step 1–8 artificial fixed-layout fixtures and the old 378 source observations. | Continue strict dataset lineage and evidence hash separation; disclose all independent/diagnostic dataset roles |

## Verifiable literature / novelty guardrail

Choi, Brunet and How, *Consensus-Based Decentralized Auctions for Robust Task Allocation*, **IEEE Transactions on Robotics** 25(4), 912–926 (2009), DOI: https://doi.org/10.1109/TRO.2009.2022423. The paper explicitly distinguishes CBAA single-assignment from the multi-assignment CBBA and contains consensus/bundle mechanics **not implemented in the current static-additive simplified baseline**. Never cite its published convergence properties as proven properties of this code.

A signed witness's coordinate-wise median and an age/speed check are standard building blocks. The reported Step 8 result provides a **repeatable empirical comparison of those policies in a synthetic threat model**; that alone does not constitute a previously unreported robust allocation algorithm or Byzantine theorem. A fuller, dated systematic literature novelty check is necessary before journal selection.

## Recommended nonmisleading Step 10 paper path

**Option A, evidence-aligned:** working title *When Signed Witnesses Disagree: Safety–Availability Limits of Consistency-Gated Task Allocation in Simulated UAV Swarms*. Frame as a reproducible empirical negative-results/ablation study, with honest scenarios, signed-false health and position, one- and two-witness attacks, stale telemetry and virtual partition. Describe both wins and failures, with one predeclared resource-feasibility endpoint and mission-coverage tradeoff. Claims must be limited to a particular simulation model; suitability for a particular peer-reviewed journal is not guaranteed.

**Option B, original-method paper:** first justify and implement a genuinely differentiated evidence-fusion / task-allocation contribution with explicit threat-budget and shared-witness information guarantees; compare fairly with full reference CBBA and robust aggregation baselines, freeze *new* development/holdout distributions, then redo formal/empirical validation. Do not reuse Step 8 examined heldout data as a prospective test.

**Step 9 engineering completion condition:** code and tests, independent full-data validation, audit artifact, limitations and claim ledger in GitHub, CI green, and reference evidence/provenance preserved. **Scientific submission gate remains NO-GO** unless the manuscript follows the accurately limited path and its novelty, reference and venue-specific requirements are independently met.

## Reproduction

```bash
python -m pytest -q test_research_step9_evidence_audit.py

# After the Step 8 frozen dev/heldout outputs have been generated:
python research_step9_evidence_audit.py \
  --development experiment_outputs/consistency-gated-step8/development \
  --heldout experiment_outputs/consistency-gated-step8/heldout \
  --out experiment_outputs/consistency-gated-step9-audit
```

This step makes no direct changes to Step 8 algorithm parameters, source random seeds or archived original evidence. The new audit is **post-hoc and transparent**, not a fresh independent confirmatory outcome.
