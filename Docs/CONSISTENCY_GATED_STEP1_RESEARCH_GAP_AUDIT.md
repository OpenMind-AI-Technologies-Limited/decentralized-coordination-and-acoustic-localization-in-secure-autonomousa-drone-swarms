# Step 1 — Research Gap, Prior-Art and Novelty Audit

**Date:** 2026-11-15  
**Repository:** https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms  
**Audited main revision:** 698926f7cec7e61efeaaef94f32867dc891bb201  
**Candidate paper (working title):** *Consistency-Gated Task Allocation for Decentralized UAV Swarms Under Stale and Byzantine-Falsified Telemetry: A Reproducible Software Validation Study*  
**Audit status:** Step 1 evidence / bounded literature screening complete; originality **not established**; Step 2 research protocol and later experimental validation outstanding.

## Executive decision

**Conditional GO** for a distinctly scoped software/simulation study of *assignment decisions under authenticated-but-untrustworthy telemetry*. **NO-GO** for claiming novelty merely from timestamps, cryptographic signatures, a trust score, uncertainty envelopes, generic Byzantine detection, or a combination of existing task allocators. A defensible contribution will require a precise decision-level mechanism, demonstrated failure of existing baselines under matched adversaries, and measured advantages under fair comparisons. Null or negative findings must be retained.

The repository is an engineering starting point, not direct evidence that the proposed method works. No new scientific experiment or novel algorithm was created by this Step 1 audit.

## 1. Source-level observations and proposed gap IDs

| ID | Priority | Evidence in current code | Hypothesized failure / scientific question | Verification needed |
|---|---|---|---|---|
| G1 | P0 | swarm_mesh.py: signed heartbeat carries self-reported HealthReport; Docs/COORDINATION_RESEARCH_AUDIT.md states battery, motor and link health are not attested | A compromised, authorized signer can publish internally plausible but false health data; a valid signature proves origin, not physical truth | Validly signed falsified-health end-to-end scenarios with an independent simulator ground-truth oracle; quantify harm and unobservable attacks |
| G2 | P0 | swarm_mesh.py: MeshNode.positions stores XYZ without per-position age; receive() refreshes health upon every heartbeat, including those lacking position; mesh_simulation.py: command_tasks() filters recent health but reuses positions indexed by that health | A recent heartbeat can retain an older XYZ estimate and alter allocation | Write a focused regression demonstrating stale XYZ is eligible after fresh health-only heartbeat, then evaluate assignment counterfactual against true XYZ. Treat as **code-derived vulnerability hypothesis**, not an observed exploit |
| G3 | P0 | swarm_tasks.py: deterministic greedy distance-plus-health penalty; positions and health accepted as trusted inputs; no trust/uncertainty or independent-observation input | An attacker may influence winner/assignment with signed inconsistent telemetry | Joint consistency-evidence/uncertainty-gating proposal; test false acceptance vs unnecessary abstention |
| G4 | P1 | swarm_geometry_experiments.py: healthy/degraded static one-shot task scenes; no task lifecycle | Assignment after crashes, stale reports, and intermittent links not experimentally characterized | Event-driven tasks, cancellation, reassignment, state/version convergence and at-most-once acceptance tests |
| G5 | P1 | swarm_geometry_experiments.py compares health-aware greedy to fixed ID-order naive allocator | Existing comparator is weak and not representative of optimized/distributed task allocation | Matched constrained Hungarian, published CBBA or faithfully disclosed implementation, and a recent uncertainty-aware method when reproducible |
| G6 | P1 | swarm_network_experiments.py: fault injections target election; packet delivery is deterministic synthetic; acoustic and formation experiments are separate | No end-to-end allocation measurement of signed data falsification combined with delay, packet loss, or partitions | Coupled network + telemetry + allocation test harness with separate decision, safety, availability and communication metrics |
| G7 | P1 | current experiment summaries have six repeats per setting; intervals are descriptive | Precision and external validity insufficient for new attack-defense claims | Independently seeded trial plan with preregistered outcome definitions, paired baselines, sensitivity, multiplicity control, effect sizes and independent holdout seeds |

### Code-path reasoning for G2 (precisely bounded)

1. MeshNode.receive() accepts an authenticated heartbeat and records self-reported health with local receive time.
2. It only updates the positions dictionary if a position field exists; the dictionary stores coordinates without independent age metadata.
3. mesh_simulation.DroneMeshSimulation.command_tasks() filters health by the configured timeout, then takes any stored position for each freshly reporting member.
4. swarm_tasks.allocate_tasks() calculates distance using those positions. Hence, **if** a member's position persists across a later health-only heartbeat and the member remains eligible, a stale coordinate may influence task selection.
5. This is a static control-flow finding. Step 2/3 must reproduce a full decision error on actual execution and check whether other runtime constraints prevent or mitigate it. It is not proof of radio exploitation, physical collision, or arbitrary malicious control.

### Fundamental observability limitation

A correctly signed, temporally fresh and internally consistent false sensor report may be **indistinguishable** from an honest report if no independent measurements, trusted anchors or physically justified bounds are available. The method must support an explicit **insufficient evidence** state and must not claim universal Byzantine truth detection. Stronger correctness claims require explicit assumptions about independent observations and number/capability of compromised observers.

## 2. Actual archived evidence and provenance

Verified archive: supplementary/uav-swarm-authority-v1.0.0/. Manifest source revision: 78cce082c5acabe68ebc5f76a32872b210308af5; seed 2026; six repeats per setting; 378 trial rows across 63 experiment settings. The archive provides S1 trial JSON/CSV, S2 summaries, checksum manifest, traceability and supplementary figures.

| Family | Existing rows | Relevance to new study | Limitation |
|---|---:|---|---|
| Election | 192 | Authentication, quorum fault semantics, packet overhead | Does not test malicious task allocation telemetry; quorum-specific results already belong to previous manuscript |
| Formation | 96 | Scene generation and geometric checks | One-shot hypothetical waypoints, not flight trajectories |
| Allocation | 48 | Baseline behavior and CSV/JSON reporting | Only healthy/degraded self-reports and a naive ID-order comparator; **no malicious signed falsification or stale-XYZ experiment** |
| Beacon receiver | 24 | Possible future measurement model | Known synchronized reference beacons; no real sensor acquisition |
| Acoustic source | 18 | Not in primary task-allocation hypotheses | Synthetic signal source; not drone position truth |

Archive check: among six N=50 degraded allocation observations, baseline naive ID-order assignments used ineligible members 7.0 times per trial on average while the existing health-aware greedy algorithm assigned 0.0 ineligible members per trial. This does **not** establish Byzantine robustness: the degraded nodes reported their poor health honestly to the allocator.

**New-paper data rule:** preserve the original archive untouched and cite it as background/related prior experiments. Generate separately versioned, source-bound and checksum-verified **new** attack/defense observations. No old trial row may silently become a new algorithm-result observation.

## 3. Targeted prior-art check (screened 2026-11-15)

This is a **targeted, non-systematic** screening of high-relevance publications and research abstracts, not an exhaustive priority search. Read the full text, methods, appendices and accessible code before asserting novelty.

| Ref | Prior study and link | Already established / overlap danger | What must be genuinely different |
|---|---|---|---|
| L1 | Zhao et al., *Drones* (9 July 2026), AC-DMTA, DOI 10.3390/drones10070523 — https://doi.org/10.3390/drones10070523 | Assignment-consistency certificates, interval bids, timestamp/recency and uncertainty-aware communication under stale asymmetric information | Do **not** claim recency, interval bids or decision-consistency certification as novel. Evaluate separate signed-data integrity/evidence constraints and allocation-level failure under adversarial falsification |
| L2 | Sophia et al., *Discover Electronics* (1 Nov 2026), ZT-GAT, DOI 10.1007/s44291-026-00305-9 — https://doi.org/10.1007/s44291-026-00305-9 | Byzantine false-state data, replay, constrained communication, multi-signal zero-trust modeling | Do **not** claim general Byzantine state detection, trust scoring or crypto integration as novel; specify task-decision correctness and a light-footprint evidence model |
| L3 | Liu et al., *Reliability Engineering & System Safety* (2026), resilient UAV task allocation with local information, DOI 10.1016/j.ress.2026.112442 — https://doi.org/10.1016/j.ress.2026.112442 | Robust decentralized/local-information task allocation | Compare assignment resilience, not simply decentralization |
| L4 | Lal & Mishra, *Ad Hoc Networks* (2026), integrity-aware communication scheduling, DOI 10.1016/j.adhoc.2026.104449 — https://doi.org/10.1016/j.adhoc.2026.104449 | Spoofing can corrupt interpretation of freshness; integrity-aware network scheduling | Distinguish assignment-level action acceptance/rejection from communication-rate management |
| L5 | Choi, Brunet & How, *IEEE Transactions on Robotics* (2009), CBAA/CBBA, DOI 10.1109/TRO.2009.2022423 — https://doi.org/10.1109/TRO.2009.2022423 | Distributed auctions / CBBA are established task assignment methods | Implement a fair published CBBA comparator; do not rebrand ordinary auctions as novel |
| L6 | Francos et al., *Trust-Aware Sequential Decision Making and Rollout Planning for Resilient Multi-Robot Systems* (2026 preprint, publication status to verify) — https://arxiv.org/abs/2608.25690 | Compromised localization reports, monitor-aware adversary and trust-aware online assignment/replanning | This is a **major novelty threat**; establish meaningful differences via assumptions, algorithms, results and verifiable code |
| L7 | IEEE TCE (2026), Byzantine-resilient FL with trust-aware task scheduling, DOI 10.1109/TCE.2026.3670496 — https://doi.org/10.1109/TCE.2026.3670496 | Trust-aware scheduling in Byzantine UAV systems exists | Differentiate mission-task correctness and independent telemetry evidence from FL training-task scheduling |

**Search gap / honest status:** no exhaustive Scopus/IEEE Xplore/Crossref snowballing, duplicate search or full systematic-review screening was executed. Absence of an exact-title match must never be interpreted as proof of global novelty. Recheck relevant new papers before manuscript submission.

## 4. Relationship to existing manuscripts

- Existing supplementary archive explicitly labels the manuscript *Quorum-Gated Authority and Safety–Availability Trade-offs in Decentralized UAV Swarms under Communication Faults*. Its main purpose is certified leader authority, fault handling, safety–availability and existing 378 synthetic outcomes.
- The repository's research_paper.md, *Reproducible Software Validation of Authenticated UAV Swarm Coordination under Network Faults with Synthetic Acoustic Localization*, is a separate journal-neutral document containing overlapping source/evidence. It is not the latest journal submission PDF.
- The related Scientific Reports work *Cyber-Resilience and Trust-Aware Command Authorization for Autonomous UAV Swarms in GPS-Denied Environments* is another potential overlap, especially in authentication and command authorization. Its publication/submission status was **not checked during this audit**.
- Related conference acoustic work DOI 10.58168/MIST2026_1425-1432 is outside this candidate's main task-allocation scope but requires disclosure if material reused.

**Boundary:** shared architecture, generic methods and baseline comparisons can be disclosed and cited; **do not** resubmit the 378 records or quorum-election claims as a new paper's original experimental contribution. The proposed paper should own a new attack model, task-decision acceptance mechanism, actual new experiments and separate versioned artifacts. Disclose related works to editors and confirm submission restrictions.

## 5. Research claim that may be worth testing (not yet proven)

**Working scientific question:** When a legitimate authenticated member supplies stale or strategically falsified position/health reports, can *separately time-bounded, evidence-supported eligibility and assignment-decision checks* reduce objectively unsafe/infeasible assignments while preserving measurable task availability under lossy communications?

Candidate conceptual elements for Step 2 (not implemented in Step 1):

- Bind health and position age to each observation, not simply the latest heartbeat or signature.
- Define an independently evidenced observation model and its observability assumptions; record unknown/unverifiable, rather than relabeling as safe.
- Use auditable accept / request-fresh-evidence / abstain / reassign decisions against task-level feasibility and bounded uncertainty.
- Isolate the decision gate from the optimizer so it can be paired fairly with multiple allocation algorithms.
- Model attacker control precisely: registered member with own signing key and ability to misreport own health/position; not arbitrary key compromise or omnipotent ground-truth manipulation.

**Negative result test:** if freshness gating or straightforward plausible-state checks already achieve the same safety–availability/cost frontier, the claimed new method has no demonstrated value and must be revised or the paper repositioned. Likewise, indistinguishable forged signals without independent checks cannot support a guaranteed defense.

## 6. Evidence required for a defensible new manuscript

All results below are **not yet collected**.

1. **Exploit/behavior reproduction:** frozen current implementation; validly signed health-only refresh with stale XYZ; true-position vs reported-position counterfactual; record assigned winners, decisions and timestamps. Distinguish reachability in real message path from unit-level construction.
2. **Threat model:** benign sensor drift and latency; malicious self-signed health inflation, position displacement, consistent slow-drift, selective omission, replay of valid signed data, mixed network loss; explicit compromised fraction and independent evidence availability.
3. **Fair comparators:** original greedy, same-feasibility constrained Hungarian (centralized oracle ceiling with limitations noted), decentralized CBBA / auction, simple age-limit filter, independent-observation sanity filter, and a reproducible recent method if accessible. Same task set, capabilities, message budget and offered observation information per paired condition.
4. **Metrics:** independently defined ground-truth infeasible/unsafe assignment rate, tasks completed (simulation abstraction explicitly defined), false rejection, abstention rate, mission utility, assignment/regret, reallocation delay, bytes/messages, decision CPU time and memory, availability under partition. Never treat proposed waypoint separation as measured flight collision.
5. **Sampling:** pilot variance assessment followed by preregistered sample counts and independent held-out random seeds, paired comparisons, uncertainty intervals, effect sizes, multiple-comparison handling, and stratification by N=5/10/20/50, compromised nodes, age, noise, loss and link/partition schedule.
6. **Ablations:** signature-only, age-only, cross-field constraint-only, external evidence-only, full gate; identify false-safe and false-reject incidents with raw traces.
7. **Independent verification:** new data/code SHA-256 checksums, run/source manifest, raw CSV/JSON + per-instance ground truth, exact configurations, reproducible charts and numeric claims, test results on supported CI; clearly separate simulation from physical drones.
8. **Adversarial independent review:** assess strongest existing related algorithms, threat-model impossibilities and potential leakage of ground truth to only one method.

## 7. Risk register and stop / revise conditions

| Risk | Severity | Mitigation / decision gate |
|---|---|---|
| AC-DMTA already addresses assignment-relevant stale decisions | High | No novelty credit for timestamps/certificates; isolate malicious authenticated falsification and independent evidence; full-paper similarity review |
| Trust-aware routing/task planning under spoofing already exists | High | Compare against Francos et al. and alternatives; differentiate assumptions and outcomes empirically |
| Cannot identify coherent forged telemetry with no trusted independent source | Critical | State observability assumptions and abstention behavior; do not claim sound detection when physically unobservable |
| Current task allocation executes under single certified leader rather than fully leaderless consensus | High | Describe as decentralized authenticated swarm with certified coordinator; do not claim leaderless task allocation |
| Adversary and method each given unequal data or ground truth | High | Shared observation model, offline ground-truth evaluator only, blinded evaluation seeds |
| Insufficient repeats or single simple ID-order baseline | High | Pilot power/precision and multiple scientifically credible baselines |
| Prior manuscript overlap / double publication | High | Separate results and disclosure; independent manuscript content audit |
| Mislabelled simulation as deployed UAV evidence | Critical | Scope explicitly software-only; no hardware/radio/flight claims |

## Step 1 exit criteria / findings

- [x] Reviewed main code path for signed self-reported health, stored position, task-command selection and greedy assignment.
- [x] Classified and counted 378 archived records (192 election, 96 formation, 48 allocation, 24 beacon, 18 acoustic).
- [x] Verified 6 existing N=50 degraded allocation rows show 7.0 mean ineligible naive vs 0.0 health-greedy assignments.
- [x] Identified that no new-paper stale/falsified allocation trials exist in those archive scenario labels.
- [x] Screened seven relevant prior-art entries with original URLs and explicit overlap hazards.
- [x] Defined paper boundary, evidence needs and high-severity novelty/observability risks.
- [ ] The G2 actual end-to-end stale-position assignment error is **not yet reproduced**: Step 2/3 target.
- [ ] Full-text systematic novelty/benchmark review and author/portal overlap verification: mandatory later before submission.
- [ ] New method and new experimental dataset: Steps 2–9, **not Step 1 deliverables**.

**Step 1 outcome:** documentation and static gap audit complete, **conditional GO to design a falsifiable Step 2 protocol**, not approval to claim a novel, superior or publication-ready algorithm.

## Next action: Step 2

Write separate preregistered research questions, hypotheses, actor/sensor trust boundary, feasibility oracle, task lifecycle, synchronized competing information views, attack generator, fairness protocol, pilot replication policy and stage-gate acceptance tests **before** implementing the proposed algorithm. Capture the G2 end-to-end baseline first to prove that the motivating failure actually occurs.
