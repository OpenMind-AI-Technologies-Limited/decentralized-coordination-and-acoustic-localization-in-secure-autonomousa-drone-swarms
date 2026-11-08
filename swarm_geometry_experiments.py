"""Seeded swarm geometry and health-weighted scheduling comparisons.

These are idealized 3D positions and waypoint calculations, not physical UAV
trajectories, aerodynamic collisions, energy measurements, or mission sorties.
"""
from __future__ import annotations

import itertools
import math
import random
from statistics import mean

from swarm_formation import formation_target, separate_from_neighbors
from swarm_mesh import HealthReport
from swarm_tasks import allocate_tasks


def _min_pair_distance(positions):
    return min(math.dist(a, b) for a, b in itertools.combinations(positions, 2))


def _close_pairs(positions, radius_m=8.0):
    return sum(math.dist(a, b) < radius_m
               for a, b in itertools.combinations(positions, 2))


def formation_trial(nodes: int, seed: int, pattern: str,
                    position_noise_m: float = 6.0) -> dict:
    if nodes < 4 or nodes > 50 or pattern not in {"v", "line", "circle", "grid"}:
        raise ValueError("Unsupported formation experiment")
    if not 0 <= position_noise_m <= 100:
        raise ValueError("Invalid synthetic displacement")
    rng = random.Random(seed)
    ids = list(range(1, nodes+1))
    targets = {
        i: formation_target(i, 1, ids, (0.0, 0.0, 30.0),
                            (1.0, 0.0), pattern, 12.0)
        for i in ids
    }
    observed = {
        i: tuple(targets[i][j] + rng.gauss(0, position_noise_m)
                 for j in range(3))
        for i in ids
    }
    # This algorithm proposes new waypoints; it does not teleport vehicles.
    adjusted = {i: separate_from_neighbors(i, observed[i], observed)
                for i in ids}
    original_positions = list(observed.values())
    suggested_positions = list(adjusted.values())
    return {
        "family": "formation", "scenario": pattern,
        "nodes": nodes, "seed": int(seed),
        "baseline_pair_violations": _close_pairs(original_positions),
        "adjusted_waypoint_violations": _close_pairs(suggested_positions),
        "baseline_min_separation_m": _min_pair_distance(original_positions),
        "adjusted_min_separation_m": _min_pair_distance(suggested_positions),
        "baseline_reference_error_m": mean(math.dist(observed[i], targets[i]) for i in ids),
        "adjusted_reference_error_m": mean(math.dist(adjusted[i], targets[i]) for i in ids),
        "suggested_displacement_m": mean(math.dist(adjusted[i], observed[i]) for i in ids),
        "pair_violation_reduction": (
            _close_pairs(original_positions) - _close_pairs(suggested_positions)
        ),
        "minimum_separation_change_m": (
            _min_pair_distance(suggested_positions) - _min_pair_distance(original_positions)
        ),
    }


def allocation_trial(nodes: int, seed: int, degraded: bool) -> dict:
    if nodes < 4 or nodes > 50:
        raise ValueError("Unsupported task allocation experiment")
    rng = random.Random(seed)
    ids = list(range(1, nodes+1))
    positions = {i: (rng.uniform(-180, 180), rng.uniform(-180, 180), 25.0)
                 for i in ids}
    degraded_ids = set(rng.sample(ids, max(1, nodes//5))) if degraded else set()
    health = {
        i: HealthReport(
            battery=15 if i in degraded_ids else rng.uniform(65, 100),
            motor_health=65 if i in degraded_ids else rng.uniform(85, 100),
            link_quality=rng.uniform(60, 100))
        for i in ids
    }
    tasks = {
        f"inspection-{j:03d}": (rng.uniform(-160, 160),
                               rng.uniform(-160, 160), 25.0)
        for j in range(max(1, 3*nodes//4))
    }
    assigned = allocate_tasks(positions, health, tasks, max_per_node=1)
    pairs = [(i, label, target)
             for i, allocation in assigned.items()
             for label, target in allocation]
    # Naive assignment baseline does not inspect battery/motor health; both
    # policies get the same spatial positions and task targets.
    naive = [(ids[j], task_id, tasks[task_id])
             for j, task_id in enumerate(sorted(tasks))]
    eligible = {i for i in ids if
                health[i].battery >= 30 and
                health[i].motor_health >= 75 and
                health[i].link_quality >= 40}
    return {
        "family": "allocation", "scenario": "degraded" if degraded else "healthy",
        "nodes": nodes, "seed": int(seed),
        "tasks_requested": len(tasks),
        "tasks_assigned": len(pairs),
        "baseline_tasks_assigned": len(naive),
        "baseline_ineligible_assignments": sum(1 for i, _, _ in naive if i not in eligible),
        "ineligible_assignments": sum(1 for i, _, _ in pairs if i not in eligible),
        "mean_assignment_distance_m": (
            mean(math.dist(positions[i], target) for i, _, target in pairs) if pairs else 0.0
        ),
        "baseline_mean_distance_m": mean(
            math.dist(positions[i], target) for i, _, target in naive),
        "ineligible_assignment_reduction": (
            sum(1 for i, _, _ in naive if i not in eligible)
            - sum(1 for i, _, _ in pairs if i not in eligible)
        ),
    }
