"""Conservative rule-based motion safety gate for SOFTWARE SIMULATION ONLY.

MLDecisionSupport is a heuristic obstacle risk model, not an empirically
validated trained collision predictor. This module cannot certify flight safety.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Optional, Sequence

from ml_system import MLDecisionSupport


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    fallback: str = "none"
    predicted_risk: float = 0.0


class SimulatedMotionSafety:
    def __init__(self, min_separation_m: float = 8.0,
                 battery_reserve_pct: float = 20.0,
                 latency_limit_ms: float = 220.0,
                 risk_threshold: float = 0.30):
        if min_separation_m <= 0 or not 0 < battery_reserve_pct < 100:
            raise ValueError("Invalid safety limits")
        if latency_limit_ms <= 0 or not 0 < risk_threshold < 1:
            raise ValueError("Invalid latency/risk thresholds")
        self.min_separation_m = min_separation_m
        self.battery_reserve_pct = battery_reserve_pct
        self.latency_limit_ms = latency_limit_ms
        self.risk_threshold = risk_threshold
        self.risk_model = MLDecisionSupport()

    def add_obstacle(self, xyz: Sequence[float], radius_m: float):
        if len(xyz) != 3 or not all(math.isfinite(float(x)) for x in xyz):
            raise ValueError("Invalid obstacle")
        if not math.isfinite(float(radius_m)) or radius_m <= 0:
            raise ValueError("Invalid obstacle radius")
        self.risk_model.add_obstacle(*[float(x) for x in xyz], float(radius_m))

    def vertical_escape_waypoint(self, drone, target_xyz: Sequence[float],
                                 peer_positions: Mapping[int, Sequence[float]],
                                 quorum_available: bool = True,
                                 observed_latency_ms: Optional[float] = None) -> Optional[tuple]:
        """First climb above peers if a straight planned segment is unsafe.

        This is only a local simulation heuristic. The intended final target
        must be rechecked with live neighbor positions after the climb.
        """
        origin = drone.current_position
        start = (float(origin.x), float(origin.y), float(origin.z))
        try:
            desired_z = float(target_xyz[2])
        except (ValueError, IndexError, TypeError):
            return None
        elevated_z = min(100., float(drone.MAX_ALTITUDE),
                         max(start[2], desired_z) + max(12., self.min_separation_m + 4.))
        if elevated_z <= start[2] + 1.:
            return None
        waypoint = (start[0], start[1], elevated_z)
        decision = self.assess(
            drone, waypoint, peer_positions,
            observed_latency_ms=observed_latency_ms,
            quorum_available=quorum_available,
        )
        return waypoint if decision.allowed else None

    def assess(self, drone, target_xyz: Sequence[float],
               peer_positions: Mapping[int, Sequence[float]],
               observed_latency_ms: Optional[float] = None,
               quorum_available: bool = True) -> SafetyDecision:
        if not quorum_available:
            return SafetyDecision(False, "quorum_unavailable", "hold")
        if observed_latency_ms is not None:
            latency = float(observed_latency_ms)
            if not math.isfinite(latency) or latency < 0 or latency > self.latency_limit_ms:
                return SafetyDecision(False, "latency_limit_exceeded", "hold")
        if drone.use_real_drone or drone.real_drone_connection or drone.mavlink_connected:
            return SafetyDecision(False, "hardware_control_not_authorized", "hold")
        if (drone.battery_level <= self.battery_reserve_pct or
                any(not motor.operational for motor in drone.motors) or
                drone.degraded_return_active or drone.emergency_return_active):
            return SafetyDecision(False, "vehicle_health_requires_local_fallback", "local_rth")
        try:
            target = tuple(float(x) for x in target_xyz)
            if len(target) != 3 or not all(math.isfinite(x) for x in target):
                return SafetyDecision(False, "invalid_target", "hold")
            if not (1 <= target[2] <= min(float(drone.MAX_ALTITUDE), 100)):
                return SafetyDecision(False, "altitude_rejected", "hold")
            origin = drone.current_position
            start = (float(origin.x), float(origin.y), float(origin.z))
            if math.dist(target[:2], (float(drone.home_position.x),
                                     float(drone.home_position.y))) > drone.MAX_OPERATION_RADIUS:
                return SafetyDecision(False, "outside_geofence", "hold")
            for other_id, position in peer_positions.items():
                if int(other_id) == drone.drone_id:
                    continue
                neighbor = tuple(float(x) for x in position)
                if len(neighbor) != 3 or not all(math.isfinite(x) for x in neighbor):
                    return SafetyDecision(False, "invalid_peer_telemetry", "hold")
                # Check the complete planned straight segment against peers,
                # not just the endpoint of the received command.
                direction = tuple(target[i] - start[i] for i in range(3))
                norm_sq = sum(x*x for x in direction)
                projected = 0.0 if norm_sq < 1e-12 else max(
                    0.0, min(1.0, sum((neighbor[i] - start[i]) * direction[i]
                                      for i in range(3)) / norm_sq))
                closest = tuple(start[i] + direction[i]*projected for i in range(3))
                if math.dist(closest, neighbor) < self.min_separation_m:
                    return SafetyDecision(False, "path_too_close_to_neighbor", "hold")
            # Heuristic velocity projection for the next three simulated seconds.
            vx = tuple((target[i] - start[i]) / 3.0 for i in range(3))
            risk = float(self.risk_model.predict_collision_risk(start, vx, time_horizon=3.0))
            if risk >= self.risk_threshold:
                return SafetyDecision(False, "projected_obstacle_collision", "hold", risk)
            return SafetyDecision(True, "safe_in_simulation", "none", risk)
        except (TypeError, ValueError, OverflowError):
            return SafetyDecision(False, "invalid_motion_state", "hold")
