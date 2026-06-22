"""Unit tests for scene-profile loading from config/settings.json."""

import json

import lamp


def test_load_profiles_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(lamp, "SETTINGS_PATH", tmp_path / "absent.json")
    assert lamp.load_profiles() == lamp.DEFAULT_PROFILES


def test_load_profiles_reads_file(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"profiles": {"cosy": {"label": "Cosy", "temp": 20, "bright": 40}}}))
    monkeypatch.setattr(lamp, "SETTINGS_PATH", p)
    assert lamp.load_profiles() == {"cosy": {"label": "Cosy", "temp": 20, "bright": 40}}


def test_load_profiles_falls_back_on_bad_json(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text("{ not valid json")
    monkeypatch.setattr(lamp, "SETTINGS_PATH", p)
    assert lamp.load_profiles() == lamp.DEFAULT_PROFILES


def test_load_profiles_ignores_empty_or_wrong_shape(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"profiles": {}}))      # empty → not usable
    monkeypatch.setattr(lamp, "SETTINGS_PATH", p)
    assert lamp.load_profiles() == lamp.DEFAULT_PROFILES
