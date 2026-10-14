# PostureXpert

A real-time posture assessment prototype built with FastAPI, OpenCV, and MediaPipe. It analyzes camera frames locally, scores visible head and torso alignment, and returns concise adjustment feedback.

## Run locally

Requires Python 3.12 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open `http://127.0.0.1:8000` and allow camera access. On first launch, the MediaPipe Tasks API downloads its pose model into the user's cache directory. The model is not stored in this repository.

## API

- `GET /api/health` reports service and pose-engine status.
- `POST /api/analyze` accepts a base64-encoded JPEG frame and a `front` or `side` view.
- `POST /api/analyze/landmarks` accepts normalized pose landmarks for direct scoring and integration tests.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Scores use heuristic alignment thresholds and are not a medical diagnosis. When run locally, camera frames are sent to the local FastAPI service for analysis.