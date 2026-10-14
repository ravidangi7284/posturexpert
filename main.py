from __future__ import annotations

import base64
import binascii
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from posture import analyze_landmarks

POSE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
POSE_MODEL_PATH = Path.home() / ".cache" / "posturexpert" / "pose_landmarker_lite.task"
_pose_lock = Lock()
VISION_ERROR: str | None = None


def _download_pose_model() -> None:
    POSE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if POSE_MODEL_PATH.exists():
        return
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=POSE_MODEL_PATH.parent, suffix=".task", delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            with urlopen(POSE_MODEL_URL, timeout=30) as response:
                shutil.copyfileobj(response, temporary_file)
        os.replace(temporary_path, POSE_MODEL_PATH)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


try:
    import cv2
    import mediapipe as mp
    import numpy as np

    if hasattr(mp, "solutions"):
        _pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        VISION_BACKEND = "solutions"
    else:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        _download_pose_model()
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(POSE_MODEL_PATH)),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=0.55,
            min_pose_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        _pose = mp_vision.PoseLandmarker.create_from_options(options)
        VISION_BACKEND = "tasks"
    VISION_AVAILABLE = True
except Exception as error:
    cv2 = mp = np = _pose = None
    VISION_AVAILABLE = False
    VISION_BACKEND = None
    VISION_ERROR = str(error)

ROOT = Path(__file__).parent
app = FastAPI(title="PostureXpert", version="1.0.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class FrameRequest(BaseModel):
    image: str
    view: str = "front"


class LandmarkRequest(BaseModel):
    landmarks: dict[str, dict[str, float]]
    view: str = "front"


@app.get("/")
def home() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "vision_available": VISION_AVAILABLE,
        "vision_backend": VISION_BACKEND,
        "vision_error": VISION_ERROR,
    }


@app.post("/api/analyze/landmarks")
def analyze_coordinates(request: LandmarkRequest) -> dict[str, object]:
    try:
        return analyze_landmarks(request.landmarks, request.view)
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/analyze")
def analyze_frame(request: FrameRequest) -> dict[str, object]:
    if not VISION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Vision dependencies are unavailable. Install requirements with Python 3.12.")
    if request.view not in {"front", "side"}:
        raise HTTPException(status_code=422, detail="View must be 'front' or 'side'")
    try:
        image_bytes = base64.b64decode(request.image, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=422, detail="Image must be valid base64 JPEG data") from error
    if len(image_bytes) > 5_000_000:
        raise HTTPException(status_code=413, detail="Image exceeds the 5 MB limit")

    frame = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=422, detail="Could not decode camera image")
    frame = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_AREA)
    names = {"left_ear": 7, "right_ear": 8, "left_shoulder": 11, "right_shoulder": 12, "left_hip": 23, "right_hip": 24}
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    with _pose_lock:
        if VISION_BACKEND == "solutions":
            result = _pose.process(rgb_frame)
            points = result.pose_landmarks.landmark if result.pose_landmarks else None
        else:
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            result = _pose.detect(image)
            points = result.pose_landmarks[0] if result.pose_landmarks else None
    if points is None:
        return {"detected": False, "status": "searching", "feedback": ["Step into view, head to hips."], "landmarks": {}}
    landmarks = {name: {"x": points[index].x, "y": points[index].y, "visibility": points[index].visibility} for name, index in names.items()}
    try:
        return analyze_landmarks(landmarks, request.view)
    except ValueError as error:
        return {"detected": False, "status": "searching", "feedback": [str(error)], "landmarks": {}}