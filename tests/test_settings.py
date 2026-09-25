"""Tests for settings persistence, atomic writes, and hotkey round-trips."""

from __future__ import annotations

import os

import pytest

from clipkit import settings
from clipkit.keys import DEFAULT_BINDS


def test_save_and_load_settings_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "settings_path", lambda: path)
    data = {"output": "C:/clips", "preset": "high", "fps": 60}
    settings.save_settings(data)
    assert settings.load_settings() == data


def test_load_settings_tolerates_corrupt_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(settings, "settings_path", lambda: path)
    assert settings.load_settings() == {}


def test_atomic_write_leaves_no_temp_files(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "settings_path", lambda: path)
    settings.save_settings({"a": 1})
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "settings.json"]
    assert leftovers == []


def test_atomic_write_keeps_old_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"keep": true}', encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        settings._atomic_write_text(path, '{"new": true}')
    # Original file is untouched and no temp file is left behind.
    assert path.read_text(encoding="utf-8") == '{"keep": true}'
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "settings.json"]
    assert leftovers == []


def test_binds_round_trip_through_settings():
    data = settings.settings_from_app(
        output="C:/clips",
        preset="high",
        clip_seconds=300,
        fps=60,
        bitrate=14000,
        capture="window",
        binds=DEFAULT_BINDS,
        start_with_windows=False,
        enable_recording=True,
    )
    restored = settings.binds_from_settings(data)
    assert restored.save.obs_key == DEFAULT_BINDS.save.obs_key
    assert restored.replay_toggle.obs_key == DEFAULT_BINDS.replay_toggle.obs_key
    assert restored.record_toggle.obs_key == DEFAULT_BINDS.record_toggle.obs_key
    assert restored.mic_mode == DEFAULT_BINDS.mic_mode
    assert [k.obs_key for k in restored.ptt_keys()] == [k.obs_key for k in DEFAULT_BINDS.ptt_keys()]


def test_settings_from_app_sanitises_bad_values():
    data = settings.settings_from_app(
        output="C:/clips",
        preset="bogus",
        clip_seconds=7,
        fps=45,
        bitrate=999999,
        capture="weird",
        binds=DEFAULT_BINDS,
        start_with_windows=True,
        enable_recording=True,
    )
    assert data["preset"] == "medium"
    assert data["clip_seconds"] == 300
    assert data["fps"] == 60
    assert data["bitrate"] == 14000
    assert data["capture"] == "window"


def test_save_ptt_config_writes_expected_shape(tmp_path, monkeypatch):
    path = tmp_path / "ptt.json"
    monkeypatch.setattr(settings, "ptt_config_path", lambda: path)
    settings.save_ptt_config(DEFAULT_BINDS)
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["enabled"] is True
    assert payload["keys"] == ["OBS_KEY_MOUSE4", "OBS_KEY_MOUSE5"]
