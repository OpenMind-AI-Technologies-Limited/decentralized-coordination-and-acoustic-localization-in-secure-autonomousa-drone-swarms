"""Telemetry regression validation gates never bypass deterministic flight safety."""
import math
import tempfile
import unittest

from drone import Drone, Position
from ml_system import PhysicalMLTrainer
from swarm_model_validation import model_readiness, velocity_advisory
from swarm_safety import SimulatedMotionSafety


class ModelValidationTests(unittest.TestCase):
    def test_untrained_model_does_not_issue_velocity_advisory(self):
        with tempfile.TemporaryDirectory() as tmp:
            trainer = PhysicalMLTrainer(owner_id=88, model_dir=tmp)
            status = velocity_advisory(trainer, [90, 95, 80, 10, 0, 0, 0])
            self.assertFalse(status["ready_for_advisory"])
            self.assertTrue(status["advisory_only"])

    def test_holdout_validated_model_yields_bounded_advisory(self):
        with tempfile.TemporaryDirectory() as tmp:
            trainer = PhysicalMLTrainer(owner_id=89, model_dir=tmp)
            for i in range(120):
                x = [
                    70 + 0.05 * i,
                    80 + math.sin(i * .2),
                    60 + math.cos(i * .17),
                    10 + .02 * i,
                    math.sin(i * .15),
                    math.cos(i * .13),
                    i * .001,
                ]
                y = [.5 * x[4] + .1 * x[5], -.2 * x[5], .05 * x[6]]
                trainer.ingest_sample(x, y)
            self.assertTrue(trainer.train(min_samples=80, poly_degree=1))
            readiness = model_readiness(trainer)
            self.assertTrue(readiness["ready_for_advisory"], readiness)
            self.assertFalse(readiness["collision_classifier"])
            advice = velocity_advisory(trainer, x, max_speed_mps=1.5)
            self.assertTrue(advice["ready_for_advisory"])
            self.assertLessEqual(math.dist(advice["velocity_xyz_mps"], (0, 0, 0)), 1.5)

            # An accepted model must never override a non-ML collision veto.
            drone = Drone(1, Position(0, 0, 0))
            drone.current_position = Position(0, 0, 10)
            guard = SimulatedMotionSafety()
            guard.add_obstacle((5, 0, 10), 4)
            self.assertFalse(guard.assess(drone, (12, 0, 10), {}).allowed)

    def test_corrupt_quality_metrics_are_rejected(self):
        class Fake:
            weights = [[0, 0, 0], [0, 0, 0]]
            training_metrics = {"samples": 200, "val_samples": 20, "val_mse": float("nan")}
        self.assertFalse(model_readiness(Fake())["ready_for_advisory"])


if __name__ == "__main__":
    unittest.main()
