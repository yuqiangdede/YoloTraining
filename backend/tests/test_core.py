import tempfile
import unittest
from pathlib import Path

from app.core.paths import ProjectPaths
from app.schemas.annotations import AnnotationDocument, AnnotationShape, TaskType
from app.services.state_machine import InvalidTransition, JobStatus, transition


class ProjectPathsTests(unittest.TestCase):
    def test_resolves_only_project_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = ProjectPaths(Path(tmp))
            self.assertEqual(paths.resolve("uploads/a.jpg"), Path(tmp) / "uploads/a.jpg")
            with self.assertRaises(ValueError):
                paths.resolve("../outside.jpg")
            with self.assertRaises(ValueError):
                paths.resolve("C:/outside.jpg")


class AnnotationValidationTests(unittest.TestCase):
    def test_detection_requires_two_normalized_points(self) -> None:
        document = AnnotationDocument(
            asset_id="asset-1",
            task=TaskType.DETECT,
            image_width=640,
            image_height=480,
            shapes=[
                AnnotationShape(
                    id="shape-1",
                    label_id="car",
                    kind="rectangle",
                    points=[[0.1, 0.2], [0.5, 0.8]],
                )
            ],
        )
        self.assertEqual(document.shapes[0].kind, "rectangle")

    def test_rejects_out_of_bounds_points(self) -> None:
        with self.assertRaises(ValueError):
            AnnotationDocument(
                asset_id="asset-1",
                task=TaskType.OBB,
                image_width=640,
                image_height=480,
                shapes=[
                    AnnotationShape(
                        id="shape-1",
                        label_id="car",
                        kind="obb",
                        points=[[0.1, 0.2], [1.2, 0.8]],
                        rotation=10,
                    )
                ],
            )


class StateMachineTests(unittest.TestCase):
    def test_pause_and_resume_are_safe_transitions(self) -> None:
        self.assertEqual(transition(JobStatus.RUNNING, JobStatus.PAUSING), JobStatus.PAUSING)
        self.assertEqual(transition(JobStatus.PAUSING, JobStatus.PAUSED), JobStatus.PAUSED)
        self.assertEqual(transition(JobStatus.PAUSED, JobStatus.QUEUED), JobStatus.QUEUED)

    def test_terminal_job_cannot_restart(self) -> None:
        with self.assertRaises(InvalidTransition):
            transition(JobStatus.SUCCEEDED, JobStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
