"""Unit tests for wakeup.py: config persistence, the HSV helper, and the scheduler
matching logic in _loop (the bit that decides *when* a sunrise fires).

The scheduler tests freeze the clock and run a single _loop iteration with the
device side-effects faked out, so they assert the firing condition only — including
that it matches the local wall-clock time (the UTC-timezone bug we fixed in the
container made "07:00" fire at 09:00 CEST; the match itself is what these guard).
"""

import datetime
import json
import types

import pytest

import wakeup

# 2026-06-22 is a Monday → weekday() == 0.
MON_0700 = datetime.datetime(2026, 6, 22, 7, 0)


# --- config: load / save -----------------------------------------------------

def test_load_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(wakeup, "WAKEUP_PATH", tmp_path / "absent.json")
    assert wakeup.load() == wakeup.DEFAULT


def test_load_merges_partial_file_over_defaults(tmp_path, monkeypatch):
    p = tmp_path / "wakeup.json"
    p.write_text(json.dumps({"time": "06:15", "enabled": True}))
    monkeypatch.setattr(wakeup, "WAKEUP_PATH", p)
    cfg = wakeup.load()
    assert cfg["time"] == "06:15" and cfg["enabled"] is True
    assert cfg["duration_min"] == wakeup.DEFAULT["duration_min"]   # untouched key kept


def test_load_falls_back_on_bad_json(tmp_path, monkeypatch):
    p = tmp_path / "wakeup.json"
    p.write_text("{ not valid json")
    monkeypatch.setattr(wakeup, "WAKEUP_PATH", p)
    assert wakeup.load() == wakeup.DEFAULT


def test_save_persists_and_round_trips(tmp_path, monkeypatch):
    p = tmp_path / "wakeup.json"
    monkeypatch.setattr(wakeup, "WAKEUP_PATH", p)
    wakeup.save({"enabled": True, "time": "05:45", "days": [0, 2, 4]})
    assert wakeup.load() == {**wakeup.DEFAULT, "enabled": True, "time": "05:45", "days": [0, 2, 4]}


def test_save_clamps_duration(tmp_path, monkeypatch):
    monkeypatch.setattr(wakeup, "WAKEUP_PATH", tmp_path / "wakeup.json")
    assert wakeup.save({"duration_min": 999})["duration_min"] == 60
    assert wakeup.save({"duration_min": 0})["duration_min"] == 1


def test_save_merges_over_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(wakeup, "WAKEUP_PATH", tmp_path / "wakeup.json")
    wakeup.save({"time": "06:00", "device": "ceiling"})
    merged = wakeup.save({"enabled": True})          # only flips enabled
    assert merged["time"] == "06:00" and merged["enabled"] is True


# --- HSV helper --------------------------------------------------------------

def test_hsv_hex_packs_three_16bit_words():
    assert wakeup._hsv_hex(35, 1000, 40) == "0023" "03e8" "0028"


def test_hsv_hex_wraps_hue_and_clamps_sat_val():
    assert wakeup._hsv_hex(360, 5000, -10).startswith("0000")   # hue wraps to 0
    assert wakeup._hsv_hex(0, 5000, -10) == "0000" "03e8" "0000"  # s→1000, v→0


# --- scheduler matching (_loop) ----------------------------------------------

class _LoopStop(Exception):
    """Raised from the faked sleep to break _loop's `while True`."""


class _SyncThread:
    """threading.Thread stand-in that runs the target inline on .start()."""

    def __init__(self, target=None, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        if self._target:
            self._target(*self._args)


def _drive_loop(monkeypatch, cfg, frozen, *, stop_after=1):
    """Run wakeup._loop for `stop_after` iterations under a frozen clock and
    return the list of (device, duration) fires it kicked off."""
    fires = []
    monkeypatch.setattr(wakeup, "load", lambda: cfg)
    monkeypatch.setattr(wakeup, "run_sunrise", lambda dev, dur: fires.append((dev, dur)))
    monkeypatch.setattr(wakeup.threading, "Thread", _SyncThread)
    monkeypatch.setattr(
        wakeup, "datetime",
        types.SimpleNamespace(datetime=types.SimpleNamespace(now=lambda: frozen)),
    )
    calls = {"n": 0}

    def _sleep(_):
        calls["n"] += 1
        if calls["n"] >= stop_after:
            raise _LoopStop

    monkeypatch.setattr(wakeup.time, "sleep", _sleep)
    with pytest.raises(_LoopStop):
        wakeup._loop()
    return fires


def _cfg(**over):
    return {"enabled": True, "time": "07:00", "duration_min": 10,
            "device": "ceiling", "days": [0, 1, 2, 3, 4], **over}


def test_loop_fires_when_enabled_time_and_day_match(monkeypatch):
    assert _drive_loop(monkeypatch, _cfg(), MON_0700) == [("ceiling", 10)]


def test_loop_does_not_fire_when_disabled(monkeypatch):
    assert _drive_loop(monkeypatch, _cfg(enabled=False), MON_0700) == []


def test_loop_does_not_fire_on_a_day_not_selected(monkeypatch):
    assert _drive_loop(monkeypatch, _cfg(days=[5, 6]), MON_0700) == []   # Mon not in {Sat,Sun}


def test_loop_does_not_fire_when_time_differs(monkeypatch):
    assert _drive_loop(monkeypatch, _cfg(time="08:00"), MON_0700) == []


def test_loop_fires_only_once_per_day(monkeypatch):
    # two iterations at the same wall-clock minute must still fire exactly once
    assert _drive_loop(monkeypatch, _cfg(), MON_0700, stop_after=2) == [("ceiling", 10)]
