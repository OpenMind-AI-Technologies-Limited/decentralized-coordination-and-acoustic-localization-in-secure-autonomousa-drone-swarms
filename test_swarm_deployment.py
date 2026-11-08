"""End-to-end isolated operating-system process tests for the loopback swarm."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from swarm_deployment import load_member, provision_members


def _free_port_block(count=4):
    for _ in range(35):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            first = probe.getsockname()[1]
        if first < 1024 or first + count >= 65000:
            continue
        sockets = []
        try:
            for port in range(first, first + count):
                item = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                item.bind(("127.0.0.1", port))
                sockets.append(item)
            return first
        except OSError:
            continue
        finally:
            for item in sockets:
                item.close()
    raise RuntimeError("Cannot reserve contiguous UDP ports")


class ProvisioningTests(unittest.TestCase):
    def test_bundles_are_member_scoped_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            members = provision_members(Path(tmp) / "fleet", 4, _free_port_block())
            self.assertEqual(len(members), 4)
            roster = []
            for i, directory in enumerate(members, 1):
                node, addresses, _, _ = load_member(directory)
                self.assertEqual(node.node_id, i)
                self.assertEqual(len(addresses), 4)
                self.assertEqual(node.quorum, 3)
                roster.append(node.roster)
            self.assertTrue(all(roster[0] == item for item in roster))
            with self.assertRaises(FileExistsError):
                provision_members(Path(tmp) / "fleet", 4, _free_port_block())

    def test_tampered_membership_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = provision_members(Path(tmp) / "fleet", 4, _free_port_block())[0]
            config = directory / "member.json"
            data = json.loads(config.read_text(encoding="utf-8"))
            data["roster"]["2"] = "00" * 32
            config.write_text(json.dumps(data), encoding="utf-8")
            if os.name == "posix":
                config.chmod(0o600)
            with self.assertRaises(ValueError):
                load_member(directory)

    def test_unknown_member_and_unsafe_port_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                provision_members(Path(tmp) / "fleet", 3, 34000)
            with self.assertRaises(ValueError):
                provision_members(Path(tmp) / "fleet", 4, 65535)


class SeparateProcessTests(unittest.TestCase):
    def _read_status(self, directory):
        path = directory / "status.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _wait(self, predicate, timeout=14.0):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if predicate():
                return True
            time.sleep(0.08)
        return False

    def test_four_os_processes_elect_failover_and_rejoin(self):
        processes = []
        with tempfile.TemporaryDirectory() as tmp:
            members = provision_members(Path(tmp) / "fleet", 4, _free_port_block())
            script = str(Path(__file__).resolve().parent / "swarm_deployment.py")

            def start_node(node_id):
                proc = subprocess.Popen(
                    [sys.executable, "-u", script, "run", "--node",
                     str(members[node_id - 1]), "--duration", "38"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                processes.append(proc)
                return proc

            def converged(node_ids, leader):
                return all(
                    (state := self._read_status(members[i - 1])).get("leader") == leader
                    and state.get("has_certificate") is True
                    and state.get("fresh_quorum") is True
                    for i in node_ids
                )
            try:
                for i in range(1, 5):
                    start_node(i)
                self.assertTrue(self._wait(lambda: converged(range(1, 5), 1), 14),
                                "four independent members failed initial election")
                processes[0].kill()
                processes[0].wait(timeout=4)
                self.assertTrue(self._wait(lambda: converged((2, 3, 4), 2), 12),
                                "three surviving members failed quorum recovery")
                restarted = start_node(1)
                self.assertTrue(self._wait(lambda: (
                    self._read_status(members[0]).get("pid") == restarted.pid
                    and self._read_status(members[0]).get("leader") == 2
                    and self._read_status(members[0]).get("has_certificate") is True
                ), 12), "restarted node failed to rejoin the certified mesh")
            finally:
                for proc in processes:
                    if proc.poll() is None:
                        proc.terminate()
                for proc in processes:
                    try:
                        proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=4)


if __name__ == "__main__":
    unittest.main()
