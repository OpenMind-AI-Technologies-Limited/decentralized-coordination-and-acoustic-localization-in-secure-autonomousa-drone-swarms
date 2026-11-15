# Research Step 2 — Threat Model, Research Questions and Prospective Experimental Protocol

**Draft date:** 2026-11-15  
**Working title:** *Consistency-Gated Task Allocation for Decentralized UAV Swarms Under Stale and Byzantine-Falsified Telemetry*  
**Parent audit:** [CONSISTENCY_GATED_STEP1_RESEARCH_GAP_AUDIT.md](CONSISTENCY_GATED_STEP1_RESEARCH_GAP_AUDIT.md)  
**Status:** Research design and baseline incident reproduction; the proposed consistency gate and publication-scale experiments **are not yet implemented**. This protocol is written prospectively before the proposed new algorithm is implemented, but it is **not an externally registered preregistration**.

## Scope and architecture

The repository has independent authenticated MeshNode agents and a quorum-certified coordinator that selects tasks. It is **not a leaderless task-allocation consensus service**. The experimental subject is a **simulation-only decision layer** between signed telemetry intake and a task allocator. No physical flight, radio-link characteristics, real hardware battery or sensor truth, real-world safety certification or formal arbitrary-Byzantine consensus is asserted.

Existing authenticated packets use Ed25519 and AES-GCM. Authentication establishes origin and tamper resistance of the packet, **not truth** of reported telemetry. Current health reports include a last-received time; cached XYZ coordinates do not have independent last-observed metadata. A health-only update can therefore leave an old position in the coordinator's cache. Step 2 captures this behavior using the actual MeshNode packet verifier, virtual time, signed elections and the actual DroneMeshSimulation.command_tasks() allocation path, **without flight control or active UDP peer threads**.

## Questions, estimands and falsifiable hypotheses

| ID | Research question | Null hypothesis / possible disconfirming outcome | Primary evidence |
|---|---|---|---|
| RQ1 | Does fresh signed health coexist with a stale cached XYZ that changes the current authorized task decision? | The observed baseline plan equals a ground-truth-data counterfactual across targeted and replicated scenarios | Actual signed packet trace; deterministic baseline probe; incident-level candidate/assignment comparison |
| RQ2 | Can independent, explicitly bounded consistency evidence reduce assignment to ground-truth-ineligible members compared with age-only and current greedy controls? | No meaningful paired reduction relative to strongest fair comparison; false rejections may dominate | New attack-fault trials, common observation budgets, paired harmful-assignment rate and rate difference |
| RQ3 | What is the availability/cost of abstaining or requesting new evidence under loss, stale measurements and partially compromised membership? | Any reduced false acceptance is offset by unjustified lost task utility; no better achievable Pareto frontier | Completed-task proxy, abstain/false reject, decision/repair time, messages/bytes |
| RQ4 | How do failures, attack ratios, sensor uncertainty and fleet size affect the rule's behavior? | Effect is not robust on independently seeded settings or disappears in ablation / holdout | Sensitivity surfaces, confidence intervals, effect sizes, transparent negative results |

**Important RQ1 interpretation:** disagreement with the oracle's *allocation decision* is not by itself a physical hazard or collision. A separate feasibility oracle (battery, motor, task deadlines, simulated travel) is needed to label ground-truth-infeasible assignment. The simple Step 2 incident proves only an **assignment correctness/eligibility counterexample in a controlled simulation scene**, if tests pass.

## Actors, assets, capabilities and threat boundaries

| Actor | Can observe and change | Cannot be assumed to control |
|---|---|---|
| Honest registered drone | Truthful own health/position messages, network send frequency | Other identities, network scheduling |
| Faulty/compromised registered drone | Sign false **own** position/health with its legitimate registered key; omit position in a later heartbeat; report plausible drift | Uncompromised peer signing keys; trusted external independent witnesses by default |
| Network scheduler / simulator | Drop, reorder, delay, partition and retransmit valid messages within specified bounded scenario | Arbitrarily forge a valid signature from an honest registered node |
| Coordinator | Verify signed envelopes, maintain caches, use eligible reports, produce certified task-intent decisions | Access to ground truth or private adversarial state unless independently supplied as observable evidence |
| Evaluation oracle (offline only) | True position/health, task feasibility, attack labels, simulated mission truth | Direct input to the tested allocator or privileged data available only to proposed method |

### Observability and impossibility assumption

Without independent observation, trusted sensors, temporal motion bounds or cross-checkable constraints, a perfectly coherent but false signed report may be indistinguishable from a truthful report. The method must output **unknown / request evidence / abstain** when justified, not assert universal Byzantine detection. In multi-witness scenarios, predefine witness trust/independence and compromised fraction; quorum certificates alone do **not** imply sensing truth.

Step 2 baseline deliberately separates:
- **Benign omission/staleness**: old position cached, new legitimate health-only signed update;
- **Signed self-falsification**: registered member signs inflated health while offline evaluation truth is degraded;
- **Healthy control**: signed data matches offline truth.

These are **controlled examples**, not estimates of attack prevalence or detector accuracy.

## Observation and time model

A proposed decision receives an event series with independent fields:

- member ID, registered signer verification result, boot/session and packet sequence;
- health value, health observation/receive time, and reported sensor quality;
- position XYZ, position observation/receive time, and uncertainty bound;
- optional independent witnesses, their age, source provenance and bounded agreement;
- task generation time, target XYZ, deadline and resource/mission constraints;
- network packet loss, delay, retry, partitions and clock error assumptions.

There must be **two** clocks in study descriptions: the event/sensor observation time and coordinator receipt time. For malicious timestamps, receipt time alone does not prove freshness of the physical observation. Explicitly bound achievable clock drift. A health-only heartbeat must **not** silently mark an older position as newly observed.

**Proposed future action set (not implemented by Step 2):** `ACCEPT`, `REQUEST_FRESH_EVIDENCE`, `ABSTAIN`, `REASSIGN`. Every decision should record a structured reason and an optional uncertainty interval. Never equate successful signature validation with physical attestation.

## Primary experimental design (planned; no results yet)

### Experimental unit and sampling

- Paired, independently seeded **scenario episode**, not a Python test assertion, is the inferential unit. Within-episode task decisions are correlated; do not treat them as independent samples.
- Fleet sizes: 5, 10, 20, 50. Validate 4-member minimum in a separate small test; do not extrapolate a 4-member probe to N=50.
- Attack factors: stale position age bins (0, 1, 3, 5, 10, 20 s); signed health falsification magnitude; position jumps and consistent slow drift; malicious fraction up to declared f; optional selective omission; link loss (0, 0.05, 0.15, 0.30); delay distributions; partition episodes; benign sensor noise/control.
- Task factors: fixed request sets and independent dynamic arrivals, resource eligibility thresholds and deadlines. All algorithms receive the same generated environment, task constraints and authorized observation information.
- Run a small deterministic **pilot** first (e.g., 30 independent seeds per selected condition) to estimate variance and failure incidence. Freeze primary metric, meaningful effect size and power/precision-driven counts **before** full study; evaluate with a held-out seed list. The earlier 6-trial archive is *not* part of this new study's inferential sample.
- Do not seed tests from future observed outcomes or drop failed episodes; report all repetitions, timeouts and missing sensor observations.

### Baselines and fairness

1. Production **greedy health-weighted allocation**, using signed reported health and cached XYZ (status quo).
2. Greedy plus **independent age limit** for position and health, with identical abstention/retry costs recorded.
3. Greedy plus bounded **kinematic plausibility** and cross-field checks, explicitly marked non-attesting.
4. Same-feasibility constrained **Hungarian matching** as a centralized optimization reference, with no privileged ground truth during decision making.
5. Faithful **CBBA / distributed auction** (or reproducible published comparator), matched against the same information and message budgets.
6. The new consistency-evidence gate paired with the **same underlying optimizer(s)** as relevant baselines.
7. A reproducible 2026 stale-information/zero-trust method if licensing, code and consistent threat assumptions permit; document differences if it cannot be implemented faithfully.

Never give ground-truth truth labels or witnesses solely to the proposed method. If independent evidence is unavailable to a baseline by its definition, disclose this as an *information advantage*, report an equally informed control, and separate the gain from the rule's gain.

### Outcomes and measurement definitions

**Primary metric** (to finalize after pilot): *episode-level ground-truth-infeasible assignment incidence*, i.e. at least one accepted task assigned to a drone whose **offline true** state violates prespecified physical/resource eligibility. This must not be confused with assignments that are merely less distance-optimal. Lower is better.

**Safety/utility secondary metrics**: tasks accepted, tasks completed under a stated simulated dynamic model, false refusal (ground-truth-feasible task blocked), abstain rate, task utility/regret, rescheduling latency in simulated time and wall-time decision CPU, link messages/bytes, decision memory, task duplication, and state transition consistency.

Metrics must be computed on **all requested tasks**, not only successful assignments. Missed localizations / unavailable telemetry remain missing or unknown, never silently imputed as safe. Attack detection false-positive/false-negative claims are only meaningful under externally grounded truth labels.

### Analysis and study integrity

- Pre-specify paired differences and expected direction for each primary/secondary hypothesis. Report sample sizes, effect sizes and uncertainty intervals; use appropriate Bernoulli/Wilson intervals or episode-cluster bootstrap, not packet-as-independent pseudo-replication.
- If hypothesis testing is used, declare multiplicity correction (e.g., Holm) for a limited primary hypothesis family, with full raw p-values and estimates. No post-hoc cherry-picking.
- Include negative and boundary cases where zero independent witnesses makes attacks undetectable.
- Mandatory ablations: signed-only; position-age; plausible motion; independent evidence; full combined gate; optional recovery. Report overhead and miss/false-reject costs of each.
- Report paired comparisons at N=5/10/20/50, benign/no-attack controls, compromised f=0..floor((N-1)/3) where computationally feasible and independently held-out seeds.

## Execution/evidence rules and folder plan

- **Step 2 baseline probe:** `python consistency_gated_step2_probe.py --out experiment_outputs/consistency-gated-step2`. Uses registered legitimate signers, AES-GCM verified encrypted heartbeats, in-memory signed election dissemination, certified task allocation and the current greedy implementation; **no peer UDP runtime threads are started and no flight occurs**. Outputs JSON, SHA-256 and source metadata. Synthetic single-instance ground truth is provided **only to the offline counterfactual evaluator**.
- **Step 2 test:** `python -m pytest -q test_consistency_gated_step2.py`. Must show that the healthy control agrees with ground truth and two targeted failure examples *disagree*, or the Step 1 motivating theory is revised. A CI artifact is a reproduced code behavior, not a publication-scale effect estimate.
- **Steps 3–9:** new versioned `experiment_outputs/consistency-gated-v1/` per-condition JSON/CSV, event traces, methodological configs, source hash, independent seed manifest, baseline output and confidence intervals. Never overwrite archived `supplementary/uav-swarm-authority-v1.0.0/` or relabel it.
- Numerical claim manifests must identify the algorithm commit, experimental config, truth oracle, seed, software deps, host and simulations/hardware boundary.

## Stage gates

**Step 2 completion** requires: prospectively written protocol + clearly scoped threat model; testable hypotheses; planned fair controls, outcome/CI rules and stop conditions; the reproducible stale-position and signed-false-health examples with an honest control; cross-platform CI check and a downloadable generated artifact. It does **not** require the proposed algorithm to be implemented.

**Step 3 gate** requires first documenting that the existing coordinator can misassign under the scoped cases and that an unmodified age-only control is a meaningful competitor. Code the new method only after the evidence model and no-ground-truth-leak rule are frozen.

**Stop/revise:** if the signed-old-position incident cannot be reproduced on the real command_tasks() path, update the motivating claim. If age-only gating alone matches the proposed safety–availability frontier, there is no demonstrated new-method advantage; accept a negative study or change the contribution. If no independent evidence exists, refrain from promising detection of internally consistent false reports.

## Literature and paper separation

See Step 1 audit for 2026 AC-DMTA, ZT-GAT, related local-information/swarm trust works, CBBA and other overlap dangers. Original quorum-election and acoustic archive evidence belong to older related manuscripts; these Step 2 probes are **new, single-scene software diagnostic examples**, not independent publication-scale data or a new consensus/flight-safety result.
