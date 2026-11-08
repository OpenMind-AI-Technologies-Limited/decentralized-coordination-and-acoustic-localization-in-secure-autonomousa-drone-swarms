"""Deterministic telemetry-aware task assignment for a certified swarm leader.

This is a greedy health-weighted assignment heuristic, not globally optimal
matching and not a leaderless distributed task-consensus protocol.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

from swarm_mesh import HealthReport


def allocate_tasks(
    positions: Mapping[int, Sequence[float]],
    health: Mapping[int, HealthReport],
    tasks: Mapping[str, Sequence[float]],
    max_per_node: int = 1,
    minimum_battery_pct: float = 30.0,
    minimum_motor_pct: float = 75.0,
    minimum_link_pct: float = 40.0,
) -> dict[int, list[tuple[str, tuple[float, float, float]]]]:
    """Assign tasks to feasible nodes using deterministic greedy travel costs.

    Each task is assigned at most once. Tasks without a qualified available
    node remain unassigned; callers should detect missing task IDs explicitly.
    """
    if max_per_node < 1:
        raise ValueError("max_per_node must be positive")
    if len(tasks) > 1000:
        raise ValueError("Too many tasks")
    eligible: dict[int, tuple[float, float, float]] = {}
    for raw_id, position in positions.items():
        node_id = int(raw_id)
        report = health.get(node_id)
        if report is None:
            continue
        if (report.battery < minimum_battery_pct or
            report.motor_health < minimum_motor_pct or
            report.link_quality < minimum_link_pct):
            continue
        pos = tuple(float(x) for x in position)
        if len(pos) != 3 or not all(math.isfinite(x) for x in pos):
            raise ValueError("Invalid node position")
        eligible[node_id] = pos

    counts = {node: 0 for node in eligible}
    allocation: dict[int, list[tuple[str, tuple[float, float, float]]]] = {
        node: [] for node in sorted(eligible)
    }
    for task_id, target_values in sorted(tasks.items(), key=lambda entry: str(entry[0])):
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("Task IDs must be nonempty strings")
        target = tuple(float(x) for x in target_values)
        if len(target) != 3 or not all(math.isfinite(x) for x in target):
            raise ValueError("Invalid task coordinates")
        if target[2] < 1 or target[2] > 100:
            raise ValueError("Task altitude outside simulation safety window")
        costs = []
        for node_id, position in eligible.items():
            if counts[node_id] >= max_per_node:
                continue
            report = health[node_id]
            distance = math.dist(position, target)
            # Explicit, explainable preference for safer battery/motor/link state.
            penalty = (0.35 * (100 - report.battery) +
                       0.50 * (100 - report.motor_health) +
                       0.15 * (100 - report.link_quality))
            costs.append((distance + penalty, node_id))
        if not costs:
            continue
        _, selected = min(costs)
        allocation[selected].append((task_id, target))
        counts[selected] += 1
    return allocation
