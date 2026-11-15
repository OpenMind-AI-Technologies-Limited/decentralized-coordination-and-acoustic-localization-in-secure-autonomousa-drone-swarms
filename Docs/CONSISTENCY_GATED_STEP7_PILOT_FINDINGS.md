# Step 7 — Observed Randomized Pilot Findings and Scientific Go/No-Go Review

**Observed date:** 2026-11-16. **Original executed source SHA:** `dbfeb8dfb6f7250bd6cca957441cd2b772a0c90f`.  
**Source CI run:** https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43763311295  
**Source artifact:** https://github.com/smshagor-dev/decentralized-coordination-and-acoustic-localization-in-secure-autonomousa-drone-swarms/actions/runs/43763311295/artifacts/14180314212  
**Frozen design:** [CONSISTENCY_GATED_STEP7_RANDOMIZED_PILOT_PROTOCOL.md](CONSISTENCY_GATED_STEP7_RANDOMIZED_PILOT_PROTOCOL.md)

This file records numbers extracted from the actual CI artifact ZIP **after successful validation of 960 episode records, 5,760 paired method rows, 192 stratum summary records, and every SHA-256 hash**. It is not a simulated example table or an estimate filled in from expectations. Any later source-code modifications must regenerate the archive and compare the recomputed summaries before the data are reused in a manuscript.

## Primary result (exploratory only)

| Policy | Episodes with ≥1 offline ground-truth **resource-ineligible** assigned member / 960 | Mean assigned tasks / episode | Mean unassigned tasks / episode |
|---|---:|---:|---:|
| `greedy_signed` | **98 / 960** | 3.918 | 0.000 |
| `age_only` | 99 / 960 | 3.872 | 0.046 |
| `motion_age` | 99 / 960 | 3.872 | 0.046 |
| `witness_age` | 49 / 960 | 3.850 | 0.068 |
| `full_opportunistic` | 49 / 960 | 3.850 | 0.068 |
| `full_strict` | **45 / 960** | **3.699** | **0.219** |

**Meaning:** The pooled counts are for a **deliberately balanced synthetic mixture** of eight scenario types, not a realistic attack prevalence, not a paired hypothesis test over deployment incidents, and not proof of physical UAV safety. A strict gate can suppress task execution; reducing harm by refusing tasks trades off with availability. No p-value or journal-level superiority conclusion is claimed.

The primary endpoint is a simulated, **resource-ineligible task assignment** (true battery <30%, motor <75% or link <40%). Wrong or longer-distance assignments caused by false position alone may not contribute to this particular endpoint; separate travel, regret, feasibility and realistic dynamic task completion require development.

## Scenario-level observations (each scenario pools four sizes × 30 seeds = 120 independent synthetic episodes)

| Scenario | Greedy harmful episodes | Age-only | Witness+age | Strict full | Mean tasks assigned, greedy / strict |
|---|---:|---:|---:|---:|---|
| Benign | 0/120 | 0/120 | 0/120 | 0/120 | 3.94 / 3.88 |
| Benign sensor noise | 0/120 | 0/120 | 0/120 | 0/120 | 3.95 / 3.85 |
| Signed false health | **49/120** | **50/120** | **0/120** | **0/120** | 3.72 / 3.58 |
| Signed false position | 0/120 | 0/120 | 0/120 | 0/120 | 4.03 / 3.97 |
| Stale position | 0/120 | 0/120 | 0/120 | 0/120 | 3.80 / 3.69 |
| Malicious witness | 0/120 | 0/120 | 0/120 | 0/120 | 4.07 / 3.89 |
| Colluding witnesses | **49/120** | **49/120** | **49/120** | **45/120** | 3.83 / 3.78 |
| Mixed packet loss | 0/120 | 0/120 | 0/120 | 0/120 | 4.00 / 2.94 |

**Interpretation of apparent gain:** The signed-false-health condition was reduced from 49/120 harmful episodes in greedy to 0/120 by **simple witness+age checks** as well as by the full gate. That is **not evidence of a new algorithm-specific gain**, and the idealized peer-witness channel supplies additional observations. In the collusion condition, the witness-informed policies still had 49/120 harmful episodes, showing the current gate can be defeated. The strict method reported fewer (45/120) only in part because some candidates lacked a complete witness set and were excluded; this does not establish lying-witness detection.

## Scientifically critical negative findings

1. **Motion ablation provides no incremental discrimination in this study.** Over all 960 episodes, `age_only` and `motion_age` selected exactly the same assignment pairs. Across all node decisions, both had 18,518 `bounded_observations_pass` and 1,882 `stale_health_or_position` outcomes. The added kinematic check never triggered a distinct rejection, so the pilot does **not** validate a novel motion-consistency contribution.
2. **Opportunistic full gate does not beat its simple witness+age control.** `witness_age` and `full_opportunistic` produced exactly identical assignment pairs in all 960 episodes. Each had 310 `signed_witness_conflict` node decisions. The full algorithm adds no empirically demonstrated benefit here.
3. **Lying independent witnesses are a major availability/accuracy vulnerability.** The one-conflicting-witness veto can exclude a truthful member. In `malicious_witness`, the gate assigned fewer tasks without addressing any resource-ineligible assignment hazard (all policies had 0/120 harmful episodes). Both colluding signers can corroborate the compromised subject and defeat that simple veto.
4. **Witness requirements impose availability cost.** Strict gate had 2,667 `independent_evidence_insufficient` node decisions across all episodes; in mixed loss, mean assigned task count fell from 4.00 (greedy) to 2.94 (strict).
5. **Quorum-loss behavior is not validated here.** Every one of the 960 episodes had a fresh quorum at the decision point. The scenario's moderate receiver loss and 3–9s delay relative to the 12s timeout never stressed a stale majority. Dedicated partition/quorum-availability experiments are missing.
6. **Threat budget needs condition-specific interpretation.** All 30 N=5 `colluding_witness` episodes used three compromised actors, exceeding that fleet's declared f=1. The other 90 collusion episodes at N=10/20/50 were at or below their declared f bounds; even this does not make their reported sensory data truthful.
7. **Uncertain ground truth/execution model.** The pilot's offline oracle has idealized simulator truth. There is no physical task completion, continuous motion or energy model, sensor provenance, task deadlines, measured decision latency or radio scheduling proof.
8. **Confirmatory claims not supported.** The 960 samples are independent randomized episodes within **fixed synthetic distributions**, but the pilot is an exploratory internally frozen design with no unseen holdout and no external preregistration. Reproducibility alone is not novel method proof.

## Observed archive provenance

The original validated CI artifact contains:

- `randomized_episodes.json`: **960** independently seeded receiver/truth records, condition and member behavior.
- `paired_methods.json`: **5,760** rows; **six methods applied to the same 960 episodes** (within-episode rows are correlated).
- `paired_method_metrics.csv`: **5,760** rows with the primary and utility metrics.
- `exploratory_stratum_summaries.json`: **192** rows = 4 fleet sizes × 8 scenarios × 6 methods, including per-size paired bootstrap risk-difference intervals (500 episode resamples).
- `manifest.json`: exact SHA-256 files, run/source metadata and explicit research-integrity limitations.

Archive file SHA-256 from original CI:

| Archive member | SHA-256 |
|---|---|
| randomized_episodes.json | `ba4c5ac398944f187eee0f135c688d29112beaef05ca48259796cfdca69c2824` |
| paired_methods.json | `b288c552c299f4639d82b853b952f1dceaa40e43af2c3ea2422f730928266df5` |
| paired_method_metrics.csv | `fcd958238e81ad7bbc269a90a48d8612e6b7d431df5bfc72c4b357404c63f752` |
| exploratory_stratum_summaries.json | `691e10842acf9299b509e148f214947cefac3a82a1fed409f537b50fde7e2fee` |

**Data lineage:** These are fresh Step 7 records, not the original 378 trials or the 52/40 handcrafted Step 4–6 diagnostic episodes. Signed envelopes, group encryption, fresh keys and synthetic peer witnesses exercise the authentic receive path but are **not reproduced from a deployed fleet**.

## Step 7 stage-gate decision

**Engineering GO:** the signed randomized pilot pipeline, seed pairing, independently sampled geometry/health/task states, archived metrics, CI and testable results are reproducible.

**Scientific NOVELTY NO-GO for the current full gate:** No incremental improvement over the simple witness+age control or age-only motion ablation is demonstrated. A paper whose main contribution asserts that the **current** full consistency gate improves over these straightforward existing protections would be misleading. Do not send such a superiority claim to a journal.

**Step 8 revised mandate:** Define a genuinely differentiated evidence aggregation mechanism before new outcome inspection (e.g. quorum-aware witness reliability under declared Byzantine and correlated-sensor assumptions), compare **equal-observation** baselines with matched message/computation budgets, include motion-adversarial trajectories that make kinematic ablation meaningful, and add no-quorum/partition cases and real dynamic task loss. Freeze different held-out seeds in advance. If no defensible incremental benefit appears, reposition as a transparent empirical failure/limitations paper, not an invented positive result.
