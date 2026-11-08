"""Opt-in PyQt5 swarm coordination dashboard, strictly simulation-only.

This is a separate mode of the existing application. It does not start the
legacy SwarmManager/GUI path and cannot connect to physical UAVs.
"""
from __future__ import annotations

import math
from typing import Optional

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
        for widget in (self.leader_label, self.quorum_label, self.nodes_label):
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
        content.addWidget(actions)

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
