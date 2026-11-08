"""Locally computed formation targets and neighbor separation.

Geometry targets are not certified flight-safe trajectories. Underlying flight
controllers must still enforce geofences, altitude and collision constraints.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence


def formation_target(node_id: int, leader_id: int, members: Sequence[int],
                     leader_position: Sequence[float], heading_xy: Sequence[float],
                     pattern: str = "v", spacing_m: float = 12.0) -> tuple[float, float, float]:
    ids = sorted(set(int(i) for i in members))
    if leader_id not in ids or node_id not in ids:
        raise ValueError("Leader and member must exist in roster")
    if pattern not in {"line", "v", "circle", "grid"}:
        raise ValueError("Unsupported formation")
    if not 3 <= len(ids) or not 1.0 <= spacing_m <= 1000.0:
        raise ValueError("Invalid fleet size or spacing")
    if len(leader_position) != 3 or len(heading_xy) != 2:
        raise ValueError("Malformed geometry")
    px, py, pz = (float(x) for x in leader_position)
    dx, dy = (float(x) for x in heading_xy)
    if not all(math.isfinite(v) for v in (px, py, pz, dx, dy)):
        raise ValueError("Non-finite geometry")
    norm = math.hypot(dx, dy)
    if norm < 1e-6:
        dx, dy = 1.0, 0.0
    else:
        dx, dy = dx / norm, dy / norm
    if node_id == leader_id:
        return px, py, pz
    rank = [i for i in ids if i != leader_id].index(node_id)
    if pattern == "line":
        forward, lateral = -spacing_m * (rank + 1), 0.0
    elif pattern == "v":
        row = rank // 2 + 1
        side = -1 if rank % 2 == 0 else 1
        forward, lateral = -spacing_m * row, side * spacing_m * row
    elif pattern == "circle":
        follower_count = len(ids) - 1
        radius = max(spacing_m, spacing_m * follower_count / math.pi)
        theta = 2 * math.pi * rank / follower_count
        forward, lateral = radius * math.cos(theta), radius * math.sin(theta)
    else:
        side = int(math.ceil(math.sqrt(len(ids))))
        if side % 2 == 0:
            side += 1
        half = side // 2
        slots = [(i, j) for i in range(-half, half + 1)
                 for j in range(-half, half + 1) if (i, j) != (0, 0)]
        slots.sort(key=lambda ij: (max(abs(ij[0]), abs(ij[1])), abs(ij[0])+abs(ij[1]), ij))
        forward, lateral = (spacing_m * x for x in slots[rank])
    return (px + dx * forward - dy * lateral,
            py + dy * forward + dx * lateral, pz)


def separate_from_neighbors(node_id: int, intended: Sequence[float],
                            positions: Mapping[int, Sequence[float]],
                            min_separation_m: float = 8.0,
                            max_adjustment_m: float = 10.0) -> tuple[float, float, float]:
    """Repel from nearby nodes without overruling flight-controller constraints."""
    if min_separation_m <= 0 or max_adjustment_m <= 0:
        raise ValueError("Separation distances must be positive")
    x, y, z = (float(v) for v in intended)
    if not all(math.isfinite(v) for v in (x, y, z)):
        raise ValueError("Non-finite goal")
    if node_id not in positions:
        return x, y, z
    own = tuple(float(v) for v in positions[node_id])
    dx_total = dy_total = dz_total = 0.0
    for peer_id, position in positions.items():
        if peer_id == node_id:
            continue
        peer = tuple(float(v) for v in position)
        vx, vy, vz = (own[i] - peer[i] for i in range(3))
        d = math.sqrt(vx*vx + vy*vy + vz*vz)
        if d >= min_separation_m:
            continue
        if d < 1e-9:
            vx, vy, vz = (-1.0 if int(node_id) < int(peer_id) else 1.0), 0.0, 0.0
            d = 1.0
        force = (min_separation_m - min(d, min_separation_m)) / min_separation_m
        dx_total += vx / d * force
        dy_total += vy / d * force
        dz_total += vz / d * force
    magnitude = math.sqrt(dx_total**2 + dy_total**2 + dz_total**2)
    if magnitude <= 1e-9:
        return x, y, z
    gain = min(max_adjustment_m, max_adjustment_m * magnitude)
    return x + gain * dx_total / magnitude, y + gain * dy_total / magnitude, z + gain * dz_total / magnitude
