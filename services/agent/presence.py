"""Webcam presence: is someone at the desk? (idea from Birdy: "person not seen for a while = away").

Opt-in only (ITOR_WEBCAM_PRESENCE=1, set by the app when the employee turns it on).
Everything stays on this PC: frames are analysed in memory and dropped right away. Nothing is saved or sent;
the only output is "present" or "away".

Detection: MediaPipe face detector (works at screen distance); the pose model is a backup, for example when the
head is turned. Both run on the CPU, one frame every 2 seconds.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

PresenceState = Literal["off", "starting", "present", "away", "no_camera", "error"]
MODELS = Path(__file__).with_name("models")


class PresenceReport(BaseModel):
    enabled: bool
    state: PresenceState
    seconds_since_seen: float | None = None
    detail: str = ""


def _stub_matplotlib() -> None:
    """MediaPipe's vision package imports its drawing helpers, which import matplotlib.pyplot.
    itor never draws anything, so the packed helper ships without matplotlib (~15 MB) and gets an empty stand-in."""
    try:
        import matplotlib.pyplot  # noqa: F401
    except ImportError:
        import types
        package = types.ModuleType("matplotlib")
        package.__path__ = []  # mark it as a package
        pyplot = types.ModuleType("matplotlib.pyplot")
        package.pyplot = pyplot
        sys.modules.setdefault("matplotlib", package)
        sys.modules.setdefault("matplotlib.pyplot", pyplot)


class MediaPipeDetector:
    """Face first, pose as a backup. Loaded only when presence is turned on (MediaPipe is heavy)."""

    def __init__(self) -> None:
        os.environ.setdefault("GLOG_minloglevel", "3")
        _stub_matplotlib()
        import mediapipe as mp
        from mediapipe.tasks.python.core import base_options
        from mediapipe.tasks.python.vision import face_detector, pose_landmarker
        self.mp = mp
        self.face = face_detector.FaceDetector.create_from_options(face_detector.FaceDetectorOptions(
            base_options=base_options.BaseOptions(model_asset_path=str(MODELS / "blaze_face_short_range.tflite")),
            min_detection_confidence=0.5))
        self.pose = pose_landmarker.PoseLandmarker.create_from_options(pose_landmarker.PoseLandmarkerOptions(
            base_options=base_options.BaseOptions(model_asset_path=str(MODELS / "pose_landmarker_lite.task")),
            num_poses=1))

    def __call__(self, rgb_frame: Any) -> bool:
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb_frame)
        if self.face.detect(image).detections:
            return True
        landmarks = self.pose.detect(image).pose_landmarks
        # Nose or a shoulder clearly visible counts as someone there (Birdy's posture landmarks).
        return bool(landmarks) and max(landmarks[0][i].visibility for i in (0, 11, 12)) >= 0.5

    def close(self) -> None:
        self.face.close()
        self.pose.close()


class WebcamSource:
    """Opens the default webcam. The camera light stays on while presence is on: a visible signal."""

    def __init__(self, index: int = 0) -> None:
        import cv2
        self.cv2 = cv2
        self.camera = cv2.VideoCapture(index, cv2.CAP_DSHOW if sys.platform == "win32" else 0)
        if not self.camera.isOpened():
            raise OSError("No webcam available.")
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:  # warm-up: the first frames are dark
            self.camera.read()

    def __call__(self) -> Any | None:
        ok, frame = self.camera.read()
        return self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB) if ok else None

    def close(self) -> None:
        self.camera.release()


class PresenceWatcher:
    def __init__(
        self, enabled: bool, interval: float = 2.0, away_after: float = 10.0,
        source_factory: Callable[[], Any] = WebcamSource, detector_factory: Callable[[], Any] = MediaPipeDetector,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.enabled = enabled
        self.interval = interval
        self.away_after = away_after
        self.source_factory = source_factory
        self.detector_factory = detector_factory
        self.clock = clock
        self.state: PresenceState = "starting" if enabled else "off"
        self.detail = ""
        self.last_seen: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="itor-presence", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def observe(self, seen: bool) -> None:
        """Birdy's rule: seen = present; not seen for `away_after` seconds = away."""
        now = self.clock()
        if seen:
            self.last_seen = now
            self.state = "present"
        elif self.last_seen is None or now - self.last_seen >= self.away_after:
            self.state = "away"

    def _run(self) -> None:
        source = detector = None
        try:
            try:
                source = self.source_factory()
            except Exception:  # noqa: BLE001 - any camera problem: report it, keep itor running
                self.state, self.detail = "no_camera", "No webcam could be opened."
                return
            detector = self.detector_factory()
            while not self._stop.is_set():
                frame = source()
                if frame is not None:
                    self.observe(bool(detector(frame)))
                    del frame  # never kept
                self._stop.wait(self.interval)
        except Exception as error:  # noqa: BLE001
            self.state, self.detail = "error", f"Presence detection stopped: {type(error).__name__}: {error}"[:200]
        finally:
            if detector is not None:
                detector.close()
            if source is not None:
                source.close()

    def idle_seconds(self) -> float | None:
        """For the time clock: 0 when someone is at the desk, time since last seen when away, None if unknown."""
        if self.state == "present":
            return 0.0
        if self.state == "away" and self.last_seen is not None:
            return self.clock() - self.last_seen
        if self.state == "away":
            return self.away_after
        return None

    def report(self) -> PresenceReport:
        since = None if self.last_seen is None else round(self.clock() - self.last_seen, 1)
        return PresenceReport(enabled=self.enabled, state=self.state, seconds_since_seen=since, detail=self.detail)


def combined_idle(keyboard: Callable[[], float | None], presence: PresenceWatcher) -> Callable[[], float | None]:
    """Idle time for the time clock: the shorter of 'no mouse/keyboard' and 'nobody seen on the webcam'.

    Someone reading or on a call in front of the PC counts as active, even without touching the mouse.
    """
    def idle() -> float | None:
        keys = keyboard()
        camera = presence.idle_seconds()
        if camera is None:
            return keys
        if keys is None:
            return camera
        return min(keys, camera)
    return idle
