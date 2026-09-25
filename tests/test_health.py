"""Tests for health-check helpers (Explorer reveal + OBS window parsing)."""

from __future__ import annotations

import os
from pathlib import Path

from clipkit.health import _explorer_select_command, _label_from_obs_window


def test_explorer_select_command_is_single_quoted_string():
    path = Path(r"C:\clips\my game\clip.mp4")
    cmd = _explorer_select_command(path)
    assert cmd == f'explorer /select,"{os.path.normpath(str(path))}"'
    # No space after the comma, and the path is wrapped in one pair of quotes.
    assert "/select," in cmd
    assert cmd.count('"') == 2
    assert cmd.startswith("explorer /select,\"")


def test_label_from_obs_window_uses_title_when_present():
    assert _label_from_obs_window("Grand Theft Auto V:grcWindow:GTA5.exe") == "Grand Theft Auto V"


def test_label_from_obs_window_falls_back_to_exe_name():
    assert _label_from_obs_window(":UnrealWindow:Fortnite.exe") == "Fortnite"


def test_label_from_obs_window_handles_empty():
    assert _label_from_obs_window("") == ""
