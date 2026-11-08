"""Opt-in PyQt5 swarm coordination dashboard, strictly simulation-only.

This is a separate mode of the existing application. It does not start the
legacy SwarmManager/GUI path and cannot connect to physical UAVs.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from acoustic_tracking import SPEED_OF_SOUND_MPS

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from drone import Drone, FlightMode, Position
from mesh_simulation import DroneMeshSimulation


def create_dashboard_swarm() -> DroneMeshSimulation:
    positions = [(0.0, 0.0), (24.0, 0.0), (0.0, 24.0), (-24.0, 0.0)]
    drones = {
        i: Drone(i, Position(x, y, 0.0))
        for i, (x, y) in enumerate(positions, start=1)
    }
    for drone in drones.values():
        drone.TAKEOFF_ALTITUDE = 2.0
        drone.wind_enabled = False
    return DroneMeshSimulation(drones)


class MeshDashboard(QMainWindow):
    """Read current per-node signed coordination state; send certified missions."""

    def __init__(self, simulation: Optional[DroneMeshSimulation] = None,
                 auto_start: bool = True):
        super().__init__()
        self.sim = simulation or create_dashboard_swarm()
        self.setWindowTitle("Secure Drone Swarm · Authenticated Mesh Simulation")
        self.resize(1000, 650)
        self._started = False

        root = QWidget(self)
        self.setCentralWidget(root)
        content = QVBoxLayout(root)
        content.setSpacing(15)

        heading = QLabel("Authenticated Swarm Coordination")
        heading.setObjectName("heading")
        content.addWidget(heading)
        subtitle = QLabel(
            "SIMULATION ONLY · Signed member telemetry · Quorum-certified leader · No physical UAV connections"
        )
        subtitle.setObjectName("subtitle")
        content.addWidget(subtitle)

        metrics = QHBoxLayout()
        self.leader_label = QLabel("Leader: acquiring quorum")
        self.quorum_label = QLabel("Quorum: pending")
        self.nodes_label = QLabel("Nodes: 0")
        self.audit_label = QLabel("Signed audit: no commits")
        for widget in (self.leader_label, self.quorum_label, self.nodes_label,
                       self.audit_label):
            metrics.addWidget(widget)
        content.addLayout(metrics)

        self.table = QTableWidget(len(self.sim.drones), 7)
        self.table.setHorizontalHeaderLabels([
            "Drone", "Role", "Epoch", "Battery", "Motor health", "XYZ (m)", "Flight state",
        ])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        content.addWidget(self.table)

        actions = QGroupBox("Simulated swarm commands")
        action_layout = QGridLayout(actions)
        self.pattern = QComboBox()
        self.pattern.addItems(["v", "line", "circle", "grid"])
        self.formation_button = QPushButton("Send certified formation")
        self.formation_button.clicked.connect(self.send_formation)
        self.tasks_button = QPushButton("Allocate inspection tasks")
        self.tasks_button.clicked.connect(self.send_tasks)
        self.acoustic_button = QPushButton("Simulate TDOA sound-source detection")
        self.acoustic_button.clicked.connect(self.simulate_acoustic)
        self.beacon_button = QPushButton("Simulate known-beacon GPS-free XY")
        self.beacon_button.clicked.connect(self.simulate_receiver_beacons)
        self.rtt_button = QPushButton("Measure authenticated UDP RTT")
        self.rtt_button.clicked.connect(self.measure_latency)
        self.failure_member = QComboBox()
        self.failure_member.addItems([str(i) for i in sorted(self.sim.drones)])
        self.failure_button = QPushButton("Simulate selected drone failure")
        self.failure_button.clicked.connect(self.fail_member)

        action_layout.addWidget(QLabel("Formation"), 0, 0)
        action_layout.addWidget(self.pattern, 0, 1)
        action_layout.addWidget(self.formation_button, 0, 2)
        action_layout.addWidget(self.tasks_button, 1, 2)
        action_layout.addWidget(QLabel("Failure target"), 1, 0)
        action_layout.addWidget(self.failure_member, 1, 1)
        action_layout.addWidget(self.failure_button, 2, 2)
        action_layout.addWidget(self.acoustic_button, 3, 1)
        action_layout.addWidget(self.beacon_button, 4, 1)
        action_layout.addWidget(self.rtt_button, 3, 2)
        content.addWidget(actions)
        self.acoustic_label = QLabel("Acoustic observation: no source estimate")
        self.rtt_label = QLabel("Measured peer RTT: not measured")
        content.addWidget(self.acoustic_label)
        content.addWidget(self.rtt_label)

        self.status = QLabel("Initializing loopback-only simulated drone physics.")
        content.addWidget(self.status)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #101722; color: #e6ecf3; font-size: 13px; }
            QLabel#heading { font-size: 24px; font-weight: bold; color: #eaf3ff; }
            QLabel#subtitle { color: #8dacc3; }
            QPushButton { background: #1661a0; border: 0; padding: 11px; border-radius: 5px; }
            QPushButton:disabled { background: #344050; color: #a5afbd; }
            QPushButton:hover { background: #247bbf; }
            QGroupBox { border: 1px solid #34485d; border-radius: 7px; margin-top: 10px; }
            QTableWidget { border: 1px solid #35485c; gridline-color: #35485c; }
            QHeaderView::section { background: #203044; color: #dbe8f1; padding: 7px; }
            QComboBox { background: #243647; border: 1px solid #426077; padding: 7px; }
        """)

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        if auto_start:
            self.start_simulation()
        self.refresh()

    def start_simulation(self):
        if self._started:
            return
        self.sim.start()
        self._started = True
        for drone in self.sim.drones.values():
            # Explicit local arm and takeoff only. Network packets never arm.
            if not drone.arm() or not drone.takeoff():
                self.status.setText(f"Simulated takeoff failed for Drone {drone.drone_id}")
        self.timer.start()

    def _ready_to_command(self) -> bool:
        if not self._started or self.sim.leader() is None:
            return False
        return all(
            not drone.running or drone.flight_mode in (FlightMode.HOVER, FlightMode.FLYING)
            for drone in self.sim.drones.values()
        )

    def refresh(self):
        leader = self.sim.leader() if self._started else None
        self.leader_label.setText(f"Leader: Drone {leader}" if leader else "Leader: no certified quorum")
        nodes = self.sim.nodes
        active = sum(
            1 for i, runtime in self.sim._runtimes.items()
            if not runtime._stop.is_set()
        )
        quorum = next(iter(nodes.values())).quorum
        self.quorum_label.setText(f"Quorum: {quorum}/{len(nodes)}")
        self.nodes_label.setText(f"Running: {active}/{len(nodes)}")
        heights = {audit.height for audit in self.sim.audit_ledgers.values()}
        latest_height = max(heights) if heights else 0
        self.audit_label.setText(
            f"Quorum audit: height {latest_height}" +
            (" (replicas differ)" if len(heights) > 1 else " (replicas aligned)")
        )
        self.acoustic_button.setEnabled(self._started and leader is not None)
        self.beacon_button.setEnabled(self._started and leader is not None)
        self.rtt_button.setEnabled(self._started and leader is not None)
        self.formation_button.setEnabled(self._ready_to_command())
        self.tasks_button.setEnabled(self._ready_to_command())
        for row, node_id in enumerate(sorted(self.sim.drones)):
            drone = self.sim.drones[node_id]
            agent = nodes[node_id]
            position = drone.current_position
            values = [
                str(node_id), "LEADER" if node_id == leader else "FOLLOWER",
                str(agent.epoch), f"{drone.battery_level:.1f}%",
                f"{sum(m.operational for m in drone.motors) / len(drone.motors) * 100:.0f}%",
                f"{position.x:.1f}, {position.y:.1f}, {position.z:.1f}",
                drone.flight_mode.value if drone.running else "OFFLINE",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

    def send_formation(self):
        if not self._ready_to_command():
            self.status.setText("Command refused: no quorum or drones not ready.")
            return
        leader = self.sim.leader()
        drone = self.sim.drones[leader]
        p = drone.current_position
        try:
            self.sim.command_formation(
                self.pattern.currentText(), (p.x, p.y, max(5.0, p.z)),
                (1.0, 0.0), 12.0,
            )
            self.status.setText(f"Signed formation command sent by Drone {leader}.")
        except (PermissionError, ValueError, OSError) as exc:
            self.status.setText(f"Command refused: {exc}")
        self.refresh()

    def send_tasks(self):
        if not self._ready_to_command():
            self.status.setText("Task allocation refused: no quorum or drones not ready.")
            return
        leader = self.sim.leader()
        p = self.sim.drones[leader].current_position
        try:
            plan = self.sim.command_tasks({
                "inspection-west": (p.x - 25, p.y + 15, max(p.z, 5.0)),
                "inspection-east": (p.x + 25, p.y + 15, max(p.z, 5.0)),
            })
            self.status.setText(
                f"Task plan sent by Drone {leader}: {len(plan['assigned'])} assigned, "
                f"{len(plan['unassigned'])} unassigned."
            )
        except (PermissionError, ValueError, OSError) as exc:
            self.status.setText(f"Task allocation refused: {exc}")
        self.refresh()

    def simulate_acoustic(self):
        """Explicitly synthetic audio pulses; never autonomous real movement."""
        if not self._started or self.sim.leader() is None:
            self.status.setText("Acoustic observation refused without certified quorum.")
            return
        points = {i: (d.current_position.x, d.current_position.y)
                  for i, d in self.sim.drones.items()}
        source = (4.0, 8.0)
        rate = 48000.0
        distances = {i: math.dist(p, source) for i, p in points.items()}
        earliest = min(distances.values())
        signals = {}
        for i, distance in distances.items():
            pulse = np.zeros(16384)
            index = 256 + round(((distance - earliest) / SPEED_OF_SOUND_MPS) * rate)
            if index >= pulse.size:
                self.status.setText("Synthetic sensor window is too short.")
                return
            pulse[index] = 1.0
            signals[i] = pulse
        try:
            result = self.sim.localize_acoustic(
                signals, rate, clock_uncertainty_s=0.00001,
            )
            if result.get("detected"):
                p = result["source_position"]
                self.acoustic_label.setText(
                    f"Synthetic acoustic SOURCE XY: ({p['x']:.1f}, {p['y']:.1f}) m; "
                    f"TDOA residual {result['tdoa_residual_rmse_m']:.3f} m"
                )
                self.status.setText("Source observation processed; no automatic flight.")
            else:
                self.acoustic_label.setText("TDOA rejected: " + result.get("reason", "unknown"))
        except (ValueError, PermissionError, OSError, RuntimeError) as exc:
            self.status.setText(f"Acoustic processing refused: {exc}")
        self.refresh()

    def simulate_receiver_beacons(self):
        """Synchronized known-anchor simulation, not real satellite-free flight."""
        if not self._started or self.sim.leader() is None:
            self.status.setText("Beacon simulation refused without quorum.")
            return
        receiver_id = next((i for i in self.sim.drones
                            if not self.sim._runtimes[i]._stop.is_set()), None)
        if receiver_id is None:
            return
        position = self.sim.drones[receiver_id].current_position
        truth = (float(position.x), float(position.y))
        anchors = {11: (0., 0.), 12: (40., 0.),
                   13: (0., 40.), 14: (40., 40.)}
        schedule = {11: 0., 12: .11, 13: .23, 14: .36}
        arrivals = {
            i: schedule[i] + .05 + math.dist(truth, point) / SPEED_OF_SOUND_MPS
            for i, point in anchors.items()
        }
        try:
            result = self.sim.localize_receiver_from_beacons(
                receiver_id, anchors, schedule, arrivals, 0.00001)
            if result.get("localized"):
                point = result["receiver_position"]
                self.acoustic_label.setText(
                    f"Known-beacon receiver {receiver_id} XY: "
                    f"({point['x']:.1f}, {point['y']:.1f}) m; simulated anchors"
                )
                self.status.setText("Known-beacon XY estimate audited; flight state unchanged.")
            else:
                self.status.setText(f"Receiver estimate rejected: {result.get('reason')}")
        except (ValueError, PermissionError, RuntimeError, OSError) as exc:
            self.status.setText(f"Receiver estimate refused: {exc}")
        self.refresh()

    def measure_latency(self):
        """Measure actual signed localhost UDP RTT, not synthetic IPC values."""
        leader = self.sim.leader() if self._started else None
        if leader is None:
            self.status.setText("RTT unavailable without quorum leader.")
            return
        target = next((i for i in self.sim.drones if i != leader and
                       not self.sim._runtimes[i]._stop.is_set()), None)
        if target is None:
            return
        try:
            value = self.sim.measure_peer_rtt(target, timeout_s=1.5)
            self.sim.set_observed_latency_ms(value)
            self.rtt_label.setText(f"Measured UDP RTT leader->{target}: {value:.2f} ms")
        except (ValueError, TimeoutError, OSError) as exc:
            self.status.setText(f"RTT probe failed: {exc}")

    def fail_member(self):
        node_id = int(self.failure_member.currentText())
        if self.sim._runtimes[node_id]._stop.is_set():
            self.status.setText(f"Drone {node_id} is already offline.")
            return
        self.sim.stop_node(node_id)
        self.status.setText(f"Simulated Drone {node_id} stopped; remaining nodes must elect.")
        self.refresh()

    def closeEvent(self, event):
        self.timer.stop()
        self.sim.stop()
        event.accept()


def start_mesh_dashboard():
    import sys
    app = QApplication.instance()
    owns_application = app is None
    if owns_application:
        app = QApplication(sys.argv)
    dashboard = MeshDashboard()
    dashboard.show()
    if owns_application:
        return app.exec_()
    return dashboard


if __name__ == "__main__":
    start_mesh_dashboard()
