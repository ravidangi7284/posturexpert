import unittest

from posture import analyze_landmarks


def make_pose(ear_x: float = 0.5) -> dict[str, dict[str, float]]:
    return {
        "left_ear": {"x": ear_x - 0.08, "y": 0.2},
        "right_ear": {"x": ear_x + 0.08, "y": 0.2},
        "left_shoulder": {"x": 0.4, "y": 0.35},
        "right_shoulder": {"x": 0.6, "y": 0.35},
        "left_hip": {"x": 0.43, "y": 0.65},
        "right_hip": {"x": 0.57, "y": 0.65},
    }


class PostureAnalysisTests(unittest.TestCase):
    def test_centered_frontal_pose_is_aligned(self) -> None:
        result = analyze_landmarks(make_pose())
        self.assertEqual(result["status"], "aligned")
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["confidence"], 100)

    def test_forward_head_gets_specific_feedback(self) -> None:
        result = analyze_landmarks(make_pose(ear_x=0.57))
        self.assertEqual(result["status"], "adjust")
        self.assertIn("Bring your head back over your shoulders", result["feedback"])

    def test_side_view_uses_the_most_visible_side(self) -> None:
        pose = make_pose()
        for name in ("left_ear", "left_shoulder", "left_hip"):
            pose[name]["visibility"] = 0.1
        result = analyze_landmarks(pose, view="side")
        self.assertTrue(result["detected"])
        self.assertIsNone(result["measurements"]["shoulder_level"])


if __name__ == "__main__":
    unittest.main()