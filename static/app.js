const video = document.querySelector("#camera");
const canvas = document.querySelector("#overlay");
const context = canvas.getContext("2d");
const stage = document.querySelector("#camera-stage");
const startButton = document.querySelector("#start-button");
const endButton = document.querySelector("#end-button");
const placeholder = document.querySelector("#camera-placeholder");
const frameMessage = document.querySelector("#frame-message");
const pointNames = ["left_ear", "right_ear", "left_shoulder", "right_shoulder", "left_hip", "right_hip"];
let view = "front";
let stream;
let active = false;
let sessionStartedAt = 0;
let alignedCount = 0;
let adjustmentCount = 0;
let timerId;
let hideMessageId;

function setText(id, value) { document.querySelector(`#${id}`).textContent = value; }

function updateClock() {
  const now = new Date();
  setText("clock", new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(now));
  setText("snapshot-date", new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(now).toUpperCase());
}

function formatTime(totalSeconds) {
  return `${Math.floor(totalSeconds / 60).toString().padStart(2, "0")}:${(totalSeconds % 60).toString().padStart(2, "0")}`;
}

function updateSessionTime() {
  if (!active) return;
  const elapsed = Math.floor((Date.now() - sessionStartedAt) / 1000);
  setText("session-time", formatTime(elapsed));
  setText("snapshot-time", formatTime(elapsed));
}

function showMessage(message) {
  frameMessage.textContent = message;
  frameMessage.style.display = "block";
  clearTimeout(hideMessageId);
  hideMessageId = setTimeout(() => { frameMessage.style.display = "none"; }, 3200);
}

function clearOverlay() { context.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight); }

function drawLandmarks(landmarks) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  clearOverlay();
  context.lineWidth = Math.max(2, width / 240);
  context.strokeStyle = "rgba(178,223,199,.8)";
  context.fillStyle = "#f0a079";
  const links = [["left_ear", "left_shoulder"], ["right_ear", "right_shoulder"], ["left_shoulder", "right_shoulder"], ["left_shoulder", "left_hip"], ["right_shoulder", "right_hip"], ["left_hip", "right_hip"]];
  for (const [first, second] of links) {
    const a = landmarks[first];
    const b = landmarks[second];
    if (!a || !b) continue;
    context.beginPath();
    context.moveTo((1 - a.x) * width, a.y * height);
    context.lineTo((1 - b.x) * width, b.y * height);
    context.stroke();
  }
  for (const name of pointNames) {
    const point = landmarks[name];
    if (!point || point.visibility < 0.35) continue;
    context.beginPath();
    context.arc((1 - point.x) * width, point.y * height, Math.max(3, width / 100), 0, Math.PI * 2);
    context.fill();
  }
}

function setMeasurement(id, value, suffix = "°") {
  setText(id, value === null || value === undefined ? "--" : `${value}${suffix}`);
}

function renderResult(result) {
  if (!result.detected) {
    setText("pose-confidence", "POSE --%");
    const tag = document.querySelector("#result-tag");
    tag.className = "result-tag";
    tag.innerHTML = '<span class="tag-dot"></span>SEARCHING';
    document.querySelector("#score-value").firstChild.textContent = "--";
    setText("score-caption", "Move into frame for an assessment");
    setText("feedback-title", "Finding your alignment");
    setText("feedback-copy", result.feedback?.[0] || "Step back until your head and hips are visible.");
    setText("head-note", "Awaiting detection");
    setText("torso-note", "Awaiting detection");
    setText("shoulder-note", view === "front" ? "Awaiting detection" : "Front view only");
    clearOverlay();
    return;
  }

  if (result.status === "aligned") alignedCount += 1;
  else adjustmentCount += 1;
  const measurements = result.measurements;
  const isGood = result.status === "aligned";
  const tag = document.querySelector("#result-tag");
  tag.className = `result-tag ${isGood ? "is-good" : "is-adjust"}`;
  tag.innerHTML = `<span class="tag-dot"></span>${isGood ? "ON TRACK" : "ADJUST"}`;
  document.querySelector("#score-value").firstChild.textContent = `${result.score}`;
  setText("score-caption", isGood ? "Your alignment is looking steady" : "A small adjustment can help");
  const fill = document.querySelector("#score-track-fill");
  fill.style.width = `${result.score}%`;
  fill.classList.toggle("is-adjust", !isGood);
  setText("pose-confidence", `POSE ${result.confidence}%`);
  setMeasurement("head-value", measurements.head_deviation, "%");
  setText("head-note", measurements.head_label);
  setMeasurement("torso-value", measurements.torso_lean);
  setText("torso-note", measurements.torso_lean <= 12 ? "Within target" : "Lean detected");
  setMeasurement("shoulder-value", measurements.shoulder_level);
  setText("shoulder-note", view === "front" ? "Left-to-right balance" : "Front view only");
  setText("snapshot-aligned", alignedCount);
  setText("snapshot-adjustments", adjustmentCount);
  setText("feedback-title", isGood ? "Nice alignment" : "Try this next");
  setText("feedback-copy", result.feedback[0]);
  const panel = document.querySelector("#feedback-panel");
  panel.classList.toggle("is-good", isGood);
  panel.classList.toggle("is-adjust", !isGood);
  setText("feedback-icon", isGood ? "✓" : "↗");
  drawLandmarks(result.landmarks);
}

async function analyzeLoop() {
  if (!active || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    if (active) setTimeout(analyzeLoop, 250);
    return;
  }
  const capture = document.createElement("canvas");
  capture.width = 640;
  capture.height = 480;
  capture.getContext("2d").drawImage(video, 0, 0, capture.width, capture.height);
  const image = capture.toDataURL("image/jpeg", 0.72).split(",")[1];
  try {
    const response = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image, view }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Analysis request failed");
    renderResult(result);
  } catch (error) {
    showMessage(error.message || "Could not analyze this frame.");
    endSession();
    return;
  }
  if (active) setTimeout(analyzeLoop, 600);
}

async function startSession() {
  if (active) return;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } }, audio: false });
    video.srcObject = stream;
    await video.play();
  } catch (error) {
    showMessage(error.name === "NotAllowedError" ? "Camera access was blocked. Allow access in your browser settings." : "No camera found. Connect a camera and try again.");
    return;
  }
  active = true;
  sessionStartedAt = Date.now();
  alignedCount = adjustmentCount = 0;
  setText("snapshot-aligned", "0");
  setText("snapshot-adjustments", "0");
  stage.classList.add("has-camera");
  document.querySelector(".session-chip").classList.add("is-live");
  document.querySelector("#live-indicator").classList.add("is-live");
  document.querySelector(".rec-dot").classList.add("is-live");
  setText("camera-state", "ASSESSMENT LIVE");
  setText("record-label", "LIVE");
  setText("session-label", "SESSION LIVE");
  startButton.disabled = true;
  endButton.disabled = false;
  timerId = setInterval(updateSessionTime, 1000);
  updateSessionTime();
  analyzeLoop();
}

function endSession() {
  if (!active) return;
  active = false;
  clearInterval(timerId);
  if (stream) stream.getTracks().forEach((track) => track.stop());
  video.srcObject = null;
  stream = undefined;
  stage.classList.remove("has-camera");
  document.querySelector(".session-chip").classList.remove("is-live");
  document.querySelector("#live-indicator").classList.remove("is-live");
  document.querySelector(".rec-dot").classList.remove("is-live");
  setText("camera-state", "CAMERA STANDBY");
  setText("record-label", "STANDBY");
  setText("session-label", "SESSION READY");
  setText("pose-confidence", "POSE --%");
  startButton.disabled = false;
  endButton.disabled = true;
  clearOverlay();
}

document.querySelectorAll(".view-button").forEach((button) => button.addEventListener("click", () => {
  view = button.dataset.view;
  document.querySelectorAll(".view-button").forEach((item) => {
    const selected = item === button;
    item.classList.toggle("is-active", selected);
    item.setAttribute("aria-pressed", String(selected));
  });
  setText("camera-hint", view === "front" ? "Face the camera, relax your shoulders, and keep your hips in view." : "Turn side-on to the camera. Keep your head, shoulder, and hip in view.");
}));
startButton.addEventListener("click", startSession);
endButton.addEventListener("click", endSession);

function resizeOverlay() {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
}

window.addEventListener("resize", resizeOverlay);

async function checkVisionRuntime() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    const mark = document.querySelector(".processing-mark");
    if (health.vision_available) {
      mark.classList.add("is-ready");
      setText("runtime-label", "VISION ENGINE READY");
    } else {
      mark.classList.add("is-missing");
      setText("runtime-label", "VISION ENGINE UNAVAILABLE");
      placeholder.querySelector(".camera-note").textContent = "Install the vision dependencies to enable live analysis";
      startButton.disabled = true;
      startButton.title = "The vision runtime is not installed";
      setText("feedback-title", "Vision engine unavailable");
      setText("feedback-copy", "Install requirements with Python 3.12, then restart the service.");
      setText("camera-hint", "Live posture analysis needs the OpenCV and MediaPipe runtime.");
    }
  } catch {
    setText("runtime-label", "API CONNECTION LOST");
  }
}

updateClock();
setInterval(updateClock, 30_000);
resizeOverlay();
checkVisionRuntime();