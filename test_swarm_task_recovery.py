"""Step 6 task recovery security/logic contracts and real certified audit path.

These tests assert local coordinator intent safety, NOT exactly-once execution
by physically isolated drones or truthful testimony from compromised owners.
"""
import base64
from dataclasses import replace
import unittest

from drone import Drone, Position
from consistency_gated_step2_probe import ManualClock
from mesh_simulation import DroneMeshSimulation
from swarm_mesh import HealthReport, InMemoryMesh, SwarmIdentity
from swarm_task_recovery import (
    RecoveryPolicy, TaskRecoveryLedger, sign_task_receipt,
)


class TaskRecoveryLedgerTests(unittest.TestCase):
    def setUp(self):
        self.identities = {i: SwarmIdentity(i) for i in range(1, 6)}
        self.roster = {i: ident.public_bytes()
                       for i, ident in self.identities.items()}
        self.ledger = TaskRecoveryLedger(
            "mission-step6", self.roster,
            policy=RecoveryPolicy(lease_s=5, receipt_max_delay_s=20))
        self.xyz = {1: (60.,0.,10.), 2:(0.,0.,10.),
                    3:(100.,0.,10.),4:(120.,0.,10.),5:(140.,0.,10.)}
        self.health = {i:HealthReport(90.,100.,95.)
                       for i in self.xyz}
        self.ledger.register({"inspect":(1.,0.,10.)},now=1000.)

    def plan(self, *, now=1000., epoch=1, quorum=True, allowed=None):
        return self.ledger.preview(
            now=now, epoch=epoch, leader_id=1, quorum_verified=quorum,
            positions=self.xyz, health=self.health, allowed_members=allowed)

    def assign(self, **kwargs):
        preview = self.plan(**kwargs)
        self.ledger.commit(preview, quorum_verified=True)
        return preview

    def receipt(self, *, actor=2, version=1, epoch=1, action="STOPPED",
                observed=1001., mission="mission-step6"):
        return sign_task_receipt(
            self.identities[actor], mission_id=mission,
            task_id="inspect", lease_version=version, authority_epoch=epoch,
            action=action, observed_at=observed)

    def test_initial_lease_and_idempotent_replanning(self):
        first = self.assign()
        self.assertEqual(first["proposed"][0]["owner_id"],2)
        self.assertEqual(first["proposed"][0]["lease_version"],1)
        self.assertFalse(first["broadcast_commands_issued"])
        again=self.plan(now=1001.,epoch=1)
        self.assertEqual(again["proposed"],[])
        self.assertEqual(again["active_lease_count"],1)
        self.assertTrue(self.ledger.verify_local_chain())

    def test_expired_unconfirmed_is_hold_not_duplicate_assignment(self):
        self.assign()
        proposed=self.plan(now=1007.,epoch=2,allowed={1,3,4,5})
        self.assertEqual(proposed["status"],"HOLD_UNCONFIRMED")
        self.assertEqual(proposed["expired_unconfirmed"],["inspect"])
        self.assertEqual(proposed["proposed"],[])
        state=self.ledger.snapshot(now=1007.)["tasks"]["inspect"]
        self.assertEqual(state["status"],"LEASED")
        self.assertTrue(state["expired_unconfirmed"])

    def test_signed_stopped_claim_allows_single_new_version(self):
        self.assign()
        accepted=self.ledger.receive(self.receipt(),now=1001.)
        self.assertEqual(accepted["state"],"PENDING")
        second=self.assign(now=1002.,epoch=2,allowed={1,3,4,5})
        self.assertEqual(second["proposed"][0]["owner_id"],1)
        self.assertEqual(second["proposed"][0]["lease_version"],2)
        self.assertEqual(second["proposed"][0]["authority_epoch"],2)
        self.assertEqual(len(self.plan(now=1002.5,epoch=2)["proposed"]),0)
        with self.assertRaises(PermissionError):
            self.ledger.receive(self.receipt(),now=1003.)
        self.assertTrue(self.ledger.verify_local_chain())

    def test_completion_is_terminal_even_with_new_epoch(self):
        self.assign()
        self.ledger.receive(self.receipt(action="COMPLETED"),now=1001.)
        later=self.plan(now=1008.,epoch=4)
        self.assertEqual(later["proposed"],[])
        self.assertEqual(self.ledger.snapshot(now=1008.)["tasks"]["inspect"]["status"],
                         "COMPLETED")

    def test_quorum_loss_prevents_planning_and_state_mutation(self):
        original=self.ledger.snapshot(now=1000.)
        with self.assertRaises(PermissionError):
            self.plan(quorum=False)
        self.assertEqual(self.ledger.snapshot(now=1000.),original)
        proposed=self.plan()
        with self.assertRaises(PermissionError):
            self.ledger.commit(proposed,quorum_verified=False)
        self.assertEqual(self.ledger.snapshot(now=1000.),original)

    def test_preview_can_only_commit_exact_version_unchanged(self):
        proposed=self.plan()
        bad=dict(proposed)
        bad["proposed"]=[dict(proposed["proposed"][0],owner_id=3)]
        with self.assertRaises(ValueError):
            self.ledger.commit(bad,quorum_verified=True)
        self.ledger.commit(proposed,quorum_verified=True)
        with self.assertRaises(ValueError):
            self.ledger.commit(proposed,quorum_verified=True)

    def test_signed_receipt_must_match_own_key_id_version_and_epoch(self):
        self.assign()
        for variant in (
            self.receipt(actor=1),
            self.receipt(version=2),
            self.receipt(epoch=0),
            self.receipt(mission="mission-elsewhere"),
            self.receipt(observed=998.),
            self.receipt(observed=1025.),
            replace(self.receipt(),action="COMPLETED"),
            replace(self.receipt(),signature_b64="invalid!"),
        ):
            with self.subTest(variant=variant), self.assertRaises(
                    (PermissionError, ValueError)):
                self.ledger.receive(variant,now=1002.)
        self.assertEqual(self.ledger.snapshot(now=1002.)["tasks"]["inspect"]["status"],
                         "LEASED")

    def test_monotonic_time_epoch_fencing_and_immutable_task_ids(self):
        self.assign()
        self.ledger.receive(self.receipt(),now=1001.)
        self.assign(now=1002.,epoch=3,allowed={1,3,4,5})
        with self.assertRaises(PermissionError):
            self.plan(now=1003.,epoch=2)
        with self.assertRaises(ValueError):
            self.ledger.register({"inspect":(40.,0.,10.)},now=1003.)
        with self.assertRaises(ValueError):
            self.ledger.register({"new":(1.,0.,10.)},now=999.)
        # Calling register twice is idempotent.
        self.assertEqual(self.ledger.register({"inspect":(1.,0.,10.)},
                                              now=1003.)["new"],[])

    def test_owner_signature_is_not_attestation_of_physical_stop(self):
        self.assign()
        # Malicious-but-registered drone can lie when signing STOPPED.
        # Ledger accepts the signature but labels it acknowledgment only.
        status=self.ledger.receive(self.receipt(),now=1001.)
        self.assertTrue(status["acknowledgment_only"])
        self.assertFalse(self.ledger.snapshot(now=1001.)["hardware_execution_attested"])

    def test_hash_chain_detects_local_record_modification(self):
        self.assign()
        self.assertTrue(self.ledger.verify_local_chain())
        self.ledger.events[0]["data"]["task_ids"].append("forged")
        self.assertFalse(self.ledger.verify_local_chain())

    def test_multiple_tasks_no_colliding_active_owner_when_cap_one(self):
        ledger=TaskRecoveryLedger("many",self.roster)
        ledger.register({"one":(1.,0.,10.),"two":(4.,0.,10.),
                         "three":(6.,0.,10.)},now=1000.)
        p=ledger.preview(now=1000.,epoch=1,leader_id=1,quorum_verified=True,
                         positions=self.xyz,health=self.health)
        self.assertEqual(len(p["proposed"]),3)
        owners=[x["owner_id"] for x in p["proposed"]]
        self.assertEqual(len(owners),len(set(owners)))
        ledger.commit(p,quorum_verified=True)
        self.assertEqual(ledger.preview(now=1000.5,epoch=1,leader_id=1,
                                        quorum_verified=True,positions=self.xyz,
                                        health=self.health)["proposed"],[])


class CertifiedRecoveryPlanningTests(unittest.TestCase):
    def setUp(self):
        coord={1:(60.,0.),2:(0.,0.),3:(100.,0.),4:(130.,0.)}
        self.drones={i:Drone(i,Position(*p,0.)) for i,p in coord.items()}
        self.sim=DroneMeshSimulation(self.drones,heartbeat_timeout_s=5.)
        self.clock=ManualClock()
        for node in self.sim.nodes.values():
            node.clock=self.clock
            node.channel.clock=self.clock
        self.channel=InMemoryMesh(list(self.sim.nodes.values()))
        for i in sorted(self.sim.nodes):
            xyz=(*coord[i],10.)
            msg=self.sim.nodes[i].publish_health(
                HealthReport(90.,100.,95.),xyz)
            self.channel.broadcast(i,msg)
        votes=[(i,node.begin_election(candidate=1)) for i,node in
               sorted(self.sim.nodes.items())]
        for i,packet in votes:
            self.channel.broadcast(i,packet)
        self.assertEqual(self.sim.leader(),1)
        self.ledger=TaskRecoveryLedger("integrated",
                                      self.sim.nodes[1].roster)
        self.ledger.register({"inspection":(1.,0.,10.)},now=self.clock.now)

    def tearDown(self):
        self.sim.stop()
        for drone in self.drones.values():
            if drone.running:
                drone.stop()

    def test_audited_intent_only_and_stopped_replan(self):
        before=len(self.sim.nodes[1].delivered_commands)
        plan=self.sim.plan_recovery_tasks(self.ledger)
        self.assertEqual(plan["leader"],1)
        self.assertEqual(len(plan["committed"]),1)
        self.assertEqual(plan["committed"][0]["owner_id"],2)
        self.assertIsNotNone(plan["quorum_audit"])
        self.assertEqual(len(self.sim.nodes[1].delivered_commands),before)
        self.assertFalse(plan["broadcast_commands_issued"])
        self.assertEqual(self.sim.plan_recovery_tasks(self.ledger)["committed"],[])
        self.clock.now+=1
        receipt=sign_task_receipt(
            self.sim._identities[2],mission_id="integrated",
            task_id="inspection",lease_version=1,authority_epoch=1,
            action="STOPPED",observed_at=self.clock.now)
        self.ledger.receive(receipt,now=self.clock.now)
        # Member 2 correctly reports degraded health before reassignment.
        degraded=self.sim.nodes[2].publish_health(
            HealthReport(10.,60.,30.),(0.,0.,10.))
        self.channel.broadcast(2,degraded)
        plan2=self.sim.plan_recovery_tasks(self.ledger)
        self.assertEqual(plan2["committed"][0]["owner_id"],1)
        self.assertEqual(plan2["committed"][0]["lease_version"],2)
        self.assertEqual(len(self.sim.nodes[1].delivered_commands),before)

    def test_denied_quorum_does_not_change_recovery_ledger(self):
        empty=DroneMeshSimulation(
            {i:Drone(i,Position(float(i),0.,0.))
             for i in (1,2,3,4)})
        try:
            inactive=TaskRecoveryLedger("denied",
                                        empty.nodes[1].roster)
            inactive.register({"test":(1.,0.,10.)},now=0.)
            before=inactive.snapshot(now=0.)
            with self.assertRaises(PermissionError):
                empty.plan_recovery_tasks(inactive)
            self.assertEqual(before,inactive.snapshot(now=0.))
        finally:
            empty.stop()


if __name__ == "__main__":
    unittest.main()
