"""Integration tests for the sunrise ramp itself (wakeup.run_sunrise) against the
faked lamp. A FakeClock fast-forwards wall-clock time so the full multi-minute ramp
runs to completion in milliseconds without sleeping for real.

The headline case is the one we verified live on real hardware: a wake-up must
light a lamp that was switched fully *off* beforehand.
"""

import time as real_time

import pytest

import wakeup


class FakeClock:
    """Stands in for the `time` module inside wakeup: time() only advances when
    sleep() is called, so the ramp completes in a bounded number of fast steps."""

    def __init__(self, start=1000.0):
        self.t = start

    def time(self):
        return self.t

    def sleep(self, dt):
        self.t += max(0.0, dt)


@pytest.fixture(autouse=True)
def _stop_sunrise():
    """Make sure no ramp thread outlives a test."""
    yield
    wakeup.cancel()
    for _ in range(50):
        if not wakeup.is_active():
            break
        real_time.sleep(0.02)


def test_sunrise_completes_in_white_cct_at_full_brightness(fake, monkeypatch):
    monkeypatch.setattr(wakeup, "time", FakeClock())
    dev = fake.dev("ceiling")

    wakeup.run_sunrise("ceiling", 0.2)            # blocking, fast-forwarded

    assert dev._power is True
    assert dev._dps["21"] == "white"              # handed off to white-CCT mode
    assert dev._dps["22"] == 1000                 # ramped to full brightness
    assert dev._dps["23"] == 1000                 # ...and coolest temp, like "Arbeiten"


def test_sunrise_turns_on_a_lamp_that_was_off(fake, monkeypatch):
    # the case the user asked about: lamp off before the alarm → lit afterwards.
    monkeypatch.setattr(wakeup, "time", FakeClock())
    dev = fake.dev("ceiling")
    dev.turn_off()
    assert dev._power is False                     # off going in

    seq = []
    original = dev.set_value

    def spy(dp, val):
        seq.append((str(dp), val))
        original(dp, val)

    monkeypatch.setattr(dev, "set_value", spy)

    wakeup.run_sunrise("ceiling", 0.2)

    assert dev._power is True                       # ...on coming out
    modes = [val for dp, val in seq if dp == "21"]
    assert modes[0] == "colour"                     # started dim in colour mode
    assert modes[-1] == "white"                     # then white-CCT for the bright phase
    assert dev._dps["22"] == 1000                   # reached full brightness


def test_sunrise_floors_brightness_so_it_is_visible_at_the_start(fake, monkeypatch):
    # the ramp must not begin below the perceptible floor (the "lamp never turned on"
    # bug). Catch the very first colour-phase value by aborting after one step.
    monkeypatch.setattr(wakeup, "time", FakeClock())
    dev = fake.dev("ceiling")
    first = []
    original = dev.set_value

    def spy(dp, val):
        if str(dp) == "24" and not first:
            first.append(val)
            wakeup.cancel()                         # stop after the opening frame
        original(dp, val)

    monkeypatch.setattr(dev, "set_value", spy)
    wakeup.run_sunrise("ceiling", 0.2)

    v = int(first[0][-4:], 16)                       # HSV value word
    assert v >= wakeup.FLOOR                         # at or above the visible floor


def test_sunrise_ignores_unknown_device(fake, monkeypatch):
    monkeypatch.setattr(wakeup, "time", FakeClock())
    wakeup.run_sunrise("ghost", 0.2)                # not in config → quiet no-op
    assert not wakeup.is_active()


def test_sunrise_is_single_instance(fake, monkeypatch):
    # a second sunrise must not start while one is already running.
    wakeup._running.set()
    touched = []
    monkeypatch.setattr(wakeup.lamp, "load_config", lambda: touched.append(1) or {})
    try:
        wakeup.run_sunrise("ceiling", 0.2)
        assert touched == []                         # returned before touching the lamp
    finally:
        wakeup._running.clear()
