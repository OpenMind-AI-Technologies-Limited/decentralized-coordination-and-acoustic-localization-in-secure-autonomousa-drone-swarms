# Step 9 — Explicit Manuscript Claim Register

**Default manuscript status: NO-GO for algorithmic superiority.** All claims are limited to controlled software simulation, not real UAV flight. This register is maintained as an audit trail; it does not override journal editorial review.

| Claim ID | Status | Safe/unsafe proposed wording | Evidence | Necessary restriction |
|---|---|---|---|---|
| `S9-C01` | **ALLOW** | 720 Step 8 heldout simulated episodes were independently seeded and each of six policies ran against same episode | heldout/manifest.json;heldout/episodes.json;heldout/paired_policies.json | No physical or independent deployment validation |
| `S9-C02` | **ALLOW** | Veto had 0/720 resource-ineligible-assignment episodes; median+motion had 30/720 on this controlled synthetic mixture | heldout/paired_policies.json;Step9 truth recomputation | Not real incident rate; zero events not zero probability |
| `S9-C03` | **ALLOW** | In the one malicious witness case, 3-signer median often prevented one conflicting claim from vetoing an otherwise eligible drone | heldout/stratum_summaries.json;Step8 controlled tests | Assumes two independent honest witness observations |
| `S9-C04` | **ALLOW** | The median health gate can accept falsely healthy source telemetry when two peer witnesses collude | heldout/paired_policies.json;test_swarm_robust_holdout.py | Violates witness-specific f_w=1; annotate global f separately |
| `S9-C05` | **ALLOW** | The simulation's impossible-position-jump stress can trigger bounded-motion rejection | test_swarm_robust_holdout.py;Step8 scenario records | Does not prove detection of plausible spoofing or real flight dynamics |
| `S9-C06` | **ALLOW_WITH_QUALIFICATION** | A signed witness proves control of an enrolled signing key for the issued claim | swarm_consistency_gate.py;swarm_mesh.py | Does not prove telemetry correctness or physical sensor provenance |
| `S9-C07` | **BLOCK** | The median gate unconditionally outperforms conservative veto across both safety and task availability | Step8 full heldout results | Contradicted by observed 30 vs 0 unsafe-assignment episodes |
| `S9-C08` | **BLOCK** | Original full CBBA was implemented and benchmarked with realistic asynchronous network faults | swarm_allocation_baselines.py;Step5 docs | Only synchronous single-task CBAA and static additive bundle-auction specializations |
| `S9-C09` | **BLOCK** | Owner-signed STOPPED ensures drone physically stopped and task executes exactly once | swarm_task_recovery.py;Step6 docs | Malicious registered owner can sign a lie; no recipient-side hardware fencing |
| `S9-C10` | **BLOCK** | The saved Step 8 archive independently replays every Ed25519 peer signature and network receipt | heldout/episodes.json;Step9 audit | Raw individual witness signature/envelope packets absent from archive |
| `S9-C11` | **BLOCK** | One observed zero-event safety count proves absence of all future hazards | Step9 Wilson interval;Step8 heldout | Even independent binomial approximation has a positive upper uncertainty bound |
| `S9-C12` | **BLOCK** | Mixed-scenario proportions represent actual attack frequency or UAV hardware risk | Step8 frozen synthetic design | Balanced scenario distribution and no hardware observations |
| `S9-C13` | **BLOCK** | false_rejected_healthy_members is a global false-positive safety metric | swarm_robust_holdout.py;Step8 findings | Resource-capable sources with impossible signed motion can be legitimately rejected |
| `S9-C14` | **ALLOW** | Step 9 independently recalculates offline resource eligibility and true-space distance for all 4,320 heldout policy rows | research_step9_evidence_audit.py;CI | Audit does not itself prove signature capture integrity |

**Submission policy:** Any BLOCK statement must be removed/replaced before drafting an abstract, conclusion, highlights, cover letter or reviewer questionnaire. ALLOW_WITH_QUALIFICATION requires the displayed restriction in the same substantive discussion. All empirical numeric claims require the generated audit manifest and GitHub run reference. Publication-grade novelty and hardware claims are not authorized by this register.

Primary literature comparator: Choi, Brunet & How (2009), *Consensus-Based Decentralized Auctions for Robust Task Allocation*, DOI [10.1109/TRO.2009.2022423](https://doi.org/10.1109/TRO.2009.2022423). Their full CBBA is not implemented in this repository.
