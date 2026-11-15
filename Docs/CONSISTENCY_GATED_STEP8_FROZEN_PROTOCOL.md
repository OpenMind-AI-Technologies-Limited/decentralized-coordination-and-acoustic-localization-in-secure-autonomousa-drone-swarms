# Step 8 — Frozen Robust Witness / Motion Holdout Protocol

**Design frozen 2026-11-16, before Step 8 data.** This is an internally planned software simulation, not an externally registered experiment. Step 7 exploratory observations will **not** be reused.

## Hypothesis and negative cases

The Step 3 one-witness veto rejects a truthful drone when one validly signed witness lies. An opt-in **3-signer coordinate-wise median consistency rule** under **at most one malicious witness per observed subject** should ignore that outlier if two independent honest observers remain. This improvement is an expected property of an established statistic, not a demonstrated algorithmically novel contribution. Two colluding dishonest witnesses can defeat the rule. Missing 3-of-3 witnesses must produce HOLD / REQUEST_FRESH_EVIDENCE; an unverified sensor claim is not truth.

## Frozen sampling and seeds

- Fleets: 5, 10, 20, 50.
- Scenarios: benign, benign_noise, signed_false_health, signed_false_position, malicious_witness, colluding_witness, motion_jump, quorum_partition, mixed_loss.
- Development pipeline: SHA-256-derived root seed **82026**, 8 independently drawn episodes/stratum: **288 episodes**.
- Different heldout sample: root seed **82027**, 20 independent episodes/stratum: **720 episodes**. The Step 8 implementation must be fixed before viewing heldout effects; no post-hoc effect tuning. This is within one synthetic scenario family, not external replication.
- All methods receive the **same authenticated self reports, signed peer testimony and task requests** (although individual methods may ignore portions). The generator sees simulated truth to make physically unverified separate idealized peer claims; policy never sees truth.
- At N=5, a colluding self liar plus 2 dishonest witnesses exceeds the static declared f=1; preserve and annotate all such episodes rather than treating them as within bound.
- Motion_jump uses a source-signed physically impossible displacement beyond vmax=25m/s between two coordinator-received position reports; this is a purpose-built detectability case, not flight trajectory data.
- Quorum_partition makes post-bootstrap coordinator telemetry unavailable for >12s, so all policies must abstain. This is not asynchronous distributed leader-consensus analysis.

## Six prospective policies

1. greedy_signed: original baseline on authenticated receiver snapshot (and fresh quorum).
2. age_only: timestamp checks without witnesses or motion.
3. motion_age: timestamp plus bounded displacement.
4. veto_3: existing single-witness contradiction veto, requires 3 distinct signed health witnesses per eligible member.
5. median_3_age: coordinate-wise median of 3 distinct signed health witnesses, no motion history.
6. median_3_motion: same median rule plus local motion history.

For both median policies, health self-report differs from observed health median by >8 points in any of battery, motor or link => REJECT; insufficient distinct registered/fresh/signature-verified peer observations => REQUEST_FRESH_EVIDENCE. Invalid, old-epoch, duplicate identities never inflate quorum. Malicious witnesses are signed and can lie. No position witness requirement or guaranteed physical truth is claimed in the initial Step 8 run.

## Predeclared outcomes and inference

- Primary safety: episode has at least one assigned **offline true resource-ineligible** drone (battery<30%, motor<75%, link<40%), with zero-assignment episodes retained in denominator.
- Primary availability: mean **fraction of all requested tasks** assigned (never condition only on accepted assignments).
- Secondary: false-rejection of honest members, missing evidence, owner mismatch, true-space travel distance, quorum unavailability and colluding-reporter failures.
- Compare median vs veto and median vs age-only, paired by episode. Report per-stratum counts, effects and seeded 500-resample episode-cluster percentile 95% intervals (root 82028); many stratum contrasts remain exploratory, no multiplicity correction.
- Do not optimize on heldout outcomes or merge prior 378-trial / Step 4–7 data into these samples. Missing/corrupt cases must fail validation, not disappear.

## Exact evidence targets

Dev: 288 episode records × 6 policies = 1728 paired rows. Heldout: **720 episodes × 6 = 4320 paired rows**. 9 scenarios × 4 fleets × 6 methods = 216 heldout stratum summary rows. Persist receiver and offline truth records distinctly, policies, negative cases, integrity hashes and source revision. Test all six cross-platform Python matrices, native build and independent study CI jobs. No experimental numbers should be asserted until real CI artifact is successfully generated and independently inspected.

**Novelty gate:** A median of 3 is a standard robust method. Any gain over an arbitrary one-witness veto is evidence of correcting that vulnerability **only**, not proof of a novel publishable algorithm or physical Byzantine safety. Full CBBA equivalence, hardware/realistic dynamics, robust trusted sensing and Step 9 manuscript scientific integrity remain outstanding.
