# Research Step 4 — Signed-Telemetry and Network Fault Injection

**Date:** 2026-11-15  
**Paper track:** *Consistency-Gated Task Allocation for Decentralized UAV Swarms Under Stale and Byzantine-Falsified Telemetry*  
**Parent:** [Step 2 prospective protocol](CONSISTENCY_GATED_STEP2_EXPERIMENTAL_PROTOCOL.md) and [Step 3 algorithm](CONSISTENCY_GATED_STEP3_ALGORITHM.md)  
**Status:** Implemented **software-only fault generation and diagnostic evidence**, not a fully validated adversarial experimental study, an operational drone security assessment or an original-method statistical superiority result.

## Research question and integrity guardrails

A validly signed message proves the identity of the reporter; it does **not** prove the sensor data truthful. A fully consistent false report remains indistinguishable from truth without independent, trustworthy measurement constraints. This Step 4 harness exercises the actual `MeshNode.publish_health()` and `MeshNode.receive()` Ed25519/AES-GCM path after a **fault-free signed quorum bootstrap**; the experiment changes the packet delivery/corruption, the registered member's own signed report and/or signed peer testimony. No outside spoofed keys are needed.

The coordinator sees only signed self-reported telemetry and optional *peer-signed synthetic witness claims*. The **offline oracle** is isolated from the allocator and available only to the evaluation functions. Witness claims are produced by an **idealized simulated peer observation source** that in some cases draws from simulator truth to model reliable measurements; they are not real independent sensors, and this information advantage must be disclosed. A signature cannot attest to the physical truth of a witness.

Every episode uses one task, a registered quorum-certified leader and the same coordinator-visible health/position cache to compare:

1. **Legacy greedy**: unchanged production allocation on locally accepted, fresh-to-leader health and cached XYZ.
2. **Age/motion-only gate**: unchanged optimizer after bounded local health/position age and motion checks, without witness requirements.
3. **Strict witness gate**: same optimizer and checks but requires two distinct, valid, time- and epoch-bound health witness signatures per member. If evidence is unavailable, it **abstains**, which can suppress all tasks.
4. **Offline ground-truth oracle**: diagnostic idealization **never provided to any of the above**; reference only, not a deployable comparator.

This design **does not yet establish fair new-method superiority**: the witness gate receives additional evidence and different information budgets than the legacy allocator. Later fair comparisons must add equally informed baselines and measure witness overhead.

## Scenarios and interpretation

| Scenario | Injection | Important observation / negative control |
|---|---|---|
| `healthy_control` | Fresh truthful signed telemetry | Age-only and legacy should agree with diagnostic oracle; strict witness gate abstains if zero witnesses |
| `stale_position` | New signed **health-only** heartbeat after 7 seconds; true XYZ changes by 80 m over the same synthetic interval | Cached old XYZ stays valid for greedy but not age gate; virtual movement 11.4 m/s, not physical flight |
| `signed_false_health` | Legitimate member 2 signs false battery/motor/link values | The age-only gate cannot detect this without independent evidence |
| `signed_position_spoof` | Member 2 self-signs position near task while true position is farther | Freshness alone cannot detect a coherent positional lie |
| `bounded_slow_drift` | Signed member 2 gradually moves reported XYZ at 2 m/s while true state remains far | Plausible-motion checks cannot prove truthful position |
| `honest_witnesses` | Two registered peers sign modeled accurate health observations | Strict gate can reject the lying subject under **idealized independent observer assumption** |
| `malicious_witness` | One legitimate peer signs false negative health for honest member 2, one other peer signs truth | A **single conflicting** valid witness in current Step 3 gate can cause false rejection / availability DoS |
| `colluding_witnesses` | Two registered peers knowingly corroborate a false self-report | Strict gate may **accept** false resource eligibility; for N=5 this exceeds f=1 and is explicitly beyond that declared budget, while N=10 has f=3 |
| `no_independent_witnesses` | Falsified self health without witnesses | Age-only may accept; strict gate abstains with availability cost |
| `packet_loss` | Seeded delivery loss and forcibly lost latest update for member 2 | Old cache persists; network loss measured in virtual scheduler, not empirical RF |
| `partition` | Targeted 2→leader partition on latest signed telemetry | Old member 2 XYZ is retained; fault injected after quorum bootstrap |
| `delayed_update` | Targeted five-second post-bootstrap delay to leader; decision before delivery | Pending messages are counted separately, not mislabeled as delivered |
| `tampered_packet` | Corrupt encrypted signed heartbeat in transit | Cryptographic receive rejects invalid packet, old value persists; rejected ≠ lost |

Scenarios are **constructed counterexamples / controlled fixtures**, not unbiased estimates of drone incident incidence. Different witnesses may lie, collude, become unavailable or use correlated sensors. The current gate's one-conflicting-witness veto is a **potential vulnerability** and an explicit hypothesis for later algorithm improvements. Step 4 records it rather than hiding failures.

## Network / fault model

- Initial bootstrap: signed, encrypted health+XYZ sent to all members using existing `InMemoryMesh`, then all vote for candidate 1 and install valid quorum certificate. **Bootstrap packets are intentionally excluded from network-fault counters**.
- Fault stage: `FaultNetwork` delivers later signed heartbeats to the coordinator with independently seeded virtual 1–16 ms delay, configured independent drop chance, explicit forced drop, partition, tampering or a pending long-delay queue. All receivers invoke the *real* `MeshNode.receive()` authenticated parser; AES-GCM tag failures are recorded as rejects, not silence.
- Absolute virtual time is controlled by a `ManualClock`; values are not radio latency or measured device wall time.
- Current **single-destination** fault graph is a controlled observation model, not arbitrary mesh-wide partition or independent adversarial consensus.
- At each decision, the recorded `quorum_fresh_at_decision` describes the **local** fresh-membership predicate; no claim is made that the simulated decision was actually transmitted or flown. The earlier Step 3 integration test covers quorum-certified task-command integration.
- The first 7-second movement case is a state trajectory *assumption* for ground-truth evaluation, not a running UAV dynamics model.

## Outputs and reproduction

```bash
python -m pytest -q test_swarm_telemetry_faults.py
python swarm_fault_experiment_runner.py --sizes 5 10 --trials 2 --seed 2026 \
  --out experiment_outputs/consistency-gated-step4
```

Outputs:

- `fault_trials.json`: full per-scenario assigned members, virtual packet traces without ciphertext/secret material, reference oracle results, component decisions, injected network counters and compromised-witness assumptions.
- `fault_trial_metrics.csv`: simple one-row-per-diagnostic-episode metrics, including distinct true-ineligibility and oracle-disagreement flags.
- `manifest.json`: source revision, platform, scenario/fleet counts, exact SHA-256 hashes, no-flight/no-sensor/no-comparative-results limitations.

Default produces **13 scenarios × 2 fleet sizes × 2 seeded repeats = 52 diagnostic episodes**, not 52 independent random field experiments. Episode random seeds affect network delay/loss, but selected synthetic layouts and attacker tactics are fixed; the resulting 52 rows must **not** be treated as independent strong inferential evidence.

For CI, `python -m compileall` and focused tests run on Linux/macOS/Windows; one Linux 3.11 job creates and verifies the new JSON/CSV/manifest artifact. Earlier 378 observations remain in their versioned supplementary folder, untouched.

## What's required next before a paper claim

1. Specify a **full attack/fault parameter distribution**, including continuous spoof magnitude, bounded healthy behavior, variable positions, task arrivals, sensor noise, varying compromised counts and independently selected random states; this release intentionally uses a transparent fixed-layout counterexample suite.
2. Implement matched published/state-of-the-art baselines (Hungarian, CBBA with disclosed assumptions) and at least one **equally informed** simple witness/age-only comparator. Do not confuse an offline oracle with a deployable state-of-the-art algorithm.
3. Replace one-witness veto with a rigorously evaluated robust aggregation/threshold strategy, or clearly report its adversarial availability problem; a multi-signer quorum is not automatically trusted sensory truth.
4. Add dynamic recovery/failure schedule experiments and correct task ownership/reassignment accounting.
5. Run a pilot for primary rate and variance, choose meaningful effect size and preregister/freeze held-out seed list before publication-scale trials.
6. Keep network receipt age vs observation capture age distinct. Receiver time cannot expose signed but old physical measurement.
7. Perform threat-aligned negative controls: malicious-witness DoS, coordinated false witness claims, benign packet loss, sensor disagreement, consistent forged positions.
8. Report **failed and missing observations**, false-reject and nonexecution costs, available evidence budget and source manifests; perform no post-hoc selective filtering.

**Step 4 completion condition:** code, regression tests, raw trace export, integrity manifest and observed full CI green. Passing tests only demonstrates the defined software fixtures; scientific efficacy remains **unverified**.
