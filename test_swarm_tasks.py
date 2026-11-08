"""Deterministic cooperative task allocation tests."""
import math
import unittest

from swarm_mesh import HealthReport
from swarm_tasks import allocate_tasks


class TaskAssignmentTests(unittest.TestCase):
    def test_unique_one_to_one_assignments(self):
        positions = {1: (0, 0, 10), 2: (100, 0, 10), 3: (200, 0, 10)}
        health = {i: HealthReport(90, 100, 95) for i in positions}
        tasks = {"A": (2, 0, 10), "B": (102, 0, 10), "C": (202, 0, 10)}
        allocated = allocate_tasks(positions, health, tasks)
        self.assertEqual({i: xs[0][0] for i, xs in allocated.items()}, {1: "A", 2: "B", 3: "C"})

    def test_degraded_node_excluded(self):
        positions = {1: (0, 0, 10), 2: (30, 0, 10)}
        health = {1: HealthReport(15, 100, 95), 2: HealthReport(80, 100, 95)}
        allocated = allocate_tasks(positions, health, {"rescue": (0, 0, 10)})
        self.assertFalse(allocated.get(1))
        self.assertEqual(allocated[2][0][0], "rescue")

    def test_unassigned_tasks_not_silently_duplicated(self):
        positions = {1: (0, 0, 10)}
        health = {1: HealthReport(90, 100, 100)}
        allocated = allocate_tasks(positions, health,
                                   {"A": (0, 0, 10), "B": (5, 0, 10)}, max_per_node=1)
        self.assertEqual(sum(len(entries) for entries in allocated.values()), 1)

    def test_deterministic_under_different_map_order(self):
        p1 = {1: (0, 0, 10), 2: (10, 0, 10)}
        p2 = {2: (10, 0, 10), 1: (0, 0, 10)}
        health = {1: HealthReport(90, 100, 100), 2: HealthReport(90, 100, 100)}
        tasks = {"B": (8, 0, 10), "A": (2, 0, 10)}
        self.assertEqual(allocate_tasks(p1, health, tasks), allocate_tasks(p2, health, tasks))

    def test_invalid_nonfinite_coordinates_rejected(self):
        with self.assertRaises(ValueError):
            allocate_tasks({1: (0, 0, 10)}, {1: HealthReport(90, 100, 100)},
                           {"bad": (math.inf, 0, 20)})

    def test_50_node_feasible_allocation(self):
        positions = {i: (float(i*10), 0, 10) for i in range(1, 51)}
        health = {i: HealthReport(90, 100, 100) for i in positions}
        tasks = {f"task-{i:02d}": (float(i*10), 0, 10) for i in range(1, 51)}
        allocation = allocate_tasks(positions, health, tasks)
        self.assertEqual(sum(len(assigned) for assigned in allocation.values()), 50)
        self.assertEqual(len({entries[0][0] for entries in allocation.values() if entries}), 50)


if __name__ == "__main__":
    unittest.main()
