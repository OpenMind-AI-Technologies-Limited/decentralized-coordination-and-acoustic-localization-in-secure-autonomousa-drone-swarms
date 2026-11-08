# Coordination Architecture and Publication-Claim Audit

**Scope:** baseline `main` compared with additive `swarm-mesh-coordination` work.  
**Review target:** swarm coordination, distributed identity, leader election, local formation planning, reproducibility.

## Confirmed baseline behavior

| Component | Actual baseline implementation | Research-report implication |
|---|---|---|
| Leader selection | `SwarmManager.elect_leader()` loops over all drones in one process and chooses maximum `Drone.get_suitability_score()` | Centralized election, not a distributed Byzantine agreement |
| Suitability score | `0.4*battery + 0.3*signal_strength + 0.3*processing_capability` | Does not match manuscript MCSS (battery/motor/link 0.45/0.35/0.20) |
| Liveness | `HEARTBEAT_TIMEOUT=5.0`; manager monitor sleeps 1 s; drone loop updates its own heartbeat | Manuscript's 1.2-s failover must not be presented as measured |
| Leader follow | `_ml_follow_leader` exists; monitor loop explicitly selects event-driven, explicit-command control | Continuous autonomous follow is not guaranteed on baseline runtime path |
| Inter-drone message path | `leader_follower_logic.CommunicationManager` is an in-process queue/event bus | Existing command flow is not demonstrably secure peer-to-peer network traffic |
| Secure channel | `communication.py` has AES-GCM and sequence checks, but does not constitute the event-bus path | Do not claim end-to-end authenticated distributed command propagation |
| Flying Ledger | Signed SHA3 hash chains replicated through manager mediation | Replication is not consensus, fork resolution or BFT commit |
| Acoustic source estimation | TDOA solver receives known sensor XY coordinates | It estimates an acoustic source, not drone self-localization in GPS-denied conditions |
| C++ control | `dronecontroller.cpp` includes placeholder MAVLink operations; Python `drone.py` separately has MAVSDK integration | Avoid claiming complete C++ hardware-closed-loop flight validation |
| Latency | `MLBridge.round_trip` synthesizes timestamps from configurable processing and network delays | Synthetic timing cannot support measured hardware RTT claims |

## Implemented on this branch

- `swarm_mesh.py`: independent `MeshNode` identity and state, normalized MCSS health model (45% battery, 35% motor, 20% link), Ed25519-signed votes, quorum election certificates, epoch tracking, replay window, known-node authentication, AES-256-GCM packet confidentiality and certified command acceptance.
- `swarm_transport.py`: peer-addressed UDP packet delivery. No master scheduling of leader state.
- `swarm_runtime.py`: per-drone process runtime. Uses caller-supplied health and safe action callbacks, sends authenticated heartbeat telemetry, detects leader heartbeat timeout, retries election and dispatches only certificate-authorized instructions.
- `swarm_formation.py`: each recipient computes its own deterministic V/line/circle/grid slot, with neighbor separation adjustments.
- `test_swarm_coordination.py`: checks quorum election, replay, unknown identity, forged certificate, partition refusal, equivocating vote, UDP packet delivery, formation math and four independent local UDP agents.

The old UI, `SwarmManager` and `Drone` paths remain untouched to prevent accidental hardware behavior changes. The new runtime is **experimental and opt-in**, not yet the default GUI flight controller.

## Election safety claim and assumptions

Registered membership `N`, declared Byzantine faults `f`, and quorum `q=N-f` require `N>=3f+1`. Each honest member signs at most one candidate per epoch; its private signing key is uncompromised. Two quorums intersect in at least `N-2f >= f+1` members, so two conflicting, independently valid certificates at the same epoch would require an honest node to sign conflicting votes.

This is **same-epoch quorum-certificate safety under stated assumptions**. It is *not* a full asynchronous Byzantine consensus protocol, or proof of termination/liveness in an arbitrary partition. A minority partition cannot produce a new certificate in the four-node test. A malicious node may lie about its own fitness: reported health is authenticated by origin but is not independently attested.

**Not yet implemented/proved:** member admission/revocation, persisted key management, distributed score attestation, strong transport availability, threshold/three-phase BFT protocol, automatic recovery from all competing election views, bounded failure detection under arbitrary network delay, real autopilot integration.

## Reproducibility and test commands

```bash
python -m pip install cryptography pytest
python -m pytest -q test_swarm_coordination.py
python -m pytest -q test_dynamic_features.py test_ledger_and_acoustic.py test_swarm_coordination.py
```

The independent UDP test binds loopback addresses and never arms or moves a real drone. Signed formation actions are delivered to a caller-provided callback, which must enforce geofence, altitude, physical separation, and autopilot constraints.

## Publication blockers

1. Reconcile MCSS equation and implementation. Baseline uses 40/30/30; experimental node uses 45/35/20. Do not silently claim the new node replaces the old manager.
2. Establish a justified distributed threat model, evidence of fault limits, certificate safety, and realistic termination assumptions.
3. Integrate new mesh runtime into existing simulation and instrument all state transitions, election recovery timing, and message volumes.
4. Test failure injection, reconnection, adversarial schedules, forged telemetry, simultaneous elections, view changes, sparse communication and large-scale fleets.
5. Benchmark formations against explicit baselines using trajectories, collisions, energy, formation error and completion probability; repeat experiments and publish raw metrics.
6. Correct paper reference-list holes `[47]`, `[48]`, `[49]`, absent Table I/II bodies, inconsistent acoustic test geometry and simulated RTT claims.
7. Clearly separate software-in-the-loop results from hardware-in-the-loop and flight experiments. Do not claim real drone safety without hardware evidence.

**Readiness:** implementation groundwork underway. Not peer-reviewed-journal submission ready. No figures, numerical timing claims or field trials are inferred from passing unit tests.
