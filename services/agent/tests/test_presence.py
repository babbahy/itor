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
