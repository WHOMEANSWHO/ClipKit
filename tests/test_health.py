"""Tests for health-check helpers (Explorer reveal + OBS window parsing)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from clipkit import obs
from clipkit.hardware import Hardware
from clipkit.health import _explorer_select_command, _label_from_obs_window, verify_apply
from clipkit.keys import DEFAULT_BINDS
from clipkit.presets import build_preset


def _write_valid_config(cfg, profile_name: str = "ClipKit") -> None:
    preset = build_preset(
        Hardware(gpu_vendor="nvidia", gpu_name="RTX 4070", vram_gb=12, ram_gb=32), "high"
    )
    prof_dir = cfg / "basic" / "profiles" / profile_name
    prof_dir.mkdir(parents=True)
    (prof_dir / "basic.ini").write_text(
        obs._profile_ini(preset, cfg / "clips", DEFAULT_BINDS, profile_name=profile_name).replace("\n", "\r\n"),
        encoding="utf-8",
    )
    scenes = cfg / "basic" / "scenes"
    scenes.mkdir(parents=True)
    (scenes / f"{profile_name}.json").write_text(
        json.dumps(obs._scene_collection(
            preset, "window", mic_device_id="default", binds=DEFAULT_BINDS, collection_name=profile_name)),
        encoding="utf-8",
    )
    (cfg / "user.ini").write_text(
        f"[Basic]\r\nProfile={profile_name}\r\nSceneCollection={profile_name}\r\n", encoding="utf-8"
    )


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


def test_verify_apply_passes_for_complete_config(tmp_path):
    _write_valid_config(tmp_path)
    checks = verify_apply(tmp_path)
    assert checks["ok"] is True
    for key in ("profile_written", "replay_configured", "scene_written", "profile_selected"):
        assert checks[key] is True


def test_verify_apply_fails_when_nothing_written(tmp_path):
    checks = verify_apply(tmp_path)
    assert checks["ok"] is False
    assert checks["profile_written"] is False
    assert checks["scene_written"] is False


def test_verify_apply_passes_for_custom_profile_name(tmp_path):
    _write_valid_config(tmp_path, profile_name="ClipKit2")
    checks = verify_apply(tmp_path, profile_name="ClipKit2")
    assert checks["ok"] is True
    # And the default name should NOT validate against this config.
    assert verify_apply(tmp_path, profile_name="ClipKit")["ok"] is False
