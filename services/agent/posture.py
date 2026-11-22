"""Posture from pose landmarks, ported from Birdy (js/posture.js).

Landmarks are MediaPipe pose points in 0..1 image coordinates (x, y, visibility).
Indices: 0 nose, 7 left ear, 8 right ear, 11 left shoulder, 12 right shoulder.
Like Birdy, posture is compared with a calibration taken while sitting up straight; before calibration,
fixed thresholds are used.
"""
from __future__ import annotations

from pydantic import BaseModel

NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER = 0, 7, 8, 11, 12
CRITICAL = (NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER)

SLOUCH_TOLERANCE = 0.15
TILT_TOLERANCE = 0.05
DISTANCE_TOLERANCE = 0.2
HEIGHT_TOLERANCE = 0.03     # Birdy: 10 px on a ~480 px image
STANDING_THRESHOLD = 0.10   # Birdy: 50 px


class Calibration(BaseModel):
    vertical_gap_ratio: float
    tilt_ratio: float
    shoulder_width: float
    nose_y: float


class Posture(BaseModel):
    label: str   # Good posture, Slouching, Shoulder tilt, Too close, Too far, Sit up, Standing, Unknown
    ok: bool
    calibrated: bool


Point = tuple[float, float, float]  # x, y, visibility


def measures(points: list[Point]) -> Calibration | None:
    """Birdy's measures, or None when the critical points are not reliable (shoulders out of frame...)."""
    if len(points) <= RIGHT_SHOULDER or any(points[i][2] < 0.5 for i in CRITICAL):
        return None
    ls, rs, le, re, nose = points[LEFT_SHOULDER], points[RIGHT_SHOULDER], points[LEFT_EAR], points[RIGHT_EAR], points[NOSE]
    width = abs(ls[0] - rs[0])
    if width < 1e-3:
        return None
    shoulder_mid_y = (ls[1] + rs[1]) / 2
    ear_mid_y = (le[1] + re[1]) / 2
    return Calibration(vertical_gap_ratio=(shoulder_mid_y - ear_mid_y) / width,
                       tilt_ratio=abs(ls[1] - rs[1]) / width, shoulder_width=width, nose_y=nose[1])


def analyse(points: list[Point] | None, calibration: Calibration | None) -> Posture:
    current = measures(points) if points else None
    if current is None:
        return Posture(label="Unknown", ok=False, calibrated=calibration is not None)
    if calibration is None:
        # Before calibration: fixed thresholds that suit a typical laptop webcam.
        if current.shoulder_width > 0.62:
            label = "Too close"
        elif current.shoulder_width < 0.2:
            label = "Too far"
        elif current.vertical_gap_ratio < 0.3:
            label = "Slouching"
        elif current.tilt_ratio > 0.1:
            label = "Shoulder tilt"
        else:
            label = "Good posture"
        return Posture(label=label, ok=label == "Good posture", calibrated=False)
    width_ratio = current.shoulder_width / calibration.shoulder_width
    if width_ratio < 1 - DISTANCE_TOLERANCE:
        label = "Too far"
    elif width_ratio > 1 + DISTANCE_TOLERANCE:
        label = "Too close"
    elif current.nose_y > calibration.nose_y + HEIGHT_TOLERANCE:
        label = "Sit up"
    elif current.nose_y < calibration.nose_y - STANDING_THRESHOLD:
        label = "Standing"
    elif current.vertical_gap_ratio < calibration.vertical_gap_ratio - SLOUCH_TOLERANCE:
        label = "Slouching"
    elif abs(current.tilt_ratio - calibration.tilt_ratio) > TILT_TOLERANCE:
        label = "Shoulder tilt"
    else:
        label = "Good posture"
    return Posture(label=label, ok=label in ("Good posture", "Standing"), calibrated=True)
