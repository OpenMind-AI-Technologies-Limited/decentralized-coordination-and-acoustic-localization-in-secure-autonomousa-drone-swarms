"""Step 5 common-information allocation comparators for simulation studies.

All comparators use the SAME reported positions, health thresholds, task XYZ,
capacity, and distance + health penalty as the unchanged production greedy.

- greedy: unchanged production heuristic.
- hungarian: maximum-cardinality then minimum-total-cost matching, central
  reference using scipy.optimize.linear_sum_assignment with dummy slots.
- cbaa_single: synchronous single-assignment consensus-based auction SPECIAL
  CASE (CBAA-style) with ideal reliable all-to-all bid dissemination.
- cbba_static: static additive-score bundle-auction SPECIALIZATION with
  synchronous consensus, NOT full path-dependent/asynchronous original CBBA.

None of the methods has access to evaluation ground truth or flight actuators.
Logical bid-message metrics are NOT physical radio packet measurements.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from swarm_mesh import HealthReport
from swarm_tasks import allocate_tasks


@dataclass(frozen=True)
class ComparableProblem:
    """Immutable validation result with strictly equal information budget."""
    positions: dict[int, tuple[float, float, float]]
    health: dict[int, HealthReport]
    tasks: dict[str, tuple[float, float, float]]
    max_per_node: int

    @classmethod
    def build(cls, positions: Mapping[int, Sequence[float]],
              health: Mapping[int, HealthReport],
              tasks: Mapping[str, Sequence[float]], *,
              max_per_node: int = 1,
              minimum_battery_pct: float = 30.0,
              minimum_motor_pct: float = 75.0,
              minimum_link_pct: float = 40.0) -> "ComparableProblem":
        if not isinstance(max_per_node, int) or max_per_node < 1:
            raise ValueError("max_per_node must be a positive integer")
        if len(tasks) > 1000:
            raise ValueError("Too many tasks")
        def xyz(value: Sequence[float]) -> tuple[float, float, float]:
            try:
                result = tuple(float(v) for v in value)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("Invalid position") from exc
            if len(result) != 3 or any(not math.isfinite(v) for v in result):
                raise ValueError("Coordinates must be finite XYZ")
            return result

        chosen = {}
        chosen_health = {}
        for raw_id, position in positions.items():
            member = int(raw_id)
            report = health.get(member)
            if report is None:
                continue
            report = HealthReport.from_dict(report.to_dict())
            if (report.battery < minimum_battery_pct or
                    report.motor_health < minimum_motor_pct or
                    report.link_quality < minimum_link_pct):
                continue
            chosen[member] = xyz(position)
            chosen_health[member] = report

        task_xyz = {}
        for task_id, destination in tasks.items():
            if not isinstance(task_id, str) or not task_id:
                raise ValueError("Task IDs must be nonempty strings")
            point = xyz(destination)
            if not 1 <= point[2] <= 100:
                raise ValueError("Task altitude outside simulation safety window")
            task_xyz[task_id] = point
        return cls(dict(sorted(chosen.items())), chosen_health,
                   dict(sorted(task_xyz.items())), max_per_node)

    def cost(self, member: int, task_id: str) -> float:
        report = self.health[member]
        return (math.dist(self.positions[member], self.tasks[task_id])
                + 0.35 * (100 - report.battery)
                + 0.50 * (100 - report.motor_health)
                + 0.15 * (100 - report.link_quality))

    def empty(self) -> dict[int, list[tuple[str, tuple[float, float, float]]]]:
        return {member: [] for member in self.positions}


def _format_result(problem: ComparableProblem, pairs: list[tuple[int, str]], *,
                   algorithm: str, rounds: int = 0,
                   logical_bid_messages: int = 0) -> dict:
    allocated = problem.empty()
    seen = set()
    for member, task_id in pairs:
        if member not in allocated or task_id not in problem.tasks:
            raise AssertionError("Comparator produced unknown member/task")
        if task_id in seen or len(allocated[member]) >= problem.max_per_node:
            raise AssertionError("Comparator assigned duplicate or overcapacity task")
        allocated[member].append((task_id, problem.tasks[task_id]))
        seen.add(task_id)
    for member in allocated:
        allocated[member].sort(key=lambda x: x[0])
    return {
        "algorithm": algorithm,
        "allocations": allocated,
        "unassigned": sorted(set(problem.tasks) - seen),
        "tasks_assigned": len(pairs),
        "objective_total_cost": math.fsum(problem.cost(member, task)
                                           for member, task in pairs),
        "consensus_rounds": rounds,
        "logical_bid_messages": logical_bid_messages,
        "communication_model": ("perfect_synchronous_all_to_all_abstract_bids"
                                if rounds else "centralized_no_auction_gossip"),
        "real_radio_bytes_measured": False,
    }


def greedy_comparable(problem: ComparableProblem) -> dict:
    """Use original greedy code, not a look-alike replacement."""
    allocation = allocate_tasks(problem.positions, problem.health, problem.tasks,
                                max_per_node=problem.max_per_node)
    pairs = [(member, task_id) for member, items in allocation.items()
             for task_id, _ in items]
    return _format_result(problem, pairs, algorithm="production_greedy")


def hungarian_comparable(problem: ComparableProblem) -> dict:
    """Exact min-cost among maximum-cardinality feasible assignments.

    Each eligible member occupies `max_per_node` slots (no coupling between
    slots). An extra private dummy column per task models unassigned tasks.
    A cost bound makes every real matched slot preferable to a dummy, so the
    objective is first coverage, then the distance/health cost.
    """
    tasks = list(problem.tasks)
    member_slots = [member for member in problem.positions
                    for _ in range(min(problem.max_per_node, len(tasks)))]
    if not tasks or not member_slots:
        return _format_result(problem, [], algorithm="hungarian_constrained")

    real = np.asarray([[problem.cost(member, task) for member in member_slots]
                       for task in tasks], dtype=np.float64)
    largest = float(np.max(real))
    # Costs are nonnegative. The penalty exceeds the total sum bound of ANY
    # <=len(tasks) feasible real assignments, guaranteeing max cardinality.
    dummy_penalty = (largest + 1.) * (len(tasks) + 1.)
    dummy = np.full((len(tasks), len(tasks)), dummy_penalty, dtype=np.float64)
    cost = np.concatenate([real, dummy], axis=1)
    rows, cols = linear_sum_assignment(cost)
    pairs = [(member_slots[int(j)], tasks[int(i)])
             for i, j in zip(rows, cols) if j < len(member_slots)]
    return _format_result(problem, pairs, algorithm="hungarian_constrained")


def cbaa_single_comparable(problem: ComparableProblem) -> dict:
    """One-task-per-member synchronous consensus auction (CBAA-style).

    Each idle member places a bid for its cheapest remaining task. The
    deterministic conflict resolver shares winning bids with all members.
    This *idealized reliable broadcast* is a single-task specialization, not
    general CBBA, and is intentionally NOT claimed to handle packet loss.
    """
    if problem.max_per_node != 1:
        raise ValueError("CBAA single-assignment requires max_per_node=1")
    remaining = set(problem.tasks)
    idle = set(problem.positions)
    winners = []
    rounds = messages = 0
    while remaining and idle:
        rounds += 1
        proposals: dict[str, list[tuple[float, int]]] = {}
        for member in sorted(idle):
            task_id = min(remaining, key=lambda task: (problem.cost(member, task), task))
            proposals.setdefault(task_id, []).append(
                (problem.cost(member, task_id), member))
            messages += max(0, len(problem.positions) - 1)
        for task_id in sorted(proposals):
            _cost, member = min(proposals[task_id])
            winners.append((member, task_id))
            idle.remove(member)
            remaining.remove(task_id)
    return _format_result(problem, winners, algorithm="cbaa_single_synchronous",
                          rounds=rounds, logical_bid_messages=messages)


def cbba_static_comparable(problem: ComparableProblem) -> dict:
    """Static additive-score synchronous *bundle auction* specialization.

    At each round, free members build a bundle of cheapest remaining tasks,
    up to their unused capacity. A consensus phase picks the highest bidder
    for each task. Outbid members refill in later rounds. Bundles here have
    no path-dependent insertion score, communication delay, inconsistent
    world models, or asynchronous conflict histories: **not a full CBBA**.
    """
    remaining = set(problem.tasks)
    free_capacity = {member: problem.max_per_node for member in problem.positions}
    winners: list[tuple[int, str]] = []
    rounds = messages = 0
    while remaining and any(free_capacity.values()):
        rounds += 1
        proposals: dict[str, list[tuple[float, int]]] = {}
        for member in sorted(free_capacity):
            limit = min(free_capacity[member], len(remaining))
            proposed = sorted(remaining,
                              key=lambda task: (problem.cost(member, task), task))[:limit]
            for task in proposed:
                proposals.setdefault(task, []).append((problem.cost(member, task), member))
                messages += max(0, len(problem.positions) - 1)
        if not proposals:
            break
        for task in sorted(proposals):
            _cost, member = min(proposals[task])
            if not free_capacity[member]:
                continue
            winners.append((member, task))
            free_capacity[member] -= 1
            remaining.remove(task)
    return _format_result(problem, winners,
                          algorithm="cbba_static_additive_specialization",
                          rounds=rounds, logical_bid_messages=messages)


METHODS = {
    "greedy": greedy_comparable,
    "hungarian": hungarian_comparable,
    "cbaa": cbaa_single_comparable,
    "cbba_static": cbba_static_comparable,
}


def compare_allocators(problem: ComparableProblem,
                       methods: Sequence[str] = tuple(METHODS)) -> dict[str, dict]:
    results = {}
    for name in methods:
        if name not in METHODS:
            raise ValueError(f"Unknown comparator: {name}")
        results[name] = METHODS[name](problem)
    return results
