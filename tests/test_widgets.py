"""Regression tests for the custom rounded widgets.

These guard the infinite-recursion crash that happened when Pillow was missing
(or the widget wasn't sized yet) and the flat fallback re-entered configure().
"""

from __future__ import annotations

import pytest

from clipkit import app


def _root():
    try:
        root = app.tk.Tk()
    except Exception:  # noqa: BLE001 - no display available
        pytest.skip("no Tk display available")
    root.withdraw()
    return root


def test_rounded_button_survives_missing_pillow(monkeypatch):
    monkeypatch.setattr(app, "_rounded_photo", lambda *a, **k: None)
    root = _root()
    try:
        btn = app.RoundedButton(root, "Apply", None, fill=app.PRIMARY_BTN, fg=app.ON_PRIMARY)
        # Each of these previously recursed forever (configure -> _redraw -> configure).
        btn.configure(state="disabled")
        btn.configure(state="normal", bg=app.RAISED)
        btn.configure(text="Install OBS and set up")
        btn._redraw()
    finally:
        root.destroy()


def test_keycap_and_chip_survive_missing_pillow(monkeypatch):
    from clipkit.keys import DEFAULT_BINDS

    monkeypatch.setattr(app, "_rounded_photo", lambda *a, **k: None)
    root = _root()
    try:
        cap = app.KeybindButton(root, DEFAULT_BINDS.save)
        cap.configure(state="disabled")
        cap._redraw()

        chip = app.RoundedChip(root, "High", "high", lambda _v: None)
        chip.set_selected(True)
        chip.set_selected(False)
        chip._redraw()
    finally:
        root.destroy()


def test_full_app_init_with_cached_hardware_and_no_pillow(monkeypatch):
    """Reproduces the reported crash: __init__ -> _apply_hardware -> _sync_obs_presence
    configured the (unmapped) Apply button with Pillow unavailable, which recursed."""
    from clipkit.hardware import Hardware

    monkeypatch.setattr(app, "_rounded_photo", lambda *a, **k: None)
    monkeypatch.setattr(
        app,
        "load_cached_hardware",
        lambda: Hardware(gpu_vendor="nvidia", gpu_name="RTX 4070", vram_gb=12, ram_gb=32),
    )
    try:
        window = app.ClipKitApp()
    except app.tk.TclError:
        pytest.skip("no Tk display available")
    try:
        window.update_idletasks()
    finally:
        window.destroy()