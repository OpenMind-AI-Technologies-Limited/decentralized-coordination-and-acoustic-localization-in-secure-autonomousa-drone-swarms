# When Signed Witnesses Disagree: Safety–Availability Limits of Consistency-Gated Task Allocation in Simulated UAV Swarms

**Manuscript status:** Full **working draft** for scientific/editorial review, not approved for journal submission.  
**Article type proposed:** Reproducible software-validation study with negative and boundary-condition results; suitability for a specific journal has **not** been established.  
**Version:** Step 10, 16 November 2026.  
**Author (provisional):** Md Shahanur Islam Shagor. **Affiliation and ORCID: confirm from the author and submission account before publication.**  
**Correspondence, funding, conflicts, ethics, author contributions, and any coauthor approvals:** see the unresolved statements in Section 10 and the submission-readiness register. No institutional or grant authorization is assumed.

## Abstract

**Background:** Authenticated reports in decentralized unmanned aerial vehicle (UAV) coordination establish who issued a claim but do not demonstrate that a reported position or resource state is true. When task assignment relies on independently signed peer observations, disagreement creates a safety–availability decision: conservative rejection may exclude capable vehicles, whereas robust aggregation may accept coordinated misinformation. **Methods:** We evaluated six task-allocation policies through an open-source, fixed-roster software simulator that exercises signed and encrypted coordination messages, certified leader election, randomized reports, and idealized signed peer-witness claims. Four fleet sizes (5, 10, 20, and 50 nodes) and nine controlled benign/adversarial scenarios were studied. A separate internally prespecified heldout set comprised 720 seeded simulator episodes after 288 development episodes. All six policies used the same underlying greedy assignment optimizer and shared per-episode available inputs. The primary diagnostic was whether any selected node violated an *offline ground-truth resource-eligibility threshold*; mean requested-task coverage measured availability. **Results:** Across the balanced heldout scenarios, authenticated-report greedy assignment had 63/720 episodes containing at least one resource-ineligible assignee, and age-only filtering had 59/720. A conservative signed-witness veto had 0/720, compared with 30/720 for a three-witness coordinate-wise median with motion filtering. Mean task coverage was 83.24% and 83.48%, respectively. The median reduced rejection induced by one malicious witness but accepted resource-ineligible assignments under two-witness collusion; motion filtering detected deliberately implausible reported position jumps without establishing sensor truth. **Conclusions:** The evaluated policies reveal a measurable conditional safety–availability trade-off, not a universally superior new allocation algorithm. These outcomes concern **synthetic resource-feasibility decisions** and cannot establish real UAV flight safety, fault-free cryptographic consensus, or field performance.

**Keywords:** UAV swarm; multi-robot task allocation; signed telemetry; malicious witness; Byzantine threat model; stale observations; quorum certificate; safety–availability trade-off; reproducible simulation; negative results.

## 1. Introduction

The multi-robot task-allocation (MRTA) problem requires selecting agents for tasks while respecting assignment, capability, and information constraints. Standard MRTA taxonomies distinguish the allocation problem's structure from its solution methods [1]. Distributed auction-based methods, including the consensus-based auction algorithm (CBAA) and consensus-based bundle algorithm (CBBA), address coordination and conflicts under stated communication assumptions [2]. Their published convergence and performance results must not be transferred to a different implementation merely because it uses similar assignment terminology.

A separate difficulty is the **credibility of the state used for allocation**. A participant can sign a battery, motor-health, radio-quality, or XYZ-position report that is malformed, old, inaccurate, or intentionally false. Authentication alone cannot transform a sender's claim into a verified measurement. A coordinator may therefore need to distinguish *accept*, *reject*, and *request more evidence* before allocating tasks. An aggressive veto can prevent hazardous allocations but also suppress service when one signed witness lies. Median-based aggregation offers robustness to an isolated outlier only when sufficiently many independent honest witnesses are available; it becomes vulnerable when the assumed honest majority is violated.

Related studies already address decentralized auctions [2], communication-constrained allocation [3], and decision-relevant stale-information consistency [4]. In particular, the 2026 assignment-consistent dynamic multi-UAV allocation (AC-DMTA) study uses uncertainty-based winner/bundle stability certificates and event-driven communication [4]. That work is distinct from the present static greedy eligibility-gating comparison and must be recognized when describing the prior state of the art. A 2026 resilient-local-information allocation paper also studies disturbance-resilient UAV task allocation [5]. Our present work **does not claim to be the first consistency-aware UAV allocator** or to replace these systems.

Instead, we ask a narrower empirical question: **What failure and abstention behavior occurs when a static task allocator conditions node eligibility on authenticated self reports and different policies for resolving signed witness disagreement?** The objective is to make both harmful acceptance and avoidable refusal visible. This is a study of *the measured software decision model*, not a new Byzantine agreement protocol, formal fault-tolerance proof, full CBBA implementation, or airborne robot trial.

The paper provides (i) a reproducible and bounded signed-receiver simulation framework, (ii) an equal-*available*-input paired evaluation of simple freshness, kinematic, veto, and median policies, (iii) positive and negative adversarial counterexamples with explicit signer-specific fault assumptions, and (iv) a source-derived integrity audit that distinguishes episode-level observations from correlated policy rows. The primary contribution is **transparent comparative evidence and limits**, not the invention of the median or speed plausibility check.

## 2. Prior work and positioning

**Distributed allocation and communication.** Gerkey and Matarić's MRTA framework establishes task/robot allocation taxonomies [1]. Choi, Brunet and How distinguish CBAA from the more general CBBA and analyze conflict-free convergence under particular assumptions [2]. Raja, Habibi and How's communication-aware CBBA addresses bandwidth and collisions using a learned communication policy [3]. Our implementation's unchanged greedy allocator and optional additive auction diagnostics are **not** full decentralized CBBA with asynchronous bid, bundle, and path consensus; no published CBBA superiority claim follows from our results.

**Staleness, dynamic consistency and local resilience.** Zhao *et al.* (2026) study decision-triggered updates, interval bids, and winner/bundle certificates under stale and asymmetric records [4]. Liu *et al.* (2026) also examine a locally informed resilient UAV swarm allocator [5]. Those studies target allocation/communication design questions broader than the present static resource-gating decision. The use of an age check or position-consistency certificate is accordingly **not presented as inherently novel** here.

**Authenticated claims and adversarial information.** The Byzantine Generals Problem formalizes limits of agreement with malfunctioning or malicious parties [6]. The general quorum threshold used by a particular authenticated coordinator is not equivalent to truthfulness of arbitrary health sensors or to an independently proven replicated-state protocol. In this paper, digital signatures provide provenance of **statements**; the veracity of a statement depends on a separate and explicitly simulated sensing model. A median of three health claims tolerates at most one arbitrary witness **if the other two observations are independent and sufficiently accurate**. It is not a substitute for trustworthy measurement.

### 2.1 Research questions

- **RQ1:** For identical simulated signed inputs, how do the considered policies change the incidence of resource-ineligible task assignments and the fraction of requested tasks allocated?
- **RQ2:** Can a three-witness median reduce an isolated malicious witness's false veto, and how does it behave against two colluding witnesses?
- **RQ3:** What additional decisions are rejected by a bounded-motion consistency check under deliberately implausible position updates, compared with source-age filtering alone?
- **RQ4:** Does an unavailable fresh coordinator quorum cause all policies to abstain, and what availability loss follows in the tested partition stress?
- **RQ5:** Can raw episode and method records be independently audited for ground-truth eligibility, pairing, statistical summaries, and file integrity without treating the same episode's policies as independent trials?

These questions ask for **software evidence**, not unconditional guarantees under arbitrary adversarial schedules.

## 3. System and threat model

### 3.1 Experimental boundary and authenticated receiver

The reference repository implements a statically registered set of UAV-like peer identities using Ed25519 source signatures, AES-GCM protected message envelopes, source-session/sequence checks, and a quorum-certified leader mechanism (`swarm_mesh.py`). The experiments invoke the actual receiver validation and signed vote paths in an in-memory, manually clocked network; positions, resource states, witness sensors, and link losses are synthetic. There is no measured physical UAV, autopilot, GNSS-denied navigation sensor, or RF packet experiment.

For fleet size `N`, the model reports a *configured* fleet budget `f = floor((N−1)/3)` and the signature count needed for its quorum certificate. These values must not be interpreted as a proof of globally consistent Byzantine state-machine replication. A separate **witness-specific assumption**, `f_w ≤ 1` among three health witnesses, is needed for the median's elementary one-outlier robustness argument; the two assumptions must not be conflated.

Tasks are candidate XYZ positions within a synthetic workspace. A single allocation episode uses a fixed task set and one task per selected node. The optimizer minimizes a deterministic travel-distance-plus-reported-health score among eligible members; no flight trajectory, physical execution, energy consumption, temporal job completion or collision is measured.

### 3.2 Input and decision model

The coordinator receives each member's signed self-reported battery percentage `b_i`, motor health `m_i`, link quality `l_i`, and XYZ position `p_i`. It tracks separately the **coordinator receipt age of health and position**, avoiding the mistake of treating a freshly received health-only heartbeat as a fresh pose sample. Previous signed position snapshots can be compared with a maximum-speed bound. Separately enrolled reporters sign simulated peer observations of a subject's resource state. The witness simulator generates claims from an offline truth oracle with noise and injected adversarial alterations; **that truth is not passed to the allocation policy**.

The base resource threshold predicate for offline evaluation is

```text
true_eligible(i) :=
    battery_true(i) >= 30
    AND motor_health_true(i) >= 75
    AND link_quality_true(i) >= 40
```

This predicate defines a *resource-ineligible assignment* but does not establish that any actual drone would crash or collide. Decisions can be `ACCEPT`, `REJECT`, or `REQUEST_FRESH_EVIDENCE`. When no fresh quorum-certified coordinator is available, the simulator's policies all abstain from allocation.

### 3.3 Compared decision policies

All six policies use the same greedy optimizer, task requests, enrolled roster, available signed self reports, and available witness claims **within a paired episode**, with differing deliberate use of information.

| Policy ID | Eligibility logic |
|---|---|
| `greedy_signed` | Greedy on the authenticated self-report snapshot, subject to fresh coordinator quorum |
| `age_only` | Health and position receipt-age limits, no witness or motion evidence |
| `motion_age` | Age checks plus bounded previous-to-current signed XYZ displacement |
| `veto_3` | Age checks plus conservative rejection if **any** of three individually valid signed witnesses conflicts with the self-report |
| `median_3_age` | Age checks plus three-unique-witness coordinate-wise health median and self–median tolerance |
| `median_3_motion` | Three-unique-witness health median, age checks, and bounded position-motion check |

The median policies require **three valid distinct witness claim sources** for each considered subject. For each of `b,m,l`, a coordinate-wise median is computed; a deviation exceeding **8 percentage points** in any health dimension rejects the source report. An insufficient verified witness set produces a request for evidence rather than an implicit acceptance. The motion policy uses a **25 m/s** bound with a small slack and the reported time separation. Invalid signatures, mismatched epochs, duplicate reporter IDs, and stale claims do not increase the counted witness set.

The median is a conventional robust statistic. For three scalar observations `x1, x2, x3`, one arbitrary outlier does not arbitrarily displace `median(x1,x2,x3)` when the other two are bounded near truth. If two adversarial witnesses submit mutually corroborating false values, the median can follow their fabricated majority. These are input-model properties, not formal UAV safety guarantees.

### 3.4 Attack and availability conditions

The study includes nine predefined conditions: `benign`, `benign_noise`, `signed_false_health`, `signed_false_position`, `malicious_witness`, `colluding_witness`, `motion_jump`, `quorum_partition`, and `mixed_loss`. The conditions are deliberately balanced in sampling, **not estimated in proportion to their real occurrence**.

The isolated malicious-witness condition contains one signed health witness falsely contradicting a resource-capable subject. In the collusion condition, one subject falsifies self-reported health and two signed peer witnesses corroborate it. For `N=5`, three compromised signers exceed the configured overall fleet `f=1`, but the *witness-specific* median limit `f_w=1` is violated in every such two-peer-colluder case regardless of fleet size. `motion_jump` introduces a deliberately impossible signed displacement; `signed_false_position` also includes spoofing that remains plausible under the studied bound. `quorum_partition` removes post-bootstrap coordinator telemetry beyond a virtual heartbeat timeout. This is not a physically faithful distributed network partition.

## 4. Experimental design and reproducibility

### 4.1 Prospective internal development and heldout samples

The Step 8 design was committed to `Docs/CONSISTENCY_GATED_STEP8_FROZEN_PROTOCOL.md` **before** its results were generated. It is *internally frozen*, not externally registered. Fleet sizes were `N∈{5,10,20,50}`. Nine scenario labels were crossed with each fleet size. Eight seeded episodes per size/scenario were assigned to development (`root=82026`), generating **288** episodes; a different SHA-256-derived root (`root=82027`) generated **20** additional episodes per size/scenario, for **720 heldout episodes**. Source random seeds are derived from the tuple `(root, fleet size, scenario, trial)` and audited for uniqueness across sets.

Each episode randomly samples fleet geometry, task positions and counts, resource truth, observation noise, witness reporters and losses. The realized 720 heldout episodes form 4,320 **correlated policy records**; the latter number is not the number of independent experiments. All six policies are evaluated on the same realized episode. The earlier Step 7 exploratory pilot (960 different episodes and six different policy definitions) is **not pooled** into Step 8 heldout estimates. The inherited Step 1–6 diagnostics are also excluded.

### 4.2 Primary and secondary measurements

The primary **resource eligibility diagnostic** is a binary episode indicator `H_e(k)`: at least one task assigned by policy `k` to an agent that fails any *offline true* resource threshold. This includes a policy that assigns no tasks, for which the observed `H_e(k)=0`; therefore it **cannot be interpreted without coverage**. The primary availability diagnostic is `C_e(k)=assigned_tasks/requested_tasks` over *all* requested tasks, including those declined for lack of quorum or witnesses.

Secondary outcomes include offline true-space Euclidean assignment distance, number of rejected resource-capable members (a diagnostic **not a universal false-positive rate**), source/witness receipt counts, task owner differences, and stratum-level summaries. A motion-inconsistent source may be resource-capable yet deserve rejection, so it would be incorrect to label all such rejections as policy errors. False positions may change winners without failing the resource eligibility threshold. The primary safety word is therefore always qualified as **resource-ineligible assignment**, not physical safety or collision avoidance.

### 4.3 Analysis plan

For each policy, report `sum(H_e(k))/720` and mean `C_e(k)`. The source archive also contains descriptive summaries within each size/scenario stratum (20 episodes per stratum) and paired mean policy differences. The reported **95% percentile bootstrap intervals** use 500 episode-level resamples. Pooled post-hoc intervals are exploratory, use the independently seeded *episode* as the resampling unit, and are not corrected for multiple tests or externally validated. A `0/720` observed count is not proof of zero true probability even within the simulation, let alone for deployment.

### 4.4 Integrity and reproducibility boundary

The study saves `episodes.json`, `paired_policies.json`, `stratum_summaries.json`, `paired_metrics.csv`, and their SHA-256 manifest separately for development and heldout samples. `research_step9_evidence_audit.py` independently verifies per-episode seed derivation, source provenance, scenario/trial completeness, pairing uniqueness, CSV/JSON agreement, resource-ineligible labels from offline true health, Euclidean distance from stored truth/assignments, summary statistics, and archived bootstrap intervals. Altered statistics with recomputed file hashes are rejected by the auditor's integrity regression tests.

**Important remaining limit:** the saved episode records do **not** contain the full signed witness envelopes, encrypted messages, or signed quorum vote envelopes. Therefore archived statistical outputs can be independently checked, but **all original cryptographic events cannot be replayed solely from the saved archive**. Reproducing the software simulator from the pinned revision tests the message verification code afresh; that is a different guarantee from byte-for-byte envelope replay.

The original Step 8 results were generated on GitHub Actions from source revision `7ada98ec78c966efc78c2a446ddfb0eb67d7c8cf`; Step 9's independent audit and final CI at `311f1f72e38cb8d1d2fa8e6a04217212c3e6b4f8` verify the preserved design and results. Exact artifact links and file hashes are listed in the accompanying evidence index. Prior software tests passing do not validate correctness of unmodeled physical claims.

## 5. Heldout results

### 5.1 Primary resource-eligibility and allocation coverage

**Table 1.** Balanced synthetic heldout episodes with ≥1 offline true resource-ineligible assignee and mean fraction of requested tasks allocated. Every policy denominator is **720 source episodes**.

| Policy | Episodes with resource-ineligible assignment | Mean task coverage |
|---|---:|---:|
| Authenticated-report Greedy (`greedy_signed`) | 63/720 | 88.89% |
| Age-only filter (`age_only`) | 59/720 | 88.25% |
| Age + motion (`motion_age`) | 59/720 | 88.16% |
| Conservative signed-witness veto (`veto_3`) | **0/720** | **83.24%** |
| Health-median only (`median_3_age`) | 30/720 | 83.67% |
| Health-median + motion (`median_3_motion`) | **30/720** | **83.48%** |

A median-with-motion strategy saw 30 more episodes with resource-ineligible assignment than the equally witness-informed conservative veto in the sampled mixture, while mean task coverage was 0.24 percentage points higher. Consequently, **the median did not dominate the conservative veto on the two reported outcomes**. Comparing the median with age-only additionally changes the use of peer information; differences cannot be attributed solely to a new allocation optimization algorithm.

### 5.2 Witness disagreement versus colluding corroboration

**Table 2.** Heldout condition-specific veto/median behavior. Each condition contains **80 episodes** from four fleet sizes and 20 trials per size.

| Condition | Veto: ineligible-assignment episodes | Median + motion: ineligible-assignment episodes | Veto coverage | Median + motion coverage |
|---|---:|---:|---:|---:|
| Benign | 0/80 | 0/80 | 99.0% | 99.0% |
| Signed false health | 0/80 | 0/80 | 95.3% | 95.3% |
| Single malicious witness | 0/80 | 0/80 | 94.5% | 96.4% |
| Two colluding witnesses | 0/80 | **30/80** | 96.9% | 98.8% |
| Benign measurement noise | 0/80 | 0/80 | 97.9% | 97.9% |
| Deliberate impossible motion jump | 0/80 | 0/80 | 98.9% | 97.2% |
| Mixed packet loss | 0/80 | 0/80 | 68.5% | 68.5% |
| Loss of fresh coordinator quorum | 0/80 | 0/80 | **0.0%** | **0.0%** |
| Plausible signed false position | 0/80 | 0/80 | 98.3% | 98.3% |

The median allowed assignment when one signed witness falsely contradicted a healthy subject, improving mean coverage from 94.5% to 96.4% under that isolated malicious-witness condition. In the collusion condition, two malicious reporters could instead support the compromised subject's false resource report, with 30/80 median episodes recording at least one resource-ineligible assignment while the conservative veto recorded none. The higher median coverage in that scenario **includes risky assignments by the measured metric**, so more assignments cannot be interpreted automatically as better safety or mission success.

Under benign noise, the original veto rejected an average of 0.787 resource-eligible members per episode and median with motion 0.350, without a material coverage change in the reported condition. Those counts are **not a global false-positive rate**: eligibility of a resource-capable source does not imply its position report is truthful. In the deliberate jump condition, the age-only policy assigned the spoofed target in 69/80 runs and the motion-bounded variant in 0/80, a deliberately constructed software counterexample rather than a real pose-attack detection rate.

### 5.3 Paired exploratory differences

**Table 3.** Median + motion minus comparator, on 720 paired episode units; percentage-point effects with exploratory **95% percentile bootstrap** intervals (500 resamples). These are **post-hoc descriptive** intervals, not a multiplicity-corrected confirmatory test.

| Comparator | Resource-ineligible-episode risk difference | Task coverage difference |
|---|---:|---:|
| Conservative witness veto | **+4.17 pp** (95% interval +2.78 to +5.69 pp) | **+0.24 pp** (−0.04 to +0.53 pp) |
| Age-only | **−4.03 pp** (−5.69 to −2.50 pp) | **−4.77 pp** (−5.93 to −3.71 pp) |
| Median without motion | **0.00 pp** (0.00 to 0.00 pp) | **−0.18 pp** (−0.33 to −0.05 pp) |

The median+motion safety count did not improve over median without motion on the **resource-eligibility** endpoint. Position spoofing can still change task winners or travel distance without making a resource value ineligible; research using a single resource endpoint cannot establish the utility of position protection comprehensively. A resource-feasibility trade-off must be reported jointly with task coverage and the attacker model.

### 5.4 Quorum refusal and availability

The `quorum_partition` condition advances the synthetic clock after withholding post-bootstrap coordinator reports; without a fresh quorum, all policies abstain. The observed **0% task coverage** in that controlled condition is a fail-closed *coordinator decision*, not a proof of eventual consensus or resilience to physical network partitions. The 3-of-3 witness requirement also sharply reduces availability under mixed loss: the conservative veto and median+motion both had 68.5% coverage, compared with approximately 95.8% for the age-only condition reported in the source study. Per-scenario loss is simulated and cannot be reported as measured RF reliability.

## 6. Discussion

### 6.1 A conditional rather than monotonic safety–availability frontier

The results challenge a simplistic claim that robustness to one malicious witness also implies better protection against colluding witnesses. The conservative veto rejects after any qualified contradiction. It is more restrictive and can sacrifice benign service, but in this sampled collusion family it also avoided the resource-ineligible assignments observed under median aggregation. The median replaces a unilateral rejection rule with an honest-majority rule. That helps where two independent honest claims bound a single liar, yet fails when a dishonest majority controls the three claims. The observed shift is **not a dominance result**.

These are also not direct estimates of a real fleet-wide Pareto frontier: the sample balances designed attack conditions, uses idealized independent synthetic witnesses and omits real tasks' execution state, deadline, trajectory and correlation. A deployment recommendation would require distribution-appropriate testing, nonidentical sensor errors, communication cost and context-specific safety/availability weighting.

### 6.2 Authentication, quorum and witness-specific trust are distinct

Ed25519 authentication binds a claim to a registered identity; it does not establish accuracy of the battery reading, freshness of sensor capture, or noncollusion of other identities. A signed quorum for leader authority also does not provide an attested consensus on task-lease state. The `f=floor((N−1)/3)` overall quorum bookkeeping is **not transferable** to `f_w=1` robustness of a particular witness triple. When two signatures support a lie, a naive median follows their majority even if the overall fleet has more honest members. The experiment therefore exposes a separation between **authenticated provenance** and **verified situational awareness**.

### 6.3 Interpretation of negative results and earlier studies

The separate Step 7 pilot found that a previous full opportunistic rule selected **the same assignments as the simpler witness-plus-age control** in its 960 controlled episodes; a purpose-built motion attack was needed in Step 8 to produce a distinct motion-ablation effect. The Step 7 pilot is hypothesis-generating and uses a different comparison matrix; its observations are not combined into Step 8 point estimates.

The current evidence therefore supports a publication narrative about **boundary conditions and failures**, not superior new Byzantine-robust task allocation. Both 3-of-3 median aggregation and conservative per-witness rejection are simple known policies. It would be misleading to claim a new cryptographic primitive, novel consensus theorem, or improved full-CBBA allocator based on these experiments.

### 6.4 Practical engineering implications

For software experimentation, these results motivate keeping health age and position age separate, refusing allocation when the coordinator lacks a fresh quorum, preserving requests for further witness evidence instead of silently accepting old reports, and testing both isolated malicious observers and colluding-majority counterexamples. These are **engineering test priorities**, not certified aircraft guidance. In a real system, the trustworthiness of source sensor capture, recipient-side lease enforcement, durable shared task state, and independent position constraints would be decisive and remain outside the measured scope.

## 7. Limitations and threats to validity

**Construct validity:** The primary `H_e` measures resource-ineligible assignees, **not** physical collision, energy loss, task completion, flight safety, detection of plausible forged positions, or trustworthy sensor provenance. The diagnostic `false_rejected_healthy_members` cannot be called a universal false-positive rate since a member may be resource-eligible but motion-inconsistent.

**Internal validity:** Cryptography verifies signing keys and receiver logic in a controlled simulator. Signed witness observations are generated using idealized access to a synthetic truth model and can have correlated or malicious error only in predefined ways. Hidden modes, arbitrary packet schedules, malicious sensor capture timestamps and real signed-envelope replay from archived outputs are missing.

**Statistical validity:** Heldout seeds were frozen internally and are distinct from the development and Step 7 samples. The 720 episodes represent a fixed scenario-balanced simulation distribution; the 4,320 policy results are *paired*, not independent experimental replicates. The analysis is primarily descriptive; bootstrap intervals are exploratory, without external preregistration, confirmatory multiplicity adjustment or power justification. Comparisons across methods with different witness use should not be described as same-observability algorithmic superiority.

**External validity:** There are no radio measurements, flight trajectories, hardware safety tests, sensor independence measurements, real obstacle geometry, time-critical tasks, mission utility, or field network latency. The negative collusion and benign-noise observations demonstrate **counterexamples in this declared model**, not empirical operational failure rates.

**Implementation scope:** Full published CBBA, path-dependent bundle consensus, state-machine-replicated task leases, sender-proof of physical stopping, and exactly-once task execution remain unvalidated. The repository's separate Step 6 signed STOPPED receipt is an authenticated *claim* and not an independently attested actuator state.

**Related-work and originality scope:** Other manuscripts derived from the same swarm coordination code have been prepared. A final submission requires an explicit text/evidence overlap check and full editor disclosure of related submissions/publications. An evidence-aligned negative-results framing does not automatically establish editorial novelty or venue acceptance.

## 8. Conclusion

In paired software-only task-allocation experiments with signed but potentially false peer testimony, the choice of consistency-gating policy changed both the fraction of tasks allocated and the incidence of assignments to resource-ineligible nodes. A three-witness median reduced denial caused by a lone malicious witness under an honest-majority observation assumption, but colluding reporters could defeat that aggregation and produce harmful resource assignments that a more conservative single-conflict veto avoided in the tested scenario mixture. The resource threshold measure did not capture all failures caused by forged positions. The results establish conditional **decision-model limitations and trade-offs**, not a generally new or universally safer UAV allocator. Reproducible source code, independent evidence audits, and documented negative cases can support subsequent validation under more realistic sensing, mission dynamics and threat distributions.

## 9. Reproducibility and data/code availability

**Public code repository:** [Decentralized Coordination and Acoustic Localization in Secure Autonomous Drone Swarms](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms).

**Experiment pipeline:** `swarm_independent_pilot.py` (exploratory Step 7), `swarm_robust_witness_gate.py`, `swarm_robust_holdout.py` (Step 8), `research_step9_evidence_audit.py` (independent audit). The frozen Step 8 design and observed findings are separately documented in `Docs/CONSISTENCY_GATED_STEP8_FROZEN_PROTOCOL.md` and `Docs/CONSISTENCY_GATED_STEP8_HELDOUT_FINDINGS.md`. The manuscript's data sources and SHA-256 hashes are indexed in `Docs/CONSISTENCY_GATED_STEP10_EVIDENCE_INDEX.md`.

**Saved raw Step 8 experiments:** [GitHub Actions evidence artifact from the measured run](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43766097557/artifacts/14181798087) (may expire under GitHub's artifact retention policy). **Independent Step 9 audit:** [verified main CI and audit](https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43769505624). A preservation-grade immutable release/DOI is **not yet confirmed**. No dataset download should be represented as permanently archived without completing that release step.

```bash
pip install -r requirements.txt
pip install cryptography pytest
python -m pytest -q test_swarm_robust_holdout.py test_research_step9_evidence_audit.py

python swarm_robust_holdout.py --sample development \
  --sizes 5 10 20 50 \
  --out experiment_outputs/consistency-gated-step8/development

python swarm_robust_holdout.py --sample heldout \
  --sizes 5 10 20 50 \
  --out experiment_outputs/consistency-gated-step8/heldout

python research_step9_evidence_audit.py \
  --development experiment_outputs/consistency-gated-step8/development \
  --heldout experiment_outputs/consistency-gated-step8/heldout \
  --out experiment_outputs/consistency-gated-step9-audit
```

The archive does not contain private signing keys; independent **byte-for-byte replay of all signed witness envelopes** is not possible from the current saved records. Re-execution exercises the algorithm and cryptographic routines afresh.

## 10. Declarations and author sign-off (REQUIRED before submission)

- **Author names/order and affiliations:** provisional lead author supplied by the repository's preexisting `research_paper.md`. All other authorship and contributions must be confirmed with involved researchers; no undisclosed coauthors should be added or removed.
- **Corresponding email and ORCID:** must be confirmed by author; not inserted from inference or personal accounts.
- **Funding:** `[AUTHOR CONFIRMATION REQUIRED — do not assert that funding was absent]`.
- **Competing interests:** `[AUTHOR CONFIRMATION REQUIRED]`.
- **Ethics/consent:** software-only simulated data are used; any journal-specific ethics-exemption or non-applicability wording requires editorial/author confirmation.
- **Author contributions:** `[AUTHOR CONFIRMATION REQUIRED — CRediT roles and all coauthors]`.
- **Data and code licensing:** confirm permissions and license compatibility for the manuscript, reused components, figure assets, and final archive.
- **Prior and simultaneous related manuscripts:** disclose the earlier swarm coordination/security/authority and acoustic-localization work; verify no duplicate article content or overlapping evidence counts.
- **Venue fit and instructions:** select a journal accepting rigorously bounded software evaluations and negative results, verify article type, novelty threshold, word/figure limits, reference style, data statement and applicable charges.
- **Pre-submission sign-off:** `[NOT RECEIVED]`. Neither manuscript completion nor green CI authorizes submitting without these items.

## References

[1] Gerkey, B. P., and Matarić, M. J. (2004). A formal analysis and taxonomy of task allocation in multi-robot systems. *The International Journal of Robotics Research*, 23(9), 939–954. https://doi.org/10.1177/0278364904045564

[2] Choi, H.-L., Brunet, L., and How, J. P. (2009). Consensus-based decentralized auctions for robust task allocation. *IEEE Transactions on Robotics*, 25(4), 912–926. https://doi.org/10.1109/TRO.2009.2022423

[3] Raja, S., Habibi, G., and How, J. P. (2022). Communication-aware consensus-based decentralized task allocation in communication constrained environments. *IEEE Access*, 10, 19753–19767. https://doi.org/10.1109/ACCESS.2021.3138857

[4] Zhao, C., Li, M., Zhu, X., and Zhu, C. (2026). Assignment-consistent dynamic multi-UAV task allocation: Communication-efficient dynamic multi-unmanned aerial vehicle task allocation under stale and asymmetric information. *Drones*, 10(7), 523. https://doi.org/10.3390/drones10070523

[5] Liu, T., Wei, S., Liu, C., Bai, G., Zhang, J., and Yuan, C. (2026). A resilient task allocation method for unmanned aerial vehicle swarm considering local information. *Reliability Engineering & System Safety*, 272, 112442. https://doi.org/10.1016/j.ress.2026.112442

[6] Lamport, L., Shostak, R., and Pease, M. (1982). The Byzantine generals problem. *ACM Transactions on Programming Languages and Systems*, 4(3), 382–401. https://doi.org/10.1145/357172.357176

---

**Submission status:** STRUCTURAL DRAFT COMPLETE; **journal submission NOT AUTHORIZED**. The paper is intended as a candid reproducible analysis of simulation trade-offs, not a novel strictly dominant algorithm. Complete the author/declaration/overlap and venue-specific review before submitting.
