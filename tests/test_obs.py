"""Tests for the OBS profile / scene / ini generation helpers."""

from __future__ import annotations

from pathlib import Path

from clipkit.hardware import Hardware
from clipkit.keys import DEFAULT_BINDS
from clipkit.obs import (
    PROFILE_NAME,
    SCENE_NAME,
    _collapse_ini_duplicates,
    _ini_parser,
    _profile_ini,
    _scene_collection,
    _upsert_ini_key,
    clipkit_profile_exists,
    existing_profile_dirs,
    next_clipkit_profile_name,
)
from clipkit.presets import build_preset


def _preset():
    hw = Hardware(gpu_vendor="nvidia", gpu_name="RTX 4070", vram_gb=12, ram_gb=32,
                  display_width=1920, display_height=1080)
    return build_preset(hw, "high")


def test_ini_parser_preserves_key_case():
    parser = _ini_parser()
    parser.read_string("[Section]\nMixedCaseKey=Value\n")
    assert parser["Section"]["MixedCaseKey"] == "Value"


def test_collapse_ini_duplicates_keeps_last_value():
    text = "[A]\nx=1\nx=2\n[B]\ny=3\n"
    collapsed = _collapse_ini_duplicates(text)
    assert "x=2" in collapsed
    assert "x=1" not in collapsed
    assert "y=3" in collapsed


def test_upsert_ini_key_updates_existing_value():
    text = "[Basic]\nProfile=Old\n"
    updated = _upsert_ini_key(text, "Basic", "Profile", "ClipKit")
    assert "Profile=ClipKit" in updated
    assert "Profile=Old" not in updated


def test_upsert_ini_key_adds_missing_section():
    updated = _upsert_ini_key("[Basic]\nProfile=ClipKit\n", "Video", "FPSCommon", "60")
    assert "[Video]" in updated
    assert "FPSCommon=60" in updated


def test_profile_ini_contains_core_settings():
    preset = _preset()
    text = _profile_ini(preset, Path("C:/clips"), DEFAULT_BINDS)
    assert "[General]" in text
    assert f"Name={PROFILE_NAME}" in text
    assert f"RecRBTime={preset.replay_seconds}" in text
    assert f"VBitrate={preset.bitrate_kbps}" in text
    assert "FilePath=C:\\clips" in text
    assert "ReplayBuffer.Save" in text  # save hotkey binding is embedded


def test_scene_collection_structure_and_mic():
    preset = _preset()
    collection = _scene_collection(preset, "window", mic_device_id="default", binds=DEFAULT_BINDS)
    assert collection["name"] == SCENE_NAME
    assert collection["current_scene"] == "Game"
    names = [s["name"] for s in collection["sources"]]
    assert "Game Capture" in names
    assert "Game" in names
    # DEFAULT_BINDS uses push-to-talk, so the mic aux device is present.
    assert "AuxAudioDevice1" in collection


def test_scene_collection_any_capture_mode():
    preset = _preset()
    collection = _scene_collection(preset, "any", mic_device_id="default", binds=DEFAULT_BINDS)
    game = next(s for s in collection["sources"] if s["name"] == "Game Capture")
    assert game["settings"]["capture_mode"] == "any"


def _make_profile_dir(cfg: Path, name: str) -> None:
    (cfg / "basic" / "profiles" / name).mkdir(parents=True, exist_ok=True)


def test_next_profile_name_when_none_exists(tmp_path):
    assert next_clipkit_profile_name(tmp_path) == "ClipKit"
    assert clipkit_profile_exists(tmp_path) is False
    assert existing_profile_dirs(tmp_path) == []


def test_next_profile_name_when_clipkit_exists(tmp_path):
    _make_profile_dir(tmp_path, "ClipKit")
    assert clipkit_profile_exists(tmp_path) is True
    assert next_clipkit_profile_name(tmp_path) == "ClipKit2"


def test_next_profile_name_skips_taken_numbers(tmp_path):
    for name in ("ClipKit", "ClipKit2", "ClipKit3"):
        _make_profile_dir(tmp_path, name)
    assert next_clipkit_profile_name(tmp_path) == "ClipKit4"


def test_profile_ini_uses_custom_profile_name():
    text = _profile_ini(_preset(), Path("C:/clips"), DEFAULT_BINDS, profile_name="ClipKit2")
    assert "Name=ClipKit2" in text
    assert "Name=ClipKit\n" not in text


def test_scene_collection_uses_custom_collection_name():
    collection = _scene_collection(
        _preset(), "window", mic_device_id="default", binds=DEFAULT_BINDS, collection_name="ClipKit2"
    )
    assert collection["name"] == "ClipKit2"
    # The scene inside the collection is still "Game".
    assert any(s["name"] == "Game" for s in collection["sources"])
