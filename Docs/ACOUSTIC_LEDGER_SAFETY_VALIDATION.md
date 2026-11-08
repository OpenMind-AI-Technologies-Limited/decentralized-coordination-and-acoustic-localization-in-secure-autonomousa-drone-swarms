# Acoustic Source Localization, Quorum Audit and Simulation Safety

**Scope:** optional signed-mesh simulator and legacy acoustic/ledger modules.
**Research integrity:** these are software-validation results. No real microphone,
GPS-denied self-localization, physical flight or full Byzantine consensus is claimed.

## Acoustic source estimation

- `acoustic_tracking.py` uses bounded GCC-PHAT/direct cross-correlation for the
  time difference of arrival, with physically permissible lag limited by known
  microphone/sensor XY baselines and the assumed sound speed (343 m/s).
- `acoustic_quality.py` rejects poor 2D array geometry, silent/nonfinite signals,
  unequal capture windows, unrealistic sample rates and impossible delays.
- Clock synchronization uncertainty is an optional **input supplied by the
  experiment**, not evidence that the software can synchronize microphones.
  When supplied and worse than one sample period, localization is refused.
- `localize()` returns `estimate_type=sound_source_xy`,
  `self_localization_supported=False`, and `tdoa_residual_rmse_m`. This residual
  is the optimizer's fit to TDOA equations, **not** ground-truth positional RMSE.
  `confidence` remains a heuristic residual-based score; it is not calibrated
  probability.
- Existing legacy `SwarmManager` may still command a formation in response to
  a configured acoustic event. The new `DroneMeshSimulation.localize_acoustic()`
  intentionally *never* commands flight automatically: acceptable source
  observations are recorded as quorum-certified evidence only.
- Localization of drones themselves in a GPS-denied environment would need
  additional reference-frame observability, synchronized clocks, hardware
  calibration, multipath modeling and independently benchmarked sensor fusion.

### Reproduce synthetic ground-truth errors

```bash
python acoustic_benchmark.py --seed 26 --trials 12 --out experiment_outputs/acoustic
```

Outputs `synthetic_acoustic_trials.csv` and
`synthetic_acoustic_summary.json`; every detected trial includes the actual
known-source position error **separately** from the TDOA residual. Inputs are
reproducible impulse-arrival simulations with Gaussian noise. The output
explicitly tags `hardware_verified=false`; never re-label synthetic values as
real-world field measurements.

## Signed quorum flight audit

`flying_ledger.py` still provides a legacy best-effort chain. Verification was
hardened to atomically validate/append blocks and verify each non-genesis
record's hash, adjacency and author signature. Best-effort replication alone
is not a fork-resolving consensus protocol.

`quorum_audit.py` is a new independent signed audit layer with:

1. A known Ed25519 static-member roster and validated certified leader.
2. Signed event proposals bound to height, parent hash, epoch and content.
3. Unique per-member signed votes, locked by height *before signing* and
   optionally fsynced to private member files on disk.
4. At least `N-f` valid approvals, with `N>=3f+1`, before a commit.
5. Cryptographic verification of commits and their certificates, fork/double
   vote rejection, deterministic replica catch-up, idempotent replay and
   startup validation of stored records.

The simulator transparently records signed **formation/task intentions** and
accepted acoustic observations. It gathers votes and broadcasts commits
through a **trusted in-process test orchestrator**, not a fully networked
consensus protocol. A surviving quorum can commit during one replica's
outage, and that replica can catch up later.

Static membership and honest signatures are essential assumptions.
Dynamic membership, reconfiguration, fully adversarial view-change safety,
durable network receive windows, and asynchronous Byzantine liveness are
**not** implemented or proved.

## Rule-based and ML-assisted software safety

`swarm_safety.py` wraps the existing `MLDecisionSupport` potential-field
collision heuristic. It **does not** claim a trained risk classifier or
statistically validated control policy. Before forwarding a certified motion
to the existing simulated `Drone.goto()` route it checks:

- Quorum and simulated drone/hardware state, battery reserve and motor health
- Ground-plane operating range, altitude and nonfinite targets
- Entire planned trajectory's minimum separation from nearby members
- Predicted nearby obstacle risk over a three-second simulated horizon
- Optional **measured** peer RTT thresholds

A background simulation safety loop holds active motion on quorum loss or
an excessive observed RTT and invokes local return-to-home behavior on
battery/motor degradation. It never automatically arms or commands physical
UAV hardware.

### Latency evidence

`MeshNode.start_latency_probe()` and
`DroneMeshSimulation.measure_peer_rtt()` use signed UDP request/reply packets
and `time.perf_counter()`. These measure **real localhost UDP round trips**.
They do not measure true UAV radio, actual C++↔Python IPC, or flight-control
latency. `MLBridge.round_trip()` remains explicitly *synthetic*; synthetic
bridge values are **not** silently fed to the safety threshold.

## E2E software validation

```bash
python -m pytest -q \
  test_acoustic_quality.py test_acoustic_benchmark.py \
  test_quorum_audit.py test_swarm_safety.py test_swarm_resilience.py \
  test_ledger_and_acoustic.py test_mesh_simulation.py
python main.py --mesh-gui
python main.py --mesh-simulation
```

GitHub Actions validates Python 3.10/3.11 on Linux/Windows/macOS and native
controller builds on Linux/macOS. Passing CI establishes repeatable
**software** behavior in these tested settings, not external flight safety.

## Limits and next research requirements

Real field recordings, synchronized 3D moving microphones, rotor/multipath
interference, calibrated uncertainty, hardware-in-the-loop fault injection,
full BFT view-change, latency percentiles under radio loss, 20–50 drone
experiments, statistical comparisons and independent flight-safety review
remain outside this software-validation scope. Scientific manuscript claims
must reflect this boundary.
