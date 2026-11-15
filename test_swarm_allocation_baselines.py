"""Step 5 comparator correctness and equal-information replay tests.

Paper statistics are NOT inferred from these small deterministic fixtures.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest

from swarm_allocation_baselines import (
    ComparableProblem, cbaa_single_comparable, cbba_static_comparable,
    compare_allocators, greedy_comparable, hungarian_comparable,
)
from swarm_baseline_comparison import (
    FILTERS, COMPARATORS, compare_one_fault_case, run_comparison_suite,
    write_comparison,
)
from swarm_mesh import HealthReport
from swarm_telemetry_faults import FaultCase, run_fault_case
from swarm_tasks import allocate_tasks


class ComparableAllocationTests(unittest.TestCase):
    def setUp(self):
        self.health = {i: HealthReport(90., 100., 95.) for i in range(1, 4)}
        self.positions = {
            1: (0.2, 0., 10.), 2: (-0.3, 0., 10.),
            3: (30., 0., 10.),
        }
        self.tasks = {
            "a": (0., 0., 10.),
            "b": (10., 0., 10.),
            "c": (25., 0., 10.),
        }

    def problem(self, *, tasks=None, positions=None, health=None, cap=1):
        return ComparableProblem.build(
            self.positions if positions is None else positions,
            self.health if health is None else health,
            self.tasks if tasks is None else tasks, max_per_node=cap)

    @staticmethod
    def assignments(result):
        return [(node, t) for node, items in result["allocations"].items()
                for t, _ in items]

    def test_greedy_is_original_code_on_identical_observations(self):
        p = self.problem()
        result = greedy_comparable(p)
        self.assertEqual(result["allocations"],
                         allocate_tasks(p.positions, p.health, p.tasks))

    def test_hungarian_improves_on_greedy_counterexample(self):
        p = self.problem(tasks={k:self.tasks[k] for k in ("a", "b")},
                         positions={i:self.positions[i] for i in (1,2)},
                         health={i:self.health[i] for i in (1,2)})
        greedy = greedy_comparable(p)
        optimized = hungarian_comparable(p)
        self.assertEqual(greedy["tasks_assigned"], 2)
        self.assertEqual(optimized["tasks_assigned"], 2)
        self.assertLess(optimized["objective_total_cost"],
                        greedy["objective_total_cost"])
        self.assertEqual(set(self.assignments(optimized)), {(2,"a"),(1,"b")})

    def test_hungarian_equal_to_bruteforce_optimum_small_problem(self):
        p = self.problem()
        optimized = hungarian_comparable(p)
        # Small independent exhaustive benchmark: all 3! bijections.
        exhaustive = min(sum(p.cost(n,t) for n,t in zip(permutation, sorted(p.tasks)))
                         for permutation in itertools.permutations(sorted(p.positions)))
        self.assertAlmostEqual(optimized["objective_total_cost"], exhaustive)
        self.assertEqual(optimized["tasks_assigned"], 3)

    def test_maximum_cardinality_with_insufficient_nodes_and_capacity(self):
        tasks = {f"job-{i}": (i*3., 0., 10.) for i in range(6)}
        problem = self.problem(tasks=tasks,cap=2)
        h = hungarian_comparable(problem)
        b = cbba_static_comparable(problem)
        self.assertEqual(h["tasks_assigned"], 6)
        self.assertEqual(h["unassigned"], [])
        self.assertEqual(b["tasks_assigned"], 6)
        self.assertEqual(b["unassigned"], [])
        for result in (h, b):
            self.assertEqual(len({task for _,task in self.assignments(result)}),6)
            self.assertTrue(all(len(v)<=2 for v in result["allocations"].values()))

    def test_eligibility_and_empty_tasks_apply_identically(self):
        bad = dict(self.health)
        bad[2]=HealthReport(10., 100., 95.)
        p = self.problem(health=bad)
        result=compare_allocators(p)
        for value in result.values():
            self.assertNotIn(2, value["allocations"])
            self.assertEqual(len({task for _,task in self.assignments(value)}),
                             value["tasks_assigned"])
        empty = self.problem(tasks={})
        for value in compare_allocators(empty).values():
            self.assertEqual(value["tasks_assigned"],0)
            self.assertEqual(value["unassigned"],[])

    def test_cbaa_is_single_task_only_and_cbba_static_is_not_full_cbba(self):
        p = self.problem()
        cbaa = cbaa_single_comparable(p)
        self.assertEqual(cbaa["tasks_assigned"],3)
        self.assertGreater(cbaa["logical_bid_messages"],0)
        self.assertGreater(cbaa["consensus_rounds"],0)
        with self.assertRaises(ValueError):
            cbaa_single_comparable(self.problem(cap=2))
        bundle=cbba_static_comparable(self.problem(cap=2))
        self.assertEqual(bundle["algorithm"],"cbba_static_additive_specialization")
        self.assertIn("perfect_synchronous_all_to_all",
                      bundle["communication_model"])

    def test_invalid_input_and_unrecognized_methods_fail_closed(self):
        with self.assertRaises(ValueError):
            self.problem(positions={1:(math.nan,0.,10.)},
                         health={1:self.health[1]})
        with self.assertRaises(ValueError):
            self.problem(tasks={"bad": (1.,0.,101.)})
        with self.assertRaises(ValueError):
            self.problem(cap=0)
        with self.assertRaises(ValueError):
            compare_allocators(self.problem(),methods=("fictitious_full_cbba",))

    def test_larger_randomized_matches_have_no_overcapacity_or_duplicates(self):
        # Separate generated problem family, not a Step 4 fixed-scene replay.
        import random
        for seed in range(12):
            rng=random.Random(seed)
            n=5+seed%6
            coords={i:(rng.uniform(-80,80),rng.uniform(-80,80),10.)
                    for i in range(1,n+1)}
            health={i:HealthReport(rng.uniform(40,100),95.,90.)
                    for i in coords}
            targets={f"t{j}":(rng.uniform(-80,80),rng.uniform(-80,80),10.)
                     for j in range(n+3)}
            for cap in (1,2):
                problem=ComparableProblem.build(coords,health,targets,max_per_node=cap)
                comps = {
                    "greedy":greedy_comparable(problem),
                    "hungarian":hungarian_comparable(problem),
                    "cbba_static":cbba_static_comparable(problem),
                }
                if cap == 1:
                    comps["cbaa"] = cbaa_single_comparable(problem)
                for result in comps.values():
                    assignments=self.assignments(result)
                    self.assertEqual(len(assignments),
                                     min(len(targets),len(problem.positions)*cap))
                    self.assertEqual(len({t for _,t in assignments}),len(assignments))
                    self.assertTrue(all(len(a)<=cap
                                        for a in result["allocations"].values()))
                h=comps["hungarian"]
                self.assertLessEqual(h["objective_total_cost"],
                                     comps["greedy"]["objective_total_cost"]+1e-8)
                self.assertLessEqual(h["objective_total_cost"],
                                     comps["cbba_static"]["objective_total_cost"]+1e-8)


class FairPairedReplayTests(unittest.TestCase):
    def test_identical_signed_snapshot_used_for_each_allocator(self):
        f=run_fault_case(FaultCase("stale_position",nodes=5,seed=17))
        records=compare_one_fault_case(f)
        self.assertEqual(len(records),len(FILTERS)*len(COMPARATORS))
        for cohort in FILTERS:
            rows=[x for x in records if x["information_cohort"]==cohort]
            self.assertEqual({x["task_count"] for x in rows},{3})
            self.assertEqual(len({x["members_accepted"] for x in rows}),1)
            self.assertEqual({x["optimizer"] for x in rows},set(COMPARATORS))
            self.assertEqual({x["source"] for x in rows},
                             {"Step4_signed_authentication_receiver_snapshot"})
            hung=next(x for x in rows if x["optimizer"]=="hungarian")
            for x in rows:
                self.assertEqual(x["tasks_assigned"],hung["tasks_assigned"])
                self.assertLessEqual(hung["reported_cost"],x["reported_cost"]+1e-8)
        self.assertEqual(
            {x["members_accepted"] for x in records
             if x["information_cohort"]=="age_motion_gate"}, {4})

    def test_false_health_cannot_be_deduced_by_age_filter(self):
        f=run_fault_case(FaultCase("signed_false_health",nodes=5,seed=19))
        records=compare_one_fault_case(f)
        raw=[x for x in records if x["optimizer"]=="greedy" and
             x["information_cohort"]=="self_reports"][0]
        age=[x for x in records if x["optimizer"]=="greedy" and
             x["information_cohort"]=="age_motion_gate"][0]
        strict=[x for x in records if x["optimizer"]=="greedy" and
                x["information_cohort"]=="strict_synthetic_witness_gate"][0]
        self.assertEqual(raw["members_accepted"],age["members_accepted"])
        self.assertEqual(raw["pairs"],age["pairs"])
        self.assertEqual(strict["tasks_assigned"],0)
        self.assertEqual(strict["sensor_information_advantage"],
                         "idealized_peer_reports_possible")

    def test_default_runner_repeats_and_archive_hashes(self):
        args=dict(sizes=(5,),trials=1,seed=33,
                  scenarios=("healthy_control","stale_position",
                             "signed_false_health","honest_witnesses"))
        episodes,records=run_comparison_suite(**args)
        self.assertEqual(len(episodes),4)
        self.assertEqual(len(records),4*len(COMPARATORS)*len(FILTERS))
        again, again_rows=run_comparison_suite(**args)
        self.assertEqual(episodes,again)
        self.assertEqual(records,again_rows)
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            m=write_comparison(out,episodes,records)
            self.assertFalse(m["statistical_superiority_established"])
            self.assertTrue(m["offline_truth_never_in_optimizer_inputs"])
            self.assertTrue(m["cbba_static_specialization_not_full_cbba"])
            for file,expected in m["sha256"].items():
                self.assertEqual(hashlib.sha256((out/file).read_bytes()).hexdigest(),
                                 expected)
            with (out/"paired_baseline_metrics.csv").open(
                    newline="",encoding="utf-8") as file:
                self.assertEqual(len(list(csv.DictReader(file))),len(records))
            self.assertEqual(json.loads((out/"paired_baseline_trials.json").read_text()),
                             records)


if __name__=="__main__":
    unittest.main()
