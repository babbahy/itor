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

from .posture import Calibration, Posture, analyse, measures

PresenceState = Literal["off", "starting", "present", "away", "no_camera", "error"]
MODELS = Path(__file__).with_name("models")
HEAD_DOWN = 0.4  # head pitch above the usual one by this much = looking down (phone on the lap or desk)


def head_pitch(keypoints: list[tuple[float, float]] | None) -> float | None:
    """How far the head is tilted down, from the 6 face points (eyes, nose, mouth, ears).

    When the head tilts down, the nose goes down and the ears go up in the image. Divided by the eye distance,
    so it does not depend on how far the person sits. Bigger = looking further down.
    """
    if not keypoints or len(keypoints) < 6:
        return None
    (rx, ry), (lx, ly), (_, nose_y) = keypoints[0], keypoints[1], keypoints[2]
    eyes = abs(rx - lx)
    if eyes < 1e-3:
        return None
    ear_y = (keypoints[4][1] + keypoints[5][1]) / 2
    return (nose_y - ear_y) / eyes


class Landmark(BaseModel):
    x: float
    y: float
    v: float


class PresenceFrame(BaseModel):
    """Live preview for the Camera tab. Mirrored (selfie view). Only kept in memory while the tab is open."""
    state: PresenceState
    jpeg_base64: str | None = None
    width: int = 0
    height: int = 0
    landmarks: list[Landmark] = []
    face: list[float] | None = None  # x, y, w, h in 0..1
    posture: Posture | None = None
    looking_down: bool = False


class PresenceReport(BaseModel):
    enabled: bool
    state: PresenceState
    seconds_since_seen: float | None = None
    # Seconds the person has been looking down / away from the screen (phone). Only for a private reminder
    # on this PC: never stored, never sent, never counted in the time clock.
    looking_down_seconds: float = 0.0
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
        return self.analyse(rgb_frame, with_pose=False)[0]

    def analyse(self, rgb_frame: Any, with_pose: bool) -> tuple[bool, list[tuple[float, float, float]] | None, list[float] | None, float | None]:
        """(someone there, pose points, face box, head pitch). The pose model runs only when needed (preview, or no face)."""
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb_frame)
        faces = self.face.detect(image).detections
        face = pitch = None
        if faces:
            box = faces[0].bounding_box
            h, w = rgb_frame.shape[0], rgb_frame.shape[1]
            face = [box.origin_x / w, box.origin_y / h, box.width / w, box.height / h]
            pitch = head_pitch([(k.x, k.y) for k in faces[0].keypoints or []])
        points = None
        if with_pose or not faces:
            landmarks = self.pose.detect(image).pose_landmarks
            if landmarks:
                points = [(p.x, p.y, p.visibility) for p in landmarks[0]]
        # Face, or nose / a shoulder clearly visible, counts as someone there (Birdy's landmarks).
        seen = bool(faces) or (points is not None and max(points[i][2] for i in (0, 11, 12)) >= 0.5)
        return seen, points, face, pitch

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
        # Camera tab: faster frames and a mirrored preview, only while it is being looked at.
        self.preview_until = 0.0
        self.calibration: Calibration | None = None
        self._frame: PresenceFrame | None = None
        self._last_points: list[tuple[float, float, float]] | None = None
        self._lock = threading.Lock()
        # Looking down (phone): the usual head pitch is learned while looking at the screen.
        self.head_baseline: float | None = None
        self.head_calibrated = False
        self.down_since: float | None = None
        self._last_pitch: float | None = None

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

    def observe_head(self, seen: bool, has_face: bool, pitch: float | None) -> None:
        """Seen but face not visible (head down or turned) or head clearly tilted down = looking away from the screen."""
        now = self.clock()
        self._last_pitch = pitch
        if not seen:
            self.down_since = None
            return
        down = not has_face or (pitch is not None and self.head_baseline is not None and pitch > self.head_baseline + HEAD_DOWN)
        if has_face and pitch is not None and not down and not self.head_calibrated:
            # Slowly learn the usual "looking at the screen" pitch.
            self.head_baseline = pitch if self.head_baseline is None else 0.9 * self.head_baseline + 0.1 * pitch
        if down:
            self.down_since = self.down_since if self.down_since is not None else now
        else:
            self.down_since = None

    def looking_down_seconds(self) -> float:
        if self.state != "present" or self.down_since is None:
            return 0.0
        return round(self.clock() - self.down_since, 1)

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
                previewing = self.clock() < self.preview_until
                frame = source()
                if frame is not None:
                    if previewing and hasattr(detector, "analyse"):
                        seen, points, face, pitch = detector.analyse(frame, with_pose=True)
                        self.observe(seen)
                        self.observe_head(seen, face is not None, pitch)
                        self._store_preview(frame, points, face)
                    elif hasattr(detector, "analyse"):
                        seen, _, face, pitch = detector.analyse(frame, with_pose=False)
                        self.observe(seen)
                        self.observe_head(seen, face is not None, pitch)
                        with self._lock:
                            self._frame = None  # preview closed: drop the last image
                    else:
                        self.observe(bool(detector(frame)))
                        with self._lock:
                            self._frame = None  # preview closed: drop the last image
                    del frame  # never kept beyond the preview
                self._stop.wait(0.12 if previewing else self.interval)
        except Exception as error:  # noqa: BLE001
            self.state, self.detail = "error", f"Presence detection stopped: {type(error).__name__}: {error}"[:200]
        finally:
            if detector is not None:
                detector.close()
            if source is not None:
                source.close()

    def _store_preview(self, rgb: Any, points: list[tuple[float, float, float]] | None, face: list[float] | None) -> None:
        import base64

        import cv2
        mirrored = cv2.flip(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), 1)
        ok, jpeg = cv2.imencode(".jpg", mirrored, [cv2.IMWRITE_JPEG_QUALITY, 70])
        flipped_points = [(1 - x, y, v) for x, y, v in points] if points else None
        flipped_face = [1 - face[0] - face[2], face[1], face[2], face[3]] if face else None
        with self._lock:
            self._last_points = points
            self._frame = PresenceFrame(
                state=self.state, jpeg_base64=base64.b64encode(jpeg.tobytes()).decode() if ok else None,
                width=int(mirrored.shape[1]), height=int(mirrored.shape[0]),
                landmarks=[Landmark(x=x, y=y, v=v) for x, y, v in flipped_points] if flipped_points else [],
                face=flipped_face, posture=analyse(points, self.calibration),
                looking_down=self.down_since is not None,
            )

    def preview(self) -> PresenceFrame:
        """Called by the Camera tab (several times a second). Keeps preview mode on for 3 more seconds."""
        self.preview_until = self.clock() + 3.0
        with self._lock:
            return self._frame or PresenceFrame(state=self.state)

    def calibrate(self) -> Posture:
        """Birdy's calibration: remember the current (straight) posture as the reference."""
        if self._last_pitch is not None:  # also remember how the head looks when facing the screen
            self.head_baseline, self.head_calibrated = self._last_pitch, True
        with self._lock:
            reference = measures(self._last_points) if self._last_points else None
        if reference is None:
            return Posture(label="Unknown", ok=False, calibrated=self.calibration is not None)
        self.calibration = reference
        return analyse(self._last_points, self.calibration)

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
        return PresenceReport(enabled=self.enabled, state=self.state, seconds_since_seen=since,
                              looking_down_seconds=self.looking_down_seconds(), detail=self.detail)


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
