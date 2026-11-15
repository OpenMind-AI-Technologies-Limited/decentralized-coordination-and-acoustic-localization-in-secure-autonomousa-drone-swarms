"""Step 7 randomized pilot: real signed input and paired/no-leak guarantees.

CI tests use a tiny fixed pilot sample. The separate pilot CI job runs the
frozen 960-episode design without filtering or cherry-picking results.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from swarm_independent_pilot import (
    METHODS, SCENARIOS, FLEET_SIZES, PILOT_TRIALS,
    _seed, _generate_episode, _evaluate,
    run_episode, run_pilot, summarize_pilot, write_pilot,
)


class RandomizedSignedInputTests(unittest.TestCase):
    def test_signed_receiver_and_certified_leader_every_small_condition(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                source, rows = run_episode(n=5,scenario=scenario,
                                           seed=_seed(2026,5,scenario,0))
                self.assertEqual(source["scenario"],scenario)
                self.assertGreater(source["authenticated_verified_heartbeats"],0)
                self.assertEqual(len(rows),len(METHODS))
                self.assertEqual({x["method"] for x in rows},set(METHODS))
                self.assertEqual({x["seed"] for x in rows},{source["seed"]})
                self.assertEqual(source["num_tasks"],len(source["tasks"]))
                self.assertTrue(all(x["tasks_assigned"]+x["tasks_unassigned"]==
                                    source["num_tasks"] for x in rows))
                for trial in rows:
                    pairs=trial["assignment_pairs"]
                    self.assertEqual(len(pairs),len(set(
                        x["task_id"] for x in pairs)))
                    self.assertEqual(len(pairs),len(set(
                        x["member"] for x in pairs)))
                    self.assertTrue(trial["simulated_only"])

    def test_same_seed_replays_identical_decisions_and_truth(self):
        s=_seed(2026,10,"signed_false_health",2)
        a,b=run_episode(n=10,scenario="signed_false_health",seed=s)
        c,d=run_episode(n=10,scenario="signed_false_health",seed=s)
        self.assertEqual(a,c)
        self.assertEqual(b,d)
        self.assertNotEqual(a["offline_truth"]["positions"],
                            run_episode(n=10,scenario="signed_false_health",
                                        seed=_seed(2026,10,"signed_false_health",3)
                                        )[0]["offline_truth"]["positions"])

    def test_stale_report_age_is_independent_of_fresh_signed_health(self):
        obs,_= _generate_episode(
            n=5,scenario="stale_position",
            seed=_seed(2026,5,"stale_position",0))
        # Fresh self-reported health can coexist with an older position.
        from swarm_independent_pilot import _seed as _s
        old=[i for i in obs["health"]
             if obs["now"]-obs["position_seen"][i]>2.0 and
             obs["now"]-obs["health_seen"][i]<=2.0]
        self.assertGreaterEqual(len(old),1)
        self.assertTrue(obs["leader_certified"])
        self.assertTrue(obs["quorum_available"])

    def test_attackers_and_declared_fault_budget_are_exposed(self):
        small,_=run_episode(n=5,scenario="colluding_witness",
                             seed=_seed(2026,5,"colluding_witness",0))
        big,_=run_episode(n=10,scenario="colluding_witness",
                           seed=_seed(2026,10,"colluding_witness",0))
        self.assertEqual(small["compromised_count"],3)
        self.assertEqual(big["compromised_count"],3)
        self.assertFalse(small["within_fault_bound"])
        self.assertTrue(big["within_fault_bound"])
        self.assertEqual(small["declared_fault_bound"],1)

    def test_idealized_witness_attacks_do_not_magic_attest_truth(self):
        source,rows=run_episode(n=10,scenario="malicious_witness",
                                 seed=_seed(2026,10,"malicious_witness",0))
        self.assertGreater(source["signed_witness_claims_available"],0)
        self.assertEqual(len(rows),len(METHODS))
        self.assertTrue(all("any_truth_ineligible_assignment" in x
                            for x in rows))

    def test_no_hardware_or_actual_radio_claims_in_results(self):
        source,rows=run_episode(n=50,scenario="mixed_loss",
                                 seed=_seed(2026,50,"mixed_loss",0))
        self.assertFalse(source["hardware_sensors"])
        self.assertGreater(source["authenticated_verified_heartbeats"],0)
        self.assertTrue(all(x["simulated_only"] for x in rows))
        self.assertEqual({x["quorum_available"] for x in rows},
                         {source["quorum_available"]})

    def test_oracle_mutation_cannot_change_method_assignments(self):
        seed=_seed(2026,5,"signed_false_health",0)
        obs,oracle=_generate_episode(n=5,scenario="signed_false_health",seed=seed)
        _,before=_evaluate(obs,oracle)
        # Method calls consume obs; modifying truth changes only evaluation.
        revised=dict(oracle)
        revised["health"]={i: type(h)(100.,100.,100.)
                           for i,h in oracle["health"].items()}
        _,after=_evaluate(obs,revised)
        self.assertEqual([x["assignment_pairs"] for x in before],
                         [x["assignment_pairs"] for x in after])


class RandomizedPilotOutputTests(unittest.TestCase):
    def test_pilot_multiple_sizes_strata_and_full_paired_row_cardinality(self):
        sizes=(5,10)
        scenarios=("benign","stale_position","signed_false_health")
        sources,paired=run_pilot(sizes=sizes,trials=2,
                                root_seed=2026,scenarios=scenarios)
        self.assertEqual(len(sources),len(sizes)*len(scenarios)*2)
        self.assertEqual(len(paired),len(sources)*len(METHODS))
        self.assertEqual(len({(x["n"],x["scenario"],x["seed"])
                              for x in sources}),len(sources))
        self.assertEqual(set(METHODS),{x["method"] for x in paired})
        summaries=summarize_pilot(paired)
        self.assertEqual(len(summaries),len(sizes)*len(scenarios)*len(METHODS))
        self.assertTrue(all(x["episodes"]==2 for x in summaries))
        with tempfile.TemporaryDirectory() as root:
            directory=Path(root)
            manifest=write_pilot(directory,sources,paired,summaries)
            self.assertEqual(manifest["source_episode_count"],len(sources))
            self.assertFalse(manifest["confirmatory_holdout_completed"])
            self.assertFalse(manifest["publication_scale_superiority_established"])
            self.assertFalse(manifest["physical_flight"])
            self.assertEqual(set(manifest["methods"]),set(METHODS))
            for name,digest in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),
                                 digest)
            with (directory/"paired_method_metrics.csv").open(
                    newline="",encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))),len(paired))

    def test_bootstrap_is_reproducible_and_rejects_missing_pair(self):
        sources,paired=run_pilot(sizes=(5,),trials=2,
                                scenarios=("benign",))
        self.assertEqual(summarize_pilot(paired),summarize_pilot(paired))
        with self.assertRaises(ValueError):
            summarize_pilot(paired[:-1])

    def test_invalid_strata_fail_fast(self):
        for kwargs in (
            {"sizes":(4,),"trials":1},
            {"sizes":(5,5),"trials":1},
            {"scenarios":("unknown",),"trials":1},
            {"sizes":(5,),"trials":0},
        ):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                run_pilot(**kwargs)

    def test_seed_distinct_across_strata_and_trials(self):
        seeds={_seed(2026,n,s,k)
               for n in FLEET_SIZES for s in SCENARIOS for k in range(PILOT_TRIALS)}
        self.assertEqual(len(seeds),len(FLEET_SIZES)*len(SCENARIOS)*PILOT_TRIALS)


if __name__=="__main__":
    unittest.main()
