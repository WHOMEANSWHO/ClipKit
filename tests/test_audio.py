"""Tests for microphone detection scoring and selection."""

from __future__ import annotations

from clipkit.audio import (
    CaptureDevice,
    obs_device_id,
    pick_microphone,
    resolve_microphone,
    usable_microphones,
)

REAL_MIC = CaptureDevice(name="Microphone (Wave XLR)", device_id="{0.0.1.0}.wavexlr")
USB_MIC = CaptureDevice(name="Microphone (HyperX QuadCast)", device_id="{0.0.1.0}.hyperx")
CABLE = CaptureDevice(name="CABLE Output (VB-Audio Virtual Cable)", device_id="{0.0.1.0}.vbcable")


def test_obs_device_id_strips_prefix_and_validates():
    raw = "MMDEVAPI\\{0.0.1.00000000}.{2a3b}"
    assert obs_device_id(raw) == "{0.0.1.00000000}.{2a3b}"


def test_obs_device_id_rejects_non_capture_endpoints():
    assert obs_device_id("MMDEVAPI\\{0.0.0.00000000}.{render}") is None
    assert obs_device_id("") is None


def test_short_name_unwraps_and_truncates():
    assert USB_MIC.short_name == "HyperX QuadCast"
    long = CaptureDevice(name="Microphone (" + "x" * 60 + ")", device_id="id")
    assert long.short_name.endswith("…")
    assert len(long.short_name) == 34


def test_usable_microphones_drops_virtual_cables():
    ranked = usable_microphones([CABLE, USB_MIC, REAL_MIC])
    assert CABLE not in ranked
    assert ranked[0] == REAL_MIC  # Wave XLR outscores everything else


def test_pick_microphone_prefers_requested_id():
    chosen = pick_microphone([REAL_MIC, USB_MIC], preferred_id="{0.0.1.0}.hyperx")
    assert chosen == USB_MIC


def test_pick_microphone_falls_back_to_best_score():
    chosen = pick_microphone([USB_MIC, REAL_MIC])
    assert chosen == REAL_MIC


def test_resolve_microphone_keeps_existing_when_still_present():
    chosen = resolve_microphone([REAL_MIC, USB_MIC], existing_id="{0.0.1.0}.hyperx")
    assert chosen == USB_MIC


def test_resolve_microphone_replaces_missing_device():
    chosen = resolve_microphone([REAL_MIC], existing_id="{0.0.1.0}.gone")
    assert chosen == REAL_MIC


def test_selection_helpers_handle_no_devices():
    assert pick_microphone([]) is None
    assert resolve_microphone([]) is None
