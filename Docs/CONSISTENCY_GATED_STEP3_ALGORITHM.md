# Research Step 3 — Opt-In Consistency-Gated Task Allocation

**Date:** 2026-11-15  
**Paper:** *Consistency-Gated Task Allocation for Decentralized UAV Swarms Under Stale and Byzantine-Falsified Telemetry*  
**Parent:** [Step 2 protocol](CONSISTENCY_GATED_STEP2_EXPERIMENTAL_PROTOCOL.md)  
**Status:** Prototype algorithm implemented, integrated into the simulated certified command path, targeted tests and five handcrafted diagnostics. **No publication-scale experiments, fairness-controlled state-of-the-art comparison or hardware verification yet.**

## Precise contribution implemented

The current experimental question is whether we can reduce *avoidable* decisions based on stale or externally contradicted observations by inserting a deterministic, inspectable **evidence gate** **before** the unchanged production greedy task allocator.

The implementation is **not** a new optimizer, complete Byzantine consensus, authenticated sensor hardware, universal lie detector or flight controller. It does not replace the quorum leader, add new physical sensing or guarantee task completion. The original `swarm_tasks.allocate_tasks()` remains the default baseline in `DroneMeshSimulation.command_tasks()`.

### Algorithm sketch

For each registered drone `i`, the local leader inspects only authenticated observations already delivered through `MeshNode.receive` (or local `publish_health`), using separately recorded **health** and **position** receipt times:

1. **Existence and validity**: Both health and XYZ must exist and be finite. Bad data is rejected; absent data requests fresh evidence.
2. **Independent freshness**: `now - health_seen_at[i] <= H` **and** `now - position_seen_at[i] <= P`. Future times and stale information are excluded. A health-only heartbeat updates *only* health age, not position age.
3. **Bounded displacement**: If there is a previous XYZ sample, require `distance(current, previous) <= v_max * dt + motion_slack`. This only checks the two locally received samples; it cannot prove truthful motion or detect slow malicious drift.
4. **Optional signed independent reports**: A distinct enrolled peer reports its observation of subject `i` with Ed25519 signature on domain-separated tuple (reporter, subject, epoch, observation time, XYZ/health, positional uncertainty). Only matching registered, non-self, fresh, unique-identity signatures for the current epoch count. A **single contradictory valid witness currently rejects** the subject, a conservative choice that may let malicious witnesses harm availability. This must be evaluated against alternative policies.
5. **Configured corroboration threshold**: If the number of valid position/health witnesses is below policy requirements, request evidence. A policy with zero required witnesses uses age/motion-only screening and **does not claim to validate sensor truth**.
6. **Assignment**: Call the existing greedy allocator on **only accepted members**, retain explicit per-node decisions, and report unassigned tasks; no eligible allocation yields a study-level `ABSTAIN`. A quorum-certified leader still signs commands/audit intents through the existing authorization layer.

Decision reasons are `missing_self_observation`, `invalid_self_observation`, `invalid_observation_time`, `stale_health_or_position`, `implausible_position_jump`, `invalid_position_history`, `signed_witness_conflict`, `independent_evidence_insufficient` or `bounded_observations_pass`. Per-node actions are `ACCEPT`, `REQUEST_FRESH_EVIDENCE` or `REJECT`.

## Files

| File | Role |
|---|---|
| `swarm_consistency_gate.py` | Explicit `ConsistencyPolicy`, `SignedWitness`, `sign_witness`, signature-verified deterministic gating, and baseline allocator composition |
| `swarm_mesh.py` | New separate `positions_seen_at` and `previous_positions`; valid signed heartbeat without XYZ does not refresh cached position |
| `mesh_simulation.py` | Opt-in `consistency_policy` + `witnesses` on `command_tasks`; requires certified leader, preserves legacy default |
| `test_swarm_consistency_gate.py` | Unit and certified end-to-end path tests: stale age, signed false health with explicitly independently modeled observations, motion, witness integrity, abstention, old-epoch/self/tampered/duplicate reports |
| `consistency_gated_step3_probe.py` | Five diagnostic scenarios with explicit lack-of-independent-evidence negative control, manifest and checksum; **not** inferential study data |

## How to run

```bash
python -m pytest -q test_swarm_consistency_gate.py
python consistency_gated_step3_probe.py --out experiment_outputs/consistency-gated-step3
```

Example of opt-in simulation use (after a quorum leader is available):

```python
from swarm_consistency_gate import ConsistencyPolicy

# Gate only on health/position freshness and bounded motion.
result = simulation.command_tasks(
    {"inspection": (15., 4., 12.)},
    consistency_policy=ConsistencyPolicy(
        max_health_age_s=1.5, max_position_age_s=1.0
    ),
)
print(result["assigned"], result["unassigned"], result["telemetry_decisions"])
```

To require external corroboration, supply *verified cryptographically signed peer witness* objects generated from **real independent observations**, and set `min_health_witnesses` and/or `min_position_witnesses`. The repository does not yet implement physical independent observers; synthetic signed reports in tests are idealized controlled inputs. Verification of the Ed25519 signature confirms who **claimed** to observe the fact; it is not proof that the signer observed or reported it truthfully.

### Default behavior and compatibility

- Calling `command_tasks(tasks)` with no policy is unchanged and executes the original greedy baseline.
- Passing witnesses without explicitly enabling a consistency policy is rejected.
- The gate does not automatically start flight, bypass signed quorum authority, persist external attestation trust or select hardware.
- Old supplementary observations and Step 2 baseline code/results remain untouched. The `positions_seen_at` metadata addition does not change baseline allocation until a policy is supplied.

## Demonstration matrix and expected interpretation

| Diagnostic condition | Legacy behavior | Expected gate behavior | What it does **not** show |
|---|---|---|---|
| Honest fresh reports | Allocate closest suitable node | Same allocation with self-report-only evidence tier | External truth of own report |
| Recent health, 7-second-old XYZ | May allocate from old cached position | Request new XYZ; choose other eligible member | Physical collision avoidance or ground-truth sensor accuracy |
| Fresh signed false health, **no** witnesses | Can allocate lying member | **Still can allocate lying member**: deliberately preserved negative control | Universal Byzantine detection |
| Fresh signed false health with two independent accurate signed health witnesses | Can allocate lying member | Contradiction rejects member; another may be selected | Real sensor verification, f-Byzantine correctness proof |
| Fresh signed false health with strict witness requirement but no witnesses | Can allocate based on self report | Abstain/reject eligible set until evidence arrives | Availability guarantee in partitions |

The five conditions are **constructed demonstrations**, not independent trials, clinical/in-field performance statistics or proof of improved population averages.

## Security, performance and validity caveats

1. Signed peer witness messages are generated/validated by the gate API, not yet collected from a real independent sensor or a distributed peer-to-peer witness protocol. A valid witness may be a liar. Multi-witness agreement with f compromised reporters cannot be assumed without an explicit independent trust/sensor model.
2. Using strict independent evidence requirements may cause **unavailability** when reports are missing; one malicious signed contradictory witness may cause additional DoS. The correct Byzantine threshold/veto policy must be studied in Step 4/7, not presumed.
3. Current freshness is recorded at local **receipt time**, not necessarily physical sensor capture time. A compromised member can fresh-sign an old observation; receiver age alone cannot reveal that. Stronger claims require authenticated capture timestamps plus bounded trusted clock offsets or external observations.
4. The `previous_positions` bound reflects two received samples; it cannot prove a continuous trajectory or prevent slow deception, GPS spoofing, rotor interference, or flight collisions.
5. Signature verification happens for every supplied witness per decision. Production deployment would need resource and witness-count bounds, caching with correctness guarantees, revocation and fully specified replay state.
6. The task allocator remains single-certified-coordinator greedy, not globally optimal or fully leaderless; no Hungarian/CBBA result or statistically grounded energy metric exists yet.
7. Cross-platform CI verifies program behavior under tests and virtual networking, not independent adversarial security or real-world generalization.

## Exit criteria for Step 3

- [x] New algorithm module with configurable explicit evidence contract and reasoned accept/refuse/abstain actions.
- [x] Independently tracked health/position receipt ages in the existing authenticated message path.
- [x] Signed-witness origin, epoch, subject, freshness, duplicate and contradiction checks.
- [x] Integration in the certified simulated task path without changing the opt-out baseline.
- [x] Unit, negative controls, and actual signed heartbeat integration tests added.
- [x] Diagnostic JSON/manifest generator implemented, with explicit research limitations.
- [ ] PR CI pass and merge; mark checked after observed successful run.
- [ ] Full attack generator, fair optimizers, recovery state, independent larger experiments, statistical analysis: **Steps 4–9**.

**Step 4 entry:** Generate reproducible malicious self-report, stale sensor, false witness, coordinated slow-drift and packet-fault sequences while respecting two distinct observation channels and keeping truth oracle offline. Include denial-of-service negative cases so observed security is not simply a byproduct of declining all tasks.
