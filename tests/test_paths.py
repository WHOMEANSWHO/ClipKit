"""Tests for path helpers and the clips-folder fallback."""

from __future__ import annotations

from pathlib import Path

from clipkit.paths import (
    appdata_dir,
    ensure_clips_dir,
    ensure_directory,
    local_appdata_dir,
    same_path,
)


def test_appdata_dir_uses_env_when_set(monkeypatch):
    monkeypatch.setenv("APPDATA", "/tmp/roaming-x")
    assert appdata_dir() == Path("/tmp/roaming-x")


def test_appdata_dir_falls_back_without_env(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    assert appdata_dir() == Path.home() / "AppData" / "Roaming"


def test_local_appdata_dir_uses_env_when_set(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "/tmp/local-x")
    assert local_appdata_dir() == Path("/tmp/local-x")


def test_same_path_ignores_slashes_and_trailing_sep():
    assert same_path("C:/games/clips", "C:\\games\\clips") is True
    assert same_path("C:/games/clips/", "C:/games/clips") is True


def test_same_path_rejects_different_and_missing():
    assert same_path("C:/games/a", "C:/games/b") is False
    assert same_path(None, "C:/games/a") is False
    assert same_path("", "") is False


def test_ensure_directory_creates_nested(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert ensure_directory(target) == target
    assert target.is_dir()


def test_ensure_clips_dir_prefers_requested_folder(tmp_path):
    preferred = tmp_path / "MyClips"
    result = ensure_clips_dir(preferred)
    assert result == preferred
    assert preferred.is_dir()
