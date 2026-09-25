"""Tests for the clipping presets and the auto-recommend logic."""

from __future__ import annotations

import pytest

from clipkit.hardware import Hardware
from clipkit.presets import (
    DEFAULT_BITRATE,
    PRESET_ORDER,
    RECORD_BITRATES,
    all_presets,
    build_preset,
    recommend_bitrate,
    recommend_id,
)

ALLOWED_BITRATES = {kbps for kbps, _label in RECORD_BITRATES}


def _hw(**kwargs) -> Hardware:
    return Hardware(**kwargs)


def test_recommend_high_for_strong_nvidia():
    hw = _hw(gpu_vendor="nvidia", gpu_name="NVIDIA GeForce RTX 4070", vram_gb=12, ram_gb=32)
    assert recommend_id(hw) == "high"


def test_recommend_low_for_cpu_only():
    hw = _hw(gpu_vendor="unknown", gpu_name="Unknown GPU", vram_gb=0, ram_gb=16)
    assert recommend_id(hw) == "low"


def test_recommend_low_for_small_ram():
    hw = _hw(gpu_vendor="nvidia", gpu_name="RTX 3060", vram_gb=8, ram_gb=8)
    assert recommend_id(hw) == "low"


def test_recommend_low_for_plain_intel():
    hw = _hw(gpu_vendor="intel", gpu_name="Intel UHD Graphics 630", vram_gb=2, ram_gb=16)
    assert recommend_id(hw) == "low"


def test_recommend_medium_for_midrange_amd():
    hw = _hw(gpu_vendor="amd", gpu_name="AMD Radeon RX 6500", vram_gb=4, ram_gb=16)
    assert recommend_id(hw) == "medium"


def test_build_preset_high_keeps_native_resolution():
    hw = _hw(gpu_vendor="nvidia", gpu_name="RTX 4080", vram_gb=16, ram_gb=32,
             display_width=2560, display_height=1440)
    preset = build_preset(hw, "high")
    assert (preset.output_width, preset.output_height) == (2560, 1440)
    assert preset.encoder_id == "obs_nvenc_h264_tex"
    assert preset.bitrate_kbps == DEFAULT_BITRATE
    assert preset.replay_seconds == 300
    assert preset.encoder_settings["rate_control"] == "CBR"


def test_build_preset_low_caps_to_1080p():
    hw = _hw(gpu_vendor="nvidia", gpu_name="RTX 4080", vram_gb=16, ram_gb=32,
             display_width=3840, display_height=2160)
    preset = build_preset(hw, "low")
    assert preset.output_width <= 1920
    assert preset.output_height <= 1080


def test_build_preset_makes_even_dimensions():
    hw = _hw(gpu_vendor="nvidia", gpu_name="RTX 4080", vram_gb=16, ram_gb=32,
             display_width=1921, display_height=1081)
    preset = build_preset(hw, "high")
    assert preset.output_width % 2 == 0
    assert preset.output_height % 2 == 0


def test_build_preset_rejects_unknown_id():
    hw = _hw()
    with pytest.raises(ValueError):
        build_preset(hw, "ultra")


def test_build_preset_rejects_bad_fps_and_clip():
    hw = _hw()
    with pytest.raises(ValueError):
        build_preset(hw, "low", fps=45)
    with pytest.raises(ValueError):
        build_preset(hw, "low", replay_seconds=99)


def test_build_preset_coerces_bad_bitrate_to_default():
    hw = _hw()
    preset = build_preset(hw, "low", bitrate_kbps=999999)
    assert preset.bitrate_kbps == DEFAULT_BITRATE


def test_recommend_bitrate_matches_default_at_1080p60():
    assert recommend_bitrate(1920, 1080, 60) == DEFAULT_BITRATE


def test_recommend_bitrate_scales_up_for_1440p60():
    assert recommend_bitrate(2560, 1440, 60) == 25000


def test_recommend_bitrate_scales_down_for_1080p30():
    assert recommend_bitrate(1920, 1080, 30) == 8000


def test_recommend_bitrate_caps_at_offered_maximum_for_4k():
    assert recommend_bitrate(3840, 2160, 60) == 25000


def test_recommend_bitrate_always_returns_an_offered_value():
    for width, height, fps in [(1280, 720, 30), (1920, 1080, 60), (2560, 1440, 30), (3840, 2160, 60)]:
        assert recommend_bitrate(width, height, fps) in ALLOWED_BITRATES


def test_recommend_bitrate_handles_bad_input():
    assert recommend_bitrate(0, 0, 0) in ALLOWED_BITRATES


def test_all_presets_covers_every_tier():
    hw = _hw(gpu_vendor="nvidia", gpu_name="RTX 4070", vram_gb=12, ram_gb=32)
    presets = all_presets(hw)
    assert set(presets) == set(PRESET_ORDER)
    assert [presets[p].label for p in PRESET_ORDER] == ["Low", "Medium", "High"]
