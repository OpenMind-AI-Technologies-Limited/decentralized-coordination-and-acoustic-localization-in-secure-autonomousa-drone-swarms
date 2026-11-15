# Research Step 5 — Common-Information Task-Allocation Baselines

**Date:** 2026-11-15  
**Candidate paper:** *Consistency-Gated Task Allocation for Decentralized UAV Swarms Under Stale and Byzantine-Falsified Telemetry*  
**Source:** [Step 2 protocol](CONSISTENCY_GATED_STEP2_EXPERIMENTAL_PROTOCOL.md), [Step 3 prototype](CONSISTENCY_GATED_STEP3_ALGORITHM.md), [Step 4 fault model](CONSISTENCY_GATED_STEP4_ATTACK_FRAMEWORK.md).

**Research status:** Comparator implementation + diagnostic paired replay. This is **not** a full CBBA or publication-grade comparison to state-of-the-art under independent flight/network episodes, and does not demonstrate statistical superiority. No research claims should exceed this scope.

## What is implemented

| Method label | Implementation | Strength / exact scope |
|---|---|---|
| `greedy` | Original `swarm_tasks.allocate_tasks()` unchanged | Deterministic sequential greedy using reported 3D Euclidean distance and health penalties |
| `hungarian` | `scipy.optimize.linear_sum_assignment` with capacity-replicated drone slots and private dummy task columns | Optimal maximum-cardinality, then minimum-total-reported-cost **under this one-shot additive model**, centralized non-deployable full-information optimizer |
| `cbaa` | Synchronous single-task consensus-based auction (CBAA-style special case) | Each idle agent bids on cheapest unassigned job, reliable all-to-all deterministic conflict resolution; **not** multi-task CBBA |
| `cbba_static` | Synchronous static additive bundle-auction specialization | Agents propose bundles of their cheapest unassigned jobs, bid conflicts resolved by common consensus; supports >1 slot/node; **does not implement general path-dependent/asynchronous CBBA** |

**Terminology:** Choi, Brunet and How introduced CBAA as the single-assignment auction and CBBA as a generalized bundle-based method. This study never labels a CBAA implementation as full CBBA. The static additive bundle implementation is explicitly a limited **CBBA-like specialization**, and remains unsuitable as a verified published CBBA comparator until full route-dependent scoring and consensus equivalence are reviewed. See [Choi et al., IEEE T-RO 2009](https://doi.org/10.1109/TRO.2009.2022423), and [Brunet's thesis](https://dspace.mit.edu/entities/publication/53d56696-45cf-46f5-bbde-fc39e88da869).

The exact assignment solution uses [SciPy's linear_sum_assignment](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html); its optimization scope is bounded by the defined task cost, feasible membership and capacity. It is **not** guaranteed physically safe, energy-optimal or best for future task sequences.

## Fairness, feasibility, objective

- Every method sees **exactly the same** accepted member list, signed-receiver-reported positions, health reports, tasks and constraints within an information cohort.
- Eligibility: member's reported battery >=30%, motor >=75%, link >=40%. Same as existing greedy.
- Position validity: finite 3D XYZ. Tasks are finite 3D coordinates with target altitude 1..100 m.
- Cost, unchanged from production: `distance(node_xyz, task_xyz) + 0.35*(100-battery) + 0.50*(100-motor) + 0.15*(100-link)`. Same task IDs sorted lexically.
- Assignment: every job at most once, maximum one job/member in the primary paired experiment. The Hungarian solver can repeat a member as a limited set of slots and a static bundle-auction special case can handle capacity>1. Duplicate assignments prohibited.
- Hungarian uses dummy unassigned task columns with a **finite penalty strictly above the sum bound of feasible real allocations**, yielding maximum feasible task coverage before minimizing total reported cost.
- Greedy, auction, Hungarian all solve decisions with **reported** information; the **offline oracle** is computed separately by Hungarian on true simulated state. No optimizer receives offline labels or true positions.
- Do not compare raw **total cost** between methods that assign different numbers of tasks without accounting for coverage or penalty; the runner separately records both counts and costs.
- CBAA and static bundle logical bid-message counts assume **perfect synchronous all-to-all messages** over a connected virtual mesh. Counts are not real radio bytes, flight telemetry or delay under intermittent partitions. The optimizer stage does **not** use the Step 4 packet scheduler to deliver individual auction bids.

## Information-cohort separation

Data come from the **actual signed & encrypted Step 4 member-to-coordinator receiver snapshots**. Step 5 enriches each original single-task synthetic fault case with **two deterministic extra task coordinates generated only from seed**. The same 3 tasks are offered to all four methods within a given episode.

Three cohorts must never be pooled or treated as equally informed:

1. `self_reports`: all reported eligible healthy drone positions and health from the same encrypted authenticated coordinator snapshot.
2. `age_motion_gate`: *exactly* the member ACCEPT mask yielded by Step 4's gate; same observations (no new witness reports).
3. `strict_synthetic_witness_gate`: uses ACCEPT mask from two-peer witness policy; **additional synthetic independent measurements when present**, hence an information advantage, but possible malicious/absent witnesses also generate false denial or total abstention.

Each cohort is evaluated under `greedy`, `hungarian`, `cbaa`, `cbba_static`. Comparisons between allocators **within one cohort** are equal-information and equal-task-cost (with the caveat that auctions have a perfect-connectivity model). Differences **across cohorts** measure the combined effects of filtering, witness information and evidence availability, NOT an isolated new algorithm optimizer contribution.

The offline truth comparison separately measures `ineligible_assignments_offline`, `matches_offline_assignment`, `offline_true_total_distance_m`, and `offline_true_total_penalized_cost`; no ground truth is used in an allocator's output. `matches_offline_assignment` is an exact matching diagnostic; it is **not** a collision, mission completion or hardware safety metric.

## Execution and raw evidence

```bash
python -m pytest -q test_swarm_allocation_baselines.py
python swarm_baseline_comparison.py \
  --sizes 5 10 --trials 2 --seed 2026 \
  --out experiment_outputs/consistency-gated-step5
```

Default: **13 Step 4 fault types × 2 fleet sizes × 2 seeded repeats = 52 source episodes**, each with **3 information cohorts × 4 optimizers = 12 paired comparator rows**. Expected 624 diagnostic output rows (not 624 independent experiments).

Generated data:

- `signed_episode_snapshots.json`: separate signed coordinator observations, offline truth and virtual network counters for each 52 source episodes. Contains **no private keys, ciphertext or live access tokens**.
- `paired_baseline_trials.json`: each optimizer's assignment, cost, member count, loss/abstention, offline diagnostics, logical consensus message count and information advantage label.
- `paired_baseline_metrics.csv`: one tabular row per paired comparator.
- `manifest.json`: source revision, assumptions, row count, exact SHA-256 of each output, source-to-prior-archive separation and no-hardware/no-full-CBBA limitations.

Tests include: production greedy exact output parity, independent brute-force verification of Hungarian minimum cost on a small complete matching, a greedy counterexample, infeasible-member exclusion, capacity/duplicate checks, randomized varied task sets and comparison replay source isolation and checksum verification.

**Statistical warning:** source Step 4 scenes use a fixed adversarial layout, with randomness largely in virtual packet delays/loss. Different optimizers on one scenario are deliberately **paired correlated records**. There is no empirical incident prevalence estimate, generalized gain, formal robustness proof, physical radio estimate, end-to-end flight safety or inferential improvement claim. Publication-grade evaluation must use independently varied target/drone/attack/witness distributions, validated CBBA, truly comparable communication constraints and prospective held-out independent seeds.

## Remaining gaps and stage gates

- **Full CBBA fidelity remains outstanding**: implement and cross-check the published path-dependent bundle insertion and timestamped peer consensus with a supported reference, or label clearly as static specialization and select a different peer-reviewed matching implementation. **Do not** cite this simplified auction as a faithful CBBA benchmark.
- **Real network partition auction liveness remains untested**: the Step 4 network fault scheduler affects telemetry receipts, but the auction phase uses idealized globally visible bids.
- **Witness information budget is not yet balanced** across observational policies; equal-informed age/witness controls and adversarial false-report channels need further work.
- **Dynamic task release/reassignment** with persistent task IDs, idempotent ownership, timeout and eventual reconciliation is Step 6.
- **New independent randomized experiments** and proper episode-level inference are Steps 7–9. Selection of seeds/settings must be frozen beforehand.
- If Hungarian or a simple age-only policy already gives equivalent benefit, report it; do not claim a novel gain without evidence.

**Step 5 code gate:** comparative optimizers, paired replay pipeline, tests, checksum-bound new artifacts and 9/9 CI; this qualifies as a **scoped comparator implementation**, not completion of the full originally envisioned research-grade CBBA comparison.
