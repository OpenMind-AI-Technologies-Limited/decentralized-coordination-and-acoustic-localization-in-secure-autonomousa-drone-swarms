"""Offscreen smoke tests for the opt-in, simulation-only coordination GUI."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from swarm_dashboard import MeshDashboard, create_dashboard_swarm


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["mesh-dashboard-test"])

    def test_renders_four_registered_drone_rows_and_refuses_no_quorum(self):
        dashboard = MeshDashboard(auto_start=False)
        try:
            self.assertEqual(dashboard.table.rowCount(), 4)
            self.assertTrue(hasattr(dashboard, "audit_label"))
            self.assertTrue(hasattr(dashboard, "acoustic_button"))
            self.assertTrue(hasattr(dashboard, "beacon_button"))
            self.assertTrue(hasattr(dashboard, "rtt_button"))
            self.assertFalse(dashboard.acoustic_button.isEnabled())
            self.assertFalse(dashboard.beacon_button.isEnabled())
            self.assertFalse(dashboard.rtt_button.isEnabled())
            self.assertFalse(dashboard.formation_button.isEnabled())
            self.assertFalse(dashboard.tasks_button.isEnabled())
            self.assertIn("no certified quorum", dashboard.leader_label.text())
            dashboard.send_formation()
            self.assertIn("refused", dashboard.status.text())
        finally:
            dashboard.close()

    def test_no_hardware_connection_and_local_teardown(self):
        simulation = create_dashboard_swarm()
        self.assertTrue(all(not drone.use_real_drone for drone in simulation.drones.values()))
        dashboard = MeshDashboard(simulation=simulation, auto_start=False)
        dashboard.close()
        self.assertTrue(all(rt._stop.is_set() or not rt._thread
                            for rt in simulation._runtimes.values()))


if __name__ == "__main__":
    unittest.main()
