# Seeded Swarm Software-Experiment Results

**Scope:** deterministic virtual-network / waypoint / known-reference
acoustic experiments. NO physical UAV, radio, field-microphone,
GPS-denied autonomous navigation or Byzantine consensus proof.

- Git commit: `78cce082c5acabe68ebc5f76a32872b210308af5`
- Seed: 2026; repeats per setting: 6
- Fleet sizes: [5, 10, 20, 50]
- Intervals: 95% percentile bootstrap for continuous metrics;
  95% Wilson for observed binary rates. With only one repeat,
  uncertainty limits are unavailable. Conditional localization errors
  exclude failed localizations and always report the missing count.
- Virtual packet delay is not physical radio latency; host
  wall time is not flight-control latency.

| Family | Scenario | N | Trials | Main observed metric (95% interval) |
|---|---|---:|---:|---|
| acoustic_source | impulse_noise_0.0 | 4 | 6 | position_error_m: 0.002 [0.001, 0.003] |
| acoustic_source | impulse_noise_0.02 | 4 | 6 | position_error_m: 0.002 [0.001, 0.003] |
| acoustic_source | impulse_noise_0.05 | 4 | 6 | position_error_m: 10.226 [4.166, 16.698] |
| allocation | degraded | 5 | 6 | ineligible_assignment_reduction: 0.333 [0.000, 0.667] |
| allocation | degraded | 10 | 6 | ineligible_assignment_reduction: 1.667 [1.333, 2.000] |
| allocation | degraded | 20 | 6 | ineligible_assignment_reduction: 2.500 [2.167, 2.833] |
| allocation | degraded | 50 | 6 | ineligible_assignment_reduction: 7.000 [5.746, 7.833] |
| allocation | healthy | 5 | 6 | ineligible_assignment_reduction: 0.000 [0.000, 0.000] |
| allocation | healthy | 10 | 6 | ineligible_assignment_reduction: 0.000 [0.000, 0.000] |
| allocation | healthy | 20 | 6 | ineligible_assignment_reduction: 0.000 [0.000, 0.000] |
| allocation | healthy | 50 | 6 | ineligible_assignment_reduction: 0.000 [0.000, 0.000] |
| beacon_receiver | known_beacons_jitter_0us | 4 | 6 | position_error_m: 0.000 [0.000, 0.000] |
| beacon_receiver | known_beacons_jitter_100us | 4 | 6 | position_error_m: 0.044 [0.033, 0.057] |
| beacon_receiver | known_beacons_jitter_350us | 4 | 6 | position_error_m: 0.153 [0.117, 0.201] |
| beacon_receiver | no_beacon_reference | 4 | 6 | position_error_m: n/a |
| election | byzantine_equivocation | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | byzantine_equivocation | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | byzantine_equivocation | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | byzantine_equivocation | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | byzantine_withholding | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | byzantine_withholding | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | byzantine_withholding | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | byzantine_withholding | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | healthy | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | healthy | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | healthy | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | healthy | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | leader_failure | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | leader_failure | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | leader_failure | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | leader_failure | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | minority_partition | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | minority_partition | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | minority_partition | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | minority_partition | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | packet_loss | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | packet_loss | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | packet_loss | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | packet_loss | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | quorum_partition | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | quorum_partition | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | quorum_partition | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | quorum_partition | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | tampered_packets | 5 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | tampered_packets | 10 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | tampered_packets | 20 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| election | tampered_packets | 50 | 6 | expected_outcome_met: 1.000 [0.610, 1.000] |
| formation | circle | 5 | 6 | pair_violation_reduction: 0.167 [0.000, 0.500] |
| formation | circle | 10 | 6 | pair_violation_reduction: 0.167 [0.000, 0.500] |
| formation | circle | 20 | 6 | pair_violation_reduction: 0.000 [0.000, 0.000] |
| formation | circle | 50 | 6 | pair_violation_reduction: 0.333 [0.000, 0.667] |
| formation | grid | 5 | 6 | pair_violation_reduction: 0.333 [0.000, 0.667] |
| formation | grid | 10 | 6 | pair_violation_reduction: 1.167 [0.500, 2.000] |
| formation | grid | 20 | 6 | pair_violation_reduction: 2.833 [0.667, 5.667] |
| formation | grid | 50 | 6 | pair_violation_reduction: 8.667 [6.833, 10.833] |
| formation | line | 5 | 6 | pair_violation_reduction: 0.500 [0.000, 1.167] |
| formation | line | 10 | 6 | pair_violation_reduction: 1.167 [0.500, 2.000] |
| formation | line | 20 | 6 | pair_violation_reduction: 1.500 [0.667, 2.667] |
| formation | line | 50 | 6 | pair_violation_reduction: 4.000 [2.667, 5.000] |
| formation | v | 5 | 6 | pair_violation_reduction: 0.167 [0.000, 0.500] |
| formation | v | 10 | 6 | pair_violation_reduction: 0.333 [0.000, 0.667] |
| formation | v | 20 | 6 | pair_violation_reduction: 0.500 [0.167, 0.833] |
| formation | v | 50 | 6 | pair_violation_reduction: 1.167 [0.667, 1.667] |

## Interpretation limits

The omniscient coordinator and naive task assignment are explanatory
baselines, not energy-matched published reference algorithms.
No p-values are inferred from bootstrap intervals. Clock precision,
real acoustic multipath, physical vehicle dynamics, hardware safety,
and cross-view Byzantine liveness require independent experiments.
The complete per-trial CSV and JSON accompany this summary.
