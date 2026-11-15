# Step 8 — Verified Robust Witness Holdout: Results and Scientific Verdict

**Observed:** 2026-11-16, after the prospective local study protocol was committed.  
**Exact source SHA for measured archive:** 7ada98ec78c966efc78c2a446ddfb0eb67d7c8cf  
**CI run:** https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43766097557  
**Step 8 archive:** https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43766097557/artifacts/14181798087  
**Frozen design:** [CONSISTENCY_GATED_STEP8_FROZEN_PROTOCOL.md](CONSISTENCY_GATED_STEP8_FROZEN_PROTOCOL.md)

These results were extracted from the **actual GitHub Actions ZIP artifact** and independently checked against all manifest SHA-256 digests. The Step 8 development run produced **288** independent synthetic source episodes and **1,728** correlated policy rows. The prospectively separate heldout root produced **720** synthetic episodes, **4,320** policy rows and **216** per-fleet/per-scenario/policy summary records. Results below use **heldout only** unless explicitly labeled development. Previous Step 7 results remain excluded.

## Full heldout primary safety–availability results

The **safety** column is the count of independent episodes with one or more assigned members whose offline true **battery/motor/link** values violate the declared resource thresholds. **Coverage** is the average proportion of all requested tasks allocated, including episodes in which all policies correctly refuse without fresh quorum.

| Policy | Ground-truth resource-ineligible assignment episodes / 720 | Mean task coverage | Mean unassigned tasks per episode |
|---|---:|---:|---:|
| Authenticated source-report greedy | **63 / 720** | 88.89% | 0.433 |
| Age-only gate | **59 / 720** | 88.25% | 0.461 |
| Age + motion gate | **59 / 720** | 88.16% | 0.465 |
| Original single-conflict veto (3 signed witnesses) | **0 / 720** | 83.24% | 0.676 |
| Three-witness median, no motion | **30 / 720** | 83.67% | 0.657 |
| Three-witness median + motion | **30 / 720** | 83.48% | 0.665 |

These are **balanced synthetic** stress scenarios, not incident prevalence or real UAV task success. Different policies deliberately ignore/use different parts of an otherwise common observation bundle; no physical sensor truth or actual task completion is measured.

**Decisive result:** The new quorum-median algorithm is **not unambiguously superior to the single-conflict veto**. It improves resistance to a *single malicious witness falsely rejecting an honest member*, but this comes with **30/720 heldout episodes of resource-ineligible assignment**, compared to **0/720** for the conservative veto. The median's overall task coverage exceeds veto only by about **0.24 percentage points**. This is a safety–availability **trade-off**, not a strict improvement.

## Key heldout conditions (80 episodes per scenario: four fleet sizes × 20 independent seeds)

| Condition | Single-conflict veto: harmful episodes / mean task coverage | Three-witness median + motion: harmful episodes / mean task coverage | Interpretation |
|---|---|---|---|
| Honest control | 0/80 / 99.0% | 0/80 / 99.0% | Equivalent in this condition |
| Signed false health | **0/80 / 95.3%** | **0/80 / 95.3%** | Both reject independently contradicted self-report |
| Single malicious witness | 0/80 / **94.5%** | 0/80 / **96.4%** | Median avoids unilateral false veto under independent-honest-majority assumption |
| Two colluding witnesses | **0/80 / 96.9%** | **30/80 / 98.8%** | Median accepts some falsified health, so extra coverage includes dangerous decisions |
| Benign sensor noise | 0/80 / 97.9% | 0/80 / 97.9% | Median reduces unnecessary rejections, but coverage is unchanged due spare capacity |
| Motion jump | 0/80 / 98.9% | 0/80 / 97.2% | Motion gate rejects implausible signed XYZ, but the **resource-only** primary endpoint cannot capture position spoofing |
| Mixed packet loss | 0/80 / 68.5% | 0/80 / 68.5% | Required 3-of-3 testimony produces substantial availability loss relative to age-only (95.8%) |
| No-quorum partition | 0/80 / 0% | 0/80 / 0% | All tested methods abstain without fresh signed quorum |
| Signed false position | 0/80 / 98.3% | 0/80 / 98.3% | No position witnesses; physically plausible position lies remain unverified |

**Malicious witness false-veto mechanism:** In the 80 malicious-witness episodes, the old veto rejected on average **0.800 otherwise resource-eligible members per episode**, while median + motion rejected **0.000**. This is an observed rule-specific benefit; it does not demonstrate a novel statistical technique.

**Benign noise:** The existing veto rejected on average 0.787 otherwise resource-eligible members/episode, versus 0.350 for median + motion, without changing allocated-task coverage.

**Motion stress:** All source reports were authenticated; the crafted impossible-jump condition resulted in 69/80 age-only decisions assigning the spoofing target, versus 0/80 when motion plausibility was enforced. This is a deliberately generated detectability stress, **not** collision avoidance, independent sensor truth or an unbiased frequency estimate.

**Explicit witness threat budget:** Two colluding peer witnesses + the self-falsifying source mean three compromised actors. For N=5 that **exceeds** declared general f=1 (20/80 colluding episodes); for N=10/20/50 it is within the configured general f bound (60/80). However the median's **assumed witness-specific f_w=1** is exceeded whenever two signed witnesses collude, including those N=10/20/50 cases. A global quorum election fault threshold is NOT an automatic truthful-sensing guarantee.

## Exploratory paired effects, heldout only

All contrasted policies were evaluated on the **same 720 episode units**, so rows from multiple policies are not independent samples. Additional pooled balanced-scenario contrasts below were calculated post-hoc from heldout pairs using 500 seeded episode-bootstrap resamples; these intervals are **exploratory**, not adjusted for multiple hypotheses or external generalization.

| Contrast: median + motion minus comparator | Safety harmful-episode risk difference (95% bootstrap interval) | Assigned-task coverage difference (95% bootstrap interval) |
|---|---|---|
| Versus single-conflict veto | **+4.17 pp** (+2.78 to +5.69 pp) | **+0.24 pp** (−0.04 to +0.53 pp) |
| Versus age-only | **−4.03 pp** (−5.69 to −2.50 pp) | **−4.77 pp** (−5.93 to −3.71 pp) |
| Versus median without motion | **0.00 pp** (0.00 to 0.00 pp) | **−0.18 pp** (−0.33 to −0.05 pp) |

Interpretation: Median reduces harmful decisions compared with age-only by using **additional modeled independent witness evidence**, but also reduces mission availability. Compared with the **same-information single-veto baseline**, the median's gain against isolated malicious-witness denial is offset by unsafe collusion outcomes in this balanced synthetic mixture.

## Important measurement caveat found during audit

The raw output metric named `false_rejected_healthy_members` literally counts **rejected resource-eligible members**, regardless of whether they falsified their position. In the `motion_jump` attack condition, **rejecting a resource-eligible member that just reported an impossible signed position jump is appropriate defensive behavior**, *not* an actual false-positive rejection. Thus that field must **not be presented as a global false-rejection-rate estimate**. The honest benign/noise and malicious-witness conditions are more meaningful for measuring witness-veto errors; subsequent work should introduce a correctly distinguished `rejected_honest_fresh_position_member` metric on new independent data, without relabeling previously observed values.

Other limitations: no verified physical sensor capture timestamps; position-only plausibly falsified telemetry can evade the health witness rule; coordinated malicious witness majority evades median; 3-of-3 quorum is unavailable under packet loss; no external preregistration, no accepted full CBBA reference, no real radio/UAV flight or independent hardware attestation; assignment is static, not proof of safe dynamic mission completion.

## Artifact integrity / reproducibility

The archive has 10 files (five under each dev/heldout folder); four primary heldout evidence SHA-256 values:

| Heldout file | Verified SHA-256 |
|---|---|
| episodes.json | `4481e74616cd0225de749bb8328fb2fd8d12103d36b34f869bb4fa1b1cd405e2` |
| paired_policies.json | `7192ce40f3fa5f00617203b77a03ac1e62b8ee69bc67d9bd8edbc774bd79029d` |
| paired_metrics.csv | `3077c7f4fb46dce06ad44f217d111db9b3ab25bb900c094083e88e1739113e72` |
| stratum_summaries.json | `402e4c2f97d83d8748c42892c179f9dde1f34909b40370d10cb9f7e62a258161` |

Source revision and exact manifest are inside both archive folders. An additional report commit changes **documentation only**; it does not replace the cited already-run evidence. All observed raw failures were retained; no favourable-subset filtering was applied. Step 7 earlier archive, 378 historical trials, Step 4–6 fixed-scenario diagnostics remain separate.

## Scientific Step 8 decision

**Engineering GO:** real-crypto simulator integration, independently seeded heldout, source separation, 3-signer median rule, adversarial controls, negative cases, raw artifact and full integrity checks succeeded.

**Scientific novelty/overall security claim: NO-GO.** A standard coordinate-wise median of three authentic reports, with fault-budget assumptions and lower availability, is not a standalone original robust-UAV-allocation algorithm. The heldout data actually show more unsafe decisions than an equally informed conservative witness veto in colluding conditions, so any claim that the new approach uniformly dominates earlier methods is **falsified by the current evidence**.

**Step 9 priority:** Either (a) create and validate a genuinely differentiated, conservative-but-available algorithm with explicit *witness confidence under varying coalition sizes* and a predefined independent observation model, comparing to published robust aggregators and full CBBA under equal communication, or (b) reposition the paper as a rigorous, reproducible *negative-results / safety–availability limits* study. Do not submit a superiority paper on these results.
