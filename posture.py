from __future__ import annotations

from math import atan2, degrees, hypot
from typing import Mapping

Point = Mapping[str, float]
Landmarks = Mapping[str, Point]


def _point(landmarks: Landmarks, name: str) -> Point:
    point = landmarks[name]
    if point.get("visibility", 1.0) < 0.35:
        raise ValueError(f"The {name.replace('_', ' ')} landmark is not visible")
    return point


def _midpoint(first: Point, second: Point) -> tuple[float, float]:
    return (first["x"] + second["x"]) / 2, (first["y"] + second["y"]) / 2


def _pair(landmarks: Landmarks, left: str, right: str, view: str) -> tuple[Point, Point]:
    if view == "side":
        name = max((left, right), key=lambda item: landmarks.get(item, {}).get("visibility", 1.0))
        point = _point(landmarks, name)
        return point, point
    return _point(landmarks, left), _point(landmarks, right)


def analyze_landmarks(landmarks: Landmarks, view: str = "front") -> dict[str, object]:
    """Score normalized MediaPipe landmarks and return readable posture feedback."""
    if view not in {"front", "side"}:
        raise ValueError("View must be 'front' or 'side'")

    left_ear, right_ear = _pair(landmarks, "left_ear", "right_ear", view)
    left_shoulder, right_shoulder = _pair(landmarks, "left_shoulder", "right_shoulder", view)
    left_hip, right_hip = _pair(landmarks, "left_hip", "right_hip", view)
    ear_x, _ = _midpoint(left_ear, right_ear)
    shoulder_x, shoulder_y = _midpoint(left_shoulder, right_shoulder)
    hip_x, hip_y = _midpoint(left_hip, right_hip)
    torso_length = hypot(hip_x - shoulder_x, hip_y - shoulder_y)
    if torso_length < 0.05:
        raise ValueError("Move back until your shoulders and hips are visible")

    torso_lean = degrees(atan2(abs(hip_x - shoulder_x), abs(hip_y - shoulder_y)))
    if view == "side":
        head_deviation = abs(ear_x - shoulder_x) / torso_length
        shoulder_level = hip_level = None
        head_limit = 0.18
        head_label = "Head offset vs. torso"
    else:
        shoulder_width = hypot(right_shoulder["x"] - left_shoulder["x"], right_shoulder["y"] - left_shoulder["y"])
        if shoulder_width < 0.05:
            raise ValueError("Face the camera and keep both shoulders in view")
        head_deviation = abs(ear_x - shoulder_x) / shoulder_width
        shoulder_level = abs(degrees(atan2(right_shoulder["y"] - left_shoulder["y"], right_shoulder["x"] - left_shoulder["x"])))
        left_hip_point, right_hip_point = _point(landmarks, "left_hip"), _point(landmarks, "right_hip")
        hip_level = abs(degrees(atan2(right_hip_point["y"] - left_hip_point["y"], right_hip_point["x"] - left_hip_point["x"])))
        head_limit = 0.16
        head_label = "Head offset vs. shoulders"

    issues: list[str] = []
    if head_deviation > head_limit:
        issues.append("Bring your head back over your shoulders")
    if torso_lean > 12:
        issues.append("Stack your shoulders above your hips")
    if shoulder_level is not None and shoulder_level > 7:
        issues.append("Level your shoulders")
    if hip_level is not None and hip_level > 7:
        issues.append("Level your hips")

    head_penalty = min(35, max(0, (head_deviation - head_limit) * 110))
    torso_penalty = min(35, max(0, (torso_lean - 8) * 1.5))
    balance_penalty = sum(min(15, max(0, (angle - 4) * 1.2)) for angle in (shoulder_level, hip_level) if angle is not None)
    score = max(0, round(100 - head_penalty - torso_penalty - balance_penalty))

    return {
        "detected": True,
        "status": "aligned" if score >= 82 else "adjust",
        "score": score,
        "confidence": round(sum(point.get("visibility", 1.0) for point in (left_ear, right_ear, left_shoulder, right_shoulder, left_hip, right_hip)) / 6 * 100),
        "feedback": issues or ["Good alignment. Keep this position."],
        "measurements": {
            "head_deviation": round(head_deviation * 100),
            "head_label": head_label,
            "torso_lean": round(torso_lean),
            "shoulder_level": round(shoulder_level) if shoulder_level is not None else None,
            "hip_level": round(hip_level) if hip_level is not None else None,
        },
        "landmarks": {
            "left_ear": dict(left_ear), "right_ear": dict(right_ear),
            "left_shoulder": dict(left_shoulder), "right_shoulder": dict(right_shoulder),
            "left_hip": dict(left_hip), "right_hip": dict(right_hip),
        },
    }