"""Loopback-only demonstration of four independently electing mesh agents.

Uses synthetic telemetry and never opens a connection to flight hardware.
"""
import os
import time

from swarm_mesh import HealthReport, MeshNode, SwarmIdentity
from swarm_runtime import MeshRuntime
from swarm_transport import UdpPeerTransport


def wait_for(predicate, deadline_s=6.0):
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main():
    identities = [SwarmIdentity(i) for i in (1, 2, 3, 4)]
    roster = {identity.node_id: identity.public_bytes() for identity in identities}
    group_key = os.urandom(32)
    transports = [UdpPeerTransport(i.node_id, ("127.0.0.1", 0)) for i in identities]
    agents = []
    try:
        for transport in transports:
            transport.configure_peers({p.node_id: p.address for p in transports if p.node_id != transport.node_id})
        for index, identity in enumerate(identities):
            report = HealthReport(95 - 10 * index, 95, 90)
            position = (float(index * 20), 0.0, 10.0)
            agent = MeshRuntime(
                MeshNode(identity, roster, group_key, heartbeat_timeout_s=1.2),
                transports[index],
                health_provider=lambda h=report, p=position: (h, p),
                command_handler=lambda action, node=identity.node_id: print(f"Drone {node}: {action}"),
                heartbeat_interval_s=0.15,
                election_retry_s=0.7,
            )
            agents.append(agent)
            agent.start()
        if not wait_for(lambda: all(agent.node.leader == 1 for agent in agents)):
            raise RuntimeError("Initial election did not converge")
        print("Quorum-certified leader: Drone 1")
        agents[0].broadcast_action({
            "kind": "formation", "pattern": "v", "leader_position": [0, 0, 10],
            "heading": [1, 0], "spacing_m": 12,
        })
        time.sleep(0.3)
        print("Simulating Drone 1 crash...")
        agents[0].stop()
        if not wait_for(lambda: all(agent.node.leader == 2 for agent in agents[1:])):
            raise RuntimeError("Failover election did not converge")
        print("Replacement quorum-certified leader: Drone 2")
    finally:
        for agent in agents:
            agent.stop()
        for transport in transports:
            transport.close()


if __name__ == "__main__":
    main()
