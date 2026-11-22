import itertools

from services.agent.presence import PresenceWatcher, combined_idle


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def watcher(clock):
    return PresenceWatcher(True, away_after=10, clock=clock)


def test_present_then_away_after_a_while():
    clock = Clock()
    w = watcher(clock)
    w.observe(True)
    assert w.state == "present" and w.idle_seconds() == 0.0
    clock.now += 4
    w.observe(False)
    assert w.state == "present"  # a few seconds without a face is not "away" yet (head turned...)
    clock.now += 7
    w.observe(False)
    assert w.state == "away" and w.idle_seconds() == 11
    w.observe(True)
    assert w.state == "present"


def test_combined_idle_uses_the_shorter_one():
    clock = Clock()
    w = watcher(clock)
    reader = combined_idle(lambda: 300.0, w)
    assert reader() == 300.0  # webcam not known yet: keyboard only
    w.observe(True)
    assert reader() == 0.0    # at the desk, reading without touching the mouse: active
    clock.now += 60
    w.observe(False)
    assert reader() == 60.0   # away for 60 s
    assert combined_idle(lambda: 5.0, w)() == 5.0  # typing just now: active


def test_off_by_default_and_no_camera_is_reported():
    assert PresenceWatcher(False).report().state == "off"

    def no_camera():
        raise OSError("no webcam")
    w = PresenceWatcher(True, source_factory=no_camera, detector_factory=lambda: None)
    w._run()
    assert w.report().state == "no_camera" and w.idle_seconds() is None


def test_frames_are_analysed_and_dropped():
    frames = itertools.chain([object(), None], itertools.repeat(None))
    seen = []

    class Source:
        def __call__(self):
            return next(frames)

        def close(self):
            seen.append("camera released")

    class Detector:
        def __call__(self, frame):
            return True

        def close(self):
            seen.append("detector closed")

    w = PresenceWatcher(True, interval=0.01, source_factory=Source, detector_factory=Detector)
    w.start()
    import time
    time.sleep(0.1)
    w.stop()
    assert w.state == "present" and seen == ["detector closed", "camera released"]


def straight(width=0.4, gap=0.45, tilt=0.0, nose_y=0.4):
    """Pose points (33) with ears, nose and shoulders set."""
    points = [(0.5, 0.5, 0.9)] * 33
    shoulder_y = 0.7
    points[0] = (0.5, nose_y, 0.9)
    points[7] = (0.6, shoulder_y - gap * width, 0.9)
    points[8] = (0.4, shoulder_y - gap * width, 0.9)
    points[11] = (0.5 + width / 2, shoulder_y, 0.9)
    points[12] = (0.5 - width / 2, shoulder_y + tilt * width, 0.9)
    return points


def test_posture_rules_ported_from_birdy():
    from services.agent.posture import analyse, measures
    assert analyse(None, None).label == "Unknown"
    assert analyse(straight(), None).label == "Good posture"
    assert analyse(straight(gap=0.2), None).label == "Slouching"
    assert analyse(straight(tilt=0.2), None).label == "Shoulder tilt"
    assert analyse(straight(width=0.7), None).label == "Too close"
    reference = measures(straight())
    assert analyse(straight(), reference).label == "Good posture"
    assert analyse(straight(width=0.55), reference).label == "Too close"
    assert analyse(straight(gap=0.1), reference).label == "Slouching"
    assert analyse(straight(nose_y=0.25), reference).label == "Standing"


def test_preview_is_mirrored_and_only_while_open():
    import numpy as np

    clock = Clock()

    class Detector:
        def __call__(self, frame):
            return True

        def analyse(self, frame, with_pose):
            return True, straight(), [0.1, 0.2, 0.3, 0.4]

        def close(self):
            pass

    w = PresenceWatcher(True, clock=clock, source_factory=lambda: None, detector_factory=Detector)
    assert w.preview().jpeg_base64 is None  # nothing yet
    w._store_preview(np.zeros((48, 64, 3), dtype=np.uint8), straight(), [0.1, 0.2, 0.3, 0.4])
    frame = w.preview()
    assert frame.jpeg_base64 and frame.width == 64 and frame.height == 48
    assert abs(frame.face[0] - 0.6) < 1e-9          # mirrored: 1 - 0.1 - 0.3
    assert frame.posture.label == "Good posture"
    assert w.calibrate().calibrated is True


def test_looking_down_is_timed_and_only_while_present():
    from services.agent.presence import PresenceWatcher, head_pitch
    now = [0.0]
    w = PresenceWatcher(True, away_after=10, clock=lambda: now[0])
    screen = [(0.4, 0.4), (0.6, 0.4), (0.5, 0.5), (0.5, 0.6), (0.3, 0.45), (0.7, 0.45)]
    phone = [(0.4, 0.4), (0.6, 0.4), (0.5, 0.58), (0.5, 0.66), (0.3, 0.38), (0.7, 0.38)]
    assert head_pitch(phone) > head_pitch(screen) + 0.4
    for _ in range(5):  # learns the usual pitch while looking at the screen
        w.observe(True); w.observe_head(True, True, head_pitch(screen)); now[0] += 2
    assert w.report().looking_down_seconds == 0
    w.observe(True); w.observe_head(True, True, head_pitch(phone)); now[0] += 30
    assert w.report().looking_down_seconds == 30
    w.observe(True); w.observe_head(True, False, None)  # face hidden but body seen: still looking away
    assert w.report().looking_down_seconds == 30
    w.observe(True); w.observe_head(True, True, head_pitch(screen))
    assert w.report().looking_down_seconds == 0
