"""Step 8 median-fusion, signed witness attacks and heldout trace contracts."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from swarm_consistency_gate import ConsistencyPolicy, sign_witness, consistency_gated_allocate
from swarm_mesh import HealthReport, SwarmIdentity
from swarm_robust_witness_gate import RobustWitnessPolicy, robust_witness_allocate
from swarm_robust_holdout import (
    SCENARIOS, POLICIES, DEV_ROOT, HOLDOUT_ROOT, episode_seed,
    _run_allocation, run_case, run_study, summarize, write_evidence,
)
from swarm_independent_pilot import _generate_episode


class QuorumMedianWitnessTests(unittest.TestCase):
    def setUp(self):
        self.ids={i:SwarmIdentity(i) for i in range(1,6)}
        self.roster={i:key.public_bytes() for i,key in self.ids.items()}
        self.positions={1:(50.,0.,10.),2:(0.,0.,10.),
                        3:(100.,0.,10.),4:(120.,0.,10.),5:(140.,0.,10.)}
        self.health={i:HealthReport(90.,100.,95.) for i in self.ids}
        self.tasks={"inspect":(1.,0.,10.)}
        self.now=1000.

    def claim(self,reporter,subject=2,health=None,epoch=1,now=1000.):
        return sign_witness(
            self.ids[reporter],subject_id=subject,epoch=epoch,observed_at=now,
            health=health or self.health[subject])

    def run_robust(self,witnesses,prior=None,positions=None,policy=None):
        return robust_witness_allocate(
            positions=positions or self.positions,health=self.health,
            health_seen_at={i:self.now for i in self.ids},
            position_seen_at={i:self.now for i in self.ids},
            now=self.now,tasks=self.tasks,roster=self.roster,epoch=1,
            witnesses=witnesses,policy=policy or RobustWitnessPolicy(),
            previous_positions=prior,
        )

    def test_one_signed_malicious_outlier_is_not_unilateral_veto(self):
        three=[
            self.claim(3,health=HealthReport(0.,0.,0.)),
            self.claim(4),self.claim(5),
        ]
        witnesses={subject:[
            self.claim(reporter,subject=subject)
            for reporter in self.ids if reporter!=subject][:3]
            for subject in self.ids}
        witnesses[2]=three
        old=consistency_gated_allocate(
            positions=self.positions,health=self.health,
            health_seen_at={i:self.now for i in self.ids},
            position_seen_at={i:self.now for i in self.ids},
            now=self.now,tasks=self.tasks,roster=self.roster,epoch=1,
            witnesses=witnesses,
            policy=ConsistencyPolicy(min_health_witnesses=3))
        new=self.run_robust(witnesses)
        self.assertEqual(old["decisions"][2]["reason"],"signed_witness_conflict")
        self.assertEqual(new["decisions"][2]["reason"],"robust_median_consistent")
        self.assertEqual(new["decisions"][2]["health_witnesses"],3)
        self.assertTrue(new["allocations"][2])

    def test_majority_honest_witnesses_reject_false_self_health(self):
        self.health[2]=HealthReport(99.,100.,99.)
        good=HealthReport(15.,60.,40.)
        witnesses={2:[self.claim(i,health=good) for i in (3,4,5)]}
        result=self.run_robust(witnesses)
        self.assertEqual(result["decisions"][2]["action"],"REJECT")
        self.assertEqual(result["decisions"][2]["reason"],
                         "robust_witness_median_conflict")
        self.assertFalse(result["allocations"].get(2))

    def test_two_colluding_witnesses_defeat_three_claim_median(self):
        self.health[2]=HealthReport(99.,100.,99.)
        honest=HealthReport(15.,60.,40.)
        witnesses={2:[
            self.claim(3),self.claim(4),self.claim(5,health=honest),
        ]}
        result=self.run_robust(witnesses)
        self.assertEqual(result["decisions"][2]["action"],"ACCEPT")
        self.assertTrue(result["allocations"][2])
        self.assertEqual(result["policy"]["assumed_faulty_witnesses"],1)

    def test_missing_duplicate_tampered_and_old_epoch_cannot_inflate_quorum(self):
        correct=self.claim(3)
        duplicate=self.claim(3)
        tampered=replace(self.claim(4),health=HealthReport(0.,0.,0.))
        old_epoch=self.claim(5,epoch=0)
        result=self.run_robust({
            2:[correct,duplicate,tampered,old_epoch]})
        self.assertEqual(result["decisions"][2]["health_witnesses"],1)
        self.assertEqual(result["decisions"][2]["action"],"REQUEST_FRESH_EVIDENCE")

    def test_equivocating_signer_is_excluded(self):
        correct=self.claim(3)
        contradictory=self.claim(3,health=HealthReport(0.,0.,0.))
        result=self.run_robust({
            2:[correct,contradictory,self.claim(4),self.claim(5)]})
        self.assertEqual(result["decisions"][2]["health_witnesses"],2)
        self.assertEqual(result["decisions"][2]["equivocating_sources"],[3])
        self.assertEqual(result["decisions"][2]["action"],"REQUEST_FRESH_EVIDENCE")

    def test_inadmissible_quorum_policy_fails(self):
        for kwargs in ({"health_witness_quorum":2,"assumed_faulty_witnesses":1},
                       {"health_witness_quorum":0},
                       {"health_tolerance_pct":float("nan")}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                RobustWitnessPolicy(**kwargs)


class HeldoutResearchTraceTests(unittest.TestCase):
    def test_motion_jump_is_a_real_counterexample_to_age_only(self):
        changes=0
        for index in range(4):
            seed=episode_seed(DEV_ROOT,5,"motion_jump",index)
            obs,_=_generate_episode(n=5,scenario="motion_jump",
                                    seed=seed,witness_count=3)
            aged=_run_allocation(obs,"age_only")
            motion=_run_allocation(obs,"motion_age")
            if any(x["reason"]=="implausible_position_jump"
                   for x in motion["decisions"].values()):
                changes+=1
            self.assertEqual(len(obs["witnesses"]),5)
        self.assertGreater(changes,0)

    def test_quorum_partition_blocks_all_policies(self):
        src,records=run_case(
            n=5,scenario="quorum_partition",
            seed=episode_seed(DEV_ROOT,5,"quorum_partition",0))
        self.assertFalse(src["quorum_available"])
        self.assertTrue(src["certified_leader"])
        self.assertTrue(all(record["tasks_assigned"]==0 for record in records))
        self.assertEqual({x["method"] for x in records},set(POLICIES))

    def test_one_episode_same_seed_replays_without_shared_truth_leakage(self):
        seed=episode_seed(DEV_ROOT,10,"malicious_witness",0)
        first,rows=run_case(n=10,scenario="malicious_witness",seed=seed)
        second,again=run_case(n=10,scenario="malicious_witness",seed=seed)
        self.assertEqual(first,second)
        self.assertEqual(rows,again)
        self.assertEqual(first["scenario"],"malicious_witness")
        self.assertTrue(all(record["synthetic_only"] for record in rows))

    def test_dedicated_dev_and_heldout_roots_do_not_overlap(self):
        dev={episode_seed(DEV_ROOT,n,s,i)
             for n in (5,10,20,50) for s in SCENARIOS for i in range(8)}
        holdout={episode_seed(HOLDOUT_ROOT,n,s,i)
                 for n in (5,10,20,50) for s in SCENARIOS for i in range(20)}
        self.assertEqual(len(dev),288)
        self.assertEqual(len(holdout),720)
        self.assertFalse(dev & holdout)

    def test_paired_study_manifest_integrity_and_no_data_dropping(self):
        settings=dict(sizes=(5,),scenarios=(
            "benign","malicious_witness","colluding_witness",
            "motion_jump","quorum_partition"),trials=2,root=DEV_ROOT)
        src,rows=run_study(**settings)
        self.assertEqual(len(src),10)
        self.assertEqual(len(rows),10*len(POLICIES))
        self.assertEqual(set(POLICIES),{row["method"] for row in rows})
        self.assertEqual(
            len({(x["scenario"],x["seed"]) for x in src}),len(src))
        summaries=summarize(rows)
        self.assertEqual(len(summaries),5*len(POLICIES))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            manifest=write_evidence(
                path,src,rows,summaries,sample_type="development",root=DEV_ROOT)
            self.assertFalse(manifest["scientific_novelty_proven"])
            self.assertFalse(manifest["real_radio_link"])
            for name,sha in manifest["sha256"].items():
                self.assertEqual(
                    hashlib.sha256((path/name).read_bytes()).hexdigest(),sha)
            self.assertEqual(json.loads((path/"episodes.json").read_text()),src)

    def test_incomplete_and_duplicate_paired_rows_rejected(self):
        src,rows=run_study(
            sizes=(5,),scenarios=("benign",),trials=1)
        with self.assertRaises(ValueError):
            summarize(rows[:-1])
        with self.assertRaises(ValueError):
            summarize(rows+[rows[0]])

    def test_invalid_settings_fail(self):
        for p in (
            {"sizes":(4,)},{"sizes":(5,5)},
            {"scenarios":("unknown",)},{"trials":0},
        ):
            with self.subTest(p=p),self.assertRaises(ValueError):
                run_study(**p)


if __name__=="__main__":
    unittest.main()
