# Step 7 — Frozen Design for Randomized Paired Software Pilot

**Date frozen:** 2026-11-16 (before any Step 7 pilot results). **Status:** *internal, prospective design specification*, not an externally registered study. Primary source lineage: Step 2 methodology and Step 3–6 software-only evidence; earlier 378 archived trials and the Step 4–6 handcrafted fixtures are **excluded** from this pilot.

## Narrow scientific question

Under randomized synthetic fleets and authentic encrypted, signed coordinator-received reports, how do independent freshness checking and peer-signed corroboration affect **offline ground-truth resource-ineligible assignment incidence** and **unassigned-task availability**, compared with unchanged production greedy allocation? The primary contrast is **strict corroboration gate vs production greedy**, paired on the same episode; secondary contrasts assess age-only, motion-only, opportunistic evidence, and simpler witness-vs-motion ablation. **The strict gate has additional evidence and may reject all requests**: it does not offer equal observability to a no-witness baseline and an improvement may simply represent refusal to operate.

## Predeclared sampling (pilot only)

- **Fleet sizes:** 5, 10, 20, 50.
- **Conditions:** `benign`, `benign_noise`, `stale_position`, `signed_false_health`, `signed_false_position`, `malicious_witness`, `colluding_witness`, `mixed_loss` (eight distinct strata).
- **30 independently derived random seeds per size × condition**, separated by SHA-256 from fixed root seed 2026, hence **4 × 8 × 30 = 960 independently generated simulation episodes**. Methods within each episode are **paired and correlated**. Each episode randomly draws positions, 2–6 task coordinates, report/health/sensor noise, feasible resources, attack magnitude and/or loss, and witness availability. The synthetic fault family is conditioned on the label, not sampled from real incident prevalence.
- **Exploratory pilot; no blinded holdout.** Its observed effects cannot be used to claim final confirmatory superiority; larger independent held-out validation and power analysis remain Step 8–9. Do **not** omit episodes that disagree with a hypothesis. A failed bootstrap, quorum, protocol or malformed case must fail CI rather than silently be excluded.
- Quorum: real `MeshNode` Ed25519+AES-GCM signed heartbeat reception and signed quorum ballots within a trusted fixed membership. A coordinator without fresh quorum abstains for **every policy**, including baseline.
- Epoch: 1, fixed per simulated episode; no network-wide Byzantine view changes/partition convergence or physical task execution is modeled. Packet loss impacts the **telemetry receiver**, not simulated auction gossip or wireless bit error rate.
- Observation times are **coordinator receipt time** for signed packets and peer-claimed observation time for signed witnesses. Neither attests physical capture time.
- Independent witness model is idealized: distinct enrolled signers report noisy readings of simulator truth; designated malicious signers may fabricate claims. This is a **simulation oracle used to generate a separate observation channel**, not a trusted sensor accessible to the tested algorithm. The algorithm receives signed claims only, with no truth values/labels.
- `colluding_witness` condition requires a self-falsifying member plus two lying witnesses; for N=5 this **exceeds** f=floor((N-1)/3)=1. Every episode explicitly records actual compromised count and whether the declaration is within f, so no theorem is inferred from all strata.
- Signed claim origin is not evidence truth. A single contradictory valid witness can deny service; strict two-witness corroboration cannot defeat two colluding witnesses or establish physical safety.

## Predeclared methods

Within each episode, all methods see the **same authenticated self-reported positions, health, timestamps, prior position history, signed peer witness objects, and task requests** (some policies deliberately ignore part of this information). Optimizer is unchanged production `allocate_tasks` in all five primary policies:

1. `greedy_signed`: original production greedy on fresh-health snapshots with any cached XYZ, gated by certified quorum.
2. `age_only`: freshness checks for health and position; motion/witness history deliberately omitted.
3. `motion_age`: freshness and previous-sample displacement bounds; no witness checks.
4. `witness_age`: age + signed witness inconsistency checks; deliberately omit displacement history.
5. `full_opportunistic`: age + motion + optional signed-witness disagreement veto; zero required corroborations.
6. `full_strict`: age + motion + at least two valid signed health witnesses per eligible member, otherwise requests evidence and abstains.

The policies use identical episode inputs, even when they ignore optional observations. Strict policy's effective observability/availability is **not** equivalent to age-only. A common-source Hungarian matching reference may be used later but is **not** being claimed as additional Step 7 evidence; full published CBBA comparison remains missing.

## Metrics and analysis

- **Primary metric:** per-episode boolean `any_ground_truth_resource_ineligible_assignment`, based on offline true battery < 30%, motor < 75%, link < 40% for any task assigned. **All requested tasks** contribute to availability denominators; never condition only on accepted assignments.
- **Secondary:** number of tasks assigned/unassigned, false refusal proxy = max(0, independently computed true-feasible oracle assigned count minus method assignment count), true-position travel-cost of assignments, task-assignment owner mismatch against the *offline true-state greedy oracle*, number of accepted/rejected/missing-evidence members, and episodes without fresh quorum. A mismatched assignment is **not** automatically physical danger.
- **Paired contrast:** risk difference in episode-level harmful assignment, strict gate minus greedy, with episode-cluster percentile-bootstrap **95%** interval (seeded 2027, fixed 500 resamples). Secondary comparisons and all multiple strata are **exploratory**, not multiplicity-corrected confirmatory p-values. Always report harm **and** coverage; a method that assigns zero tasks has zero observed assignment harm but zero availability.
- Report per-stratum numerator, denominator, and mean task coverage; explicitly avoid drawing general prevalence estimates from condition-balanced strata.
- No real radio/CPU benchmark, MAVLink simulator dynamics, independent sensor hardware, or collision/flight safety proofs.

## Reproduction / file lineage

```bash
python -m pytest -q test_swarm_independent_pilot.py
python swarm_independent_pilot.py --sizes 5 10 20 50 --trials 30 --seed 2026 \
  --out experiment_outputs/consistency-gated-step7-pilot
```

The pilot archives **raw episode observations separated from offline truth**, per-method per-episode task metrics, paired stratum summaries, frozen protocol reference, source SHA and SHA-256 file hashes. Save all failures (CI fails on attempted omitted episodes); do not silently mix in Step 4–6 fixed-layout diagnostics.

## Stop / revise conditions

- Real signed-receiver authentication must work and report the source as such; failure is a study failure, not a reason to backfill unauthenticated data.
- If a method is less available due to witness requirements, report that cost; do not optimize the paper to show only low unsafe rate.
- If signed-health falsification cannot be detected without independent observations, report that limitation; do not claim universal Byzantine detection.
- If malicious witnesses can trigger false denial or collusion defeats the gate, report both.
- This study does not close outstanding limitations: full published CBBA, dynamic recipient-side lease enforcement, robust witnessed evidence fusion, real heterogeneous mission dynamics, neutral source-of-witness comparison, and properly held-out confirmatory replication.

**Step 7 engineering exit:** actual randomized data generator, signed receiver tests, all four fleet sizes, at least 30 seeds/condition in CI, honest complete raw archive, reproducible statistical summaries and 9/9 CI (plus pilot job) pass. **Step 7 scientific exit remains a pilot, not final journal readiness.**
