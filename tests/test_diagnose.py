"""Tests for the --diagnose report helpers."""

from __future__ import annotations

from pathlib import Path

from clipkit import diagnose


def test_obs_base_dir_from_exe():
    exe = Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
    assert diagnose._obs_base_dir(exe) == Path(r"C:\Program Files\obs-studio")


def test_obs_base_dir_handles_none():
    assert diagnose._obs_base_dir(None) is None


def test_portable_markers_detects_config_and_marker(tmp_path):
    assert diagnose._portable_markers(tmp_path) == []
    (tmp_path / "config" / "obs-studio").mkdir(parents=True)
    assert "config/obs-studio present" in diagnose._portable_markers(tmp_path)
    (tmp_path / "obs_portable_mode").write_text("x", encoding="utf-8")
    assert "obs_portable_mode" in diagnose._portable_markers(tmp_path)


def test_tail_returns_last_lines(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("\n".join(str(i) for i in range(100)), encoding="utf-8")
    assert diagnose._tail(log, 5).splitlines() == ["95", "96", "97", "98", "99"]


def test_tail_handles_missing_file(tmp_path):
    assert diagnose._tail(tmp_path / "nope.txt") == "(not found)"
