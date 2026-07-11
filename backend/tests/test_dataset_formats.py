import math
import unittest

from app.services.dataset_builder import _label_line


class DatasetFormatTests(unittest.TestCase):
    def test_obb_exports_four_rotated_corners_without_comments(self) -> None:
        line = _label_line(
            {"task": "obb"},
            {"points": [[0.25, 0.25], [0.75, 0.75]], "rotation": 45},
            2,
        )
        tokens = line.split()
        self.assertEqual(len(tokens), 9)
        self.assertEqual(tokens[0], "2")
        self.assertNotIn("#", line)
        coordinates = [float(value) for value in tokens[1:]]
        self.assertTrue(all(math.isfinite(value) and 0 <= value <= 1 for value in coordinates))

    def test_pose_includes_derived_bounding_box_before_keypoints(self) -> None:
        line = _label_line(
            {"task": "pose"},
            {"points": [[0.25, 0.25], [0.75, 0.75]], "visibility": [2, 2]},
            0,
        )
        tokens = line.split()
        self.assertEqual(len(tokens), 11)
        self.assertEqual(tokens[0], "0")
        self.assertEqual(tokens[5:], ["0.250000", "0.250000", "2", "0.750000", "0.750000", "2"])


if __name__ == "__main__":
    unittest.main()
