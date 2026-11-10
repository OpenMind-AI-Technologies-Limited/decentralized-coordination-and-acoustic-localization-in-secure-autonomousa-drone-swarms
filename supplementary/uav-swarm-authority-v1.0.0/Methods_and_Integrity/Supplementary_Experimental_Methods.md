# Swarm Resilience and Reproducibility Protocol

**Artifact scope:** software-only virtual-network and known-reference acoustic simulations. No claim of GPS-denied autonomous flight, formal Byzantine consensus, radio latency, aerodynamic swarm safety or physical flight performance.

## Research questions

1. Under static known membership, what fraction of seeded trials obtains a quorum-certified leader despite delivery loss, Byzantine vote withholding/equivocation, or malformed envelopes?
2. Does a near-even partition fail closed instead of electing an unsafe leader?
3. Does the local separation algorithm change hypothetical instantaneous pairwise distance violations relative to unchanged waypoints? These are not realized collisions.
4. How does health-aware greedy task assignment compare to naive node-ID assignment on task eligibility and straight-line task distance?
5. How do source localization and *separately* known-beacon receiver localization behave under synthetic noise? The beacon frame is externally known and is not independently GPS-denied UAV navigation.

## Algorithms under test

The network experiment uses the repository's real MeshNode, Ed25519 keys, AES-256-GCM envelopes, signed votes, certificate checks and health telemetry. The transport alone is substituted by a seeded virtual packet queue. Do not mistake this for independently validated network deployment or a competing consensus protocol.

Formation trials call the production formation_target and separate_from_neighbors routines. These create hypothetical 3D waypoints, not closed-loop trajectories. Allocation trials call the actual allocate_tasks function, compared with a simple position- and health-unaware node-ID assignment. Acoustic trials use acoustic_benchmark and estimate_receiver_xy with known 2D reference points.

## Experiment matrix

| Variable | Settings |
|---|---|
| Member counts | 5, 10, 20, 50 |
| Byzantine bound f=floor((N-1)/3) | 1, 3, 6, 16 |
| Required quorum N-f | 4, 7, 14, 34 |
| Election scenarios | healthy, packet loss 15% with three signed retransmissions, Byzantine withholding, equivocation, tampered envelopes, quorum partition, minority partition, leader failure |
| Formation patterns | line, V, circle, grid; 12-meter target spacing; Gaussian observed displacement sigma 6m |
| Assignment | Same fixed-seed task/position set with and without approximately 20% degraded nodes |
| Known-beacon receiver | Four fixed 2D anchors, no GPS input; 0, 100, 350 microsecond synthetic arrival jitter; no-reference baseline |
| Sound source | Four fixed sensors, synthetic impulse noise sigma 0, 0.02 and 0.05 |
| Primary seed | 2026, with derived per-scenario and per-trial seeds |
| Automated CI evidence | Six repetitions per scenario; all fleet sizes; raw artifact uploaded to Actions |
| Publication-scale default | Twenty repeats; more permitted for uncertainty analysis |

Virtual delivery delay is uniformly sampled from 1–12 simulated milliseconds. Neither virtual time nor measured host execution duration is physical UAV network latency. Packet counts and bytes are measured from the actual cryptographic envelopes produced by each run.

### Outcome definitions

- **Converged** means eligible honest nodes hold the expected certificate; in a minority/near-even partition convergence is FALSE, even if the desired secure result is withholding all leadership.
- **Expected outcome met** is TRUE for a valid election in quorum-available scenarios, or for total safe unavailability in a partition with no viable quorum.
- **Safety disagreement** is an observed pair of different certified leaders in the same epoch. A zero observed count is not a proof of safety in all asynchronous schedules.
- **Attack rejection** counts receiver exceptions for malformed encrypted packets. It is not a calibrated security detection classifier.
- **Formation** records minimum pairwise waypoint separation and distance violations before/after suggested adjustment, plus reference error and waypoint displacement. No physical collisions, real energy or flight dynamics are measured.
- **Task assignment** reports requested and assigned task counts, assignments to ineligible nodes and mean Euclidean distances. The baseline is intentionally simple and is not a recognized state-of-the-art comparison.
- **Localization** reports success rate over all trials and conditional position error among successful estimates. Failed estimates remain null and their missing count is reported; no imputation to 0m. TDOA fit residual is not ground-truth position RMSE.

## Reproduction commands

    python -m pip install numpy scipy cryptography pytest
    python -m pytest -q test_swarm_experiments.py

    python -m pip install matplotlib
    python swarm_experiment_runner.py --sizes 5 10 20 50 --trials 20 --seed 2026 --bootstrap-samples 2000 --figures --out experiment_outputs/swarm

    python swarm_experiment_runner.py --sizes 5 10 --trials 3 --seed 2026 --out experiment_outputs/smoke

Generated files: trials.csv, trials.json, summary.json, manifest.json, REPORT.md and (when requested) PNG/SVG figures. The manifest includes the SHA-256 digest of trials.json. Every row must originate from a real execution of the designated harness. GitHub Actions uploads observed outputs, not prefilled tables. Never claim numerical results without checking those actual artifacts.

## Statistical method

Binary success proportions use 95% Wilson intervals. Continuous metric means use seeded 95% percentile bootstrap intervals. Paired baseline deltas refer to the same generated per-trial scene. These do not establish statistical significance or generalization beyond the simulation distribution. One observation cannot produce a useful confidence interval. Randomized simulation choices are seed-reproducible; harness wall time and environment metadata may vary.

## Scientific and engineering limitations

This work does NOT establish full BFT view-change safety/liveness, field measurements, real microphone clock synchronization, rotor/multipath effects, GPS-denied autonomous control, hardware-in-the-loop telemetry, flight certification or real power/energy data. Source XY and receiver XY are distinct. Strong submission claims require independent validation and recognized baseline implementations.

## Branch acceptance conditions

- Regression tests pass across Linux, Windows and macOS.
- CI produces parseable nonempty raw results for N=5,10,20,50 and a summary artifact.
- Reported numerical claims can be traced to the exact generated trial and computation.
- Synthetic scope and unverified real-world claims are clearly separated.
