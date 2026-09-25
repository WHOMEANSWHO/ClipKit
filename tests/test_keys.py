"""Tests for hotkey formatting and Tk event conversion."""

from __future__ import annotations

import json
from types import SimpleNamespace

from clipkit.keys import DEFAULT_BINDS, Hotkey, from_tk


def _event(keysym="", num=0, state=0):
    return SimpleNamespace(keysym=keysym, num=num, state=state)


def test_short_name_uses_pretty_table():
    assert Hotkey("OBS_KEY_PAGEUP").short_name == "Page Up"
    assert Hotkey("OBS_KEY_MOUSE4").short_name == "Mouse 4"
    assert Hotkey("OBS_KEY_NUMMINUS").short_name == "Num -"


def test_label_lists_modifiers_in_order():
    key = Hotkey("OBS_KEY_A", control=True, alt=True, shift=True)
    assert key.label == "Ctrl + Alt + Shift + A"


def test_binding_only_includes_active_modifiers():
    assert Hotkey("OBS_KEY_A").binding() == {"key": "OBS_KEY_A"}
    assert Hotkey("OBS_KEY_A", control=True).binding() == {"key": "OBS_KEY_A", "control": True}


def test_frontend_and_replay_ini_are_valid_json():
    key = Hotkey("OBS_KEY_PAGEUP")
    assert json.loads(key.frontend_ini()) == {"bindings": [{"key": "OBS_KEY_PAGEUP"}]}
    assert json.loads(key.replay_save_ini()) == {"ReplayBuffer.Save": [{"key": "OBS_KEY_PAGEUP"}]}


def test_from_tk_maps_letters_specials_and_function_keys():
    assert from_tk(_event(keysym="a")).obs_key == "OBS_KEY_A"
    assert from_tk(_event(keysym="prior")).obs_key == "OBS_KEY_PAGEUP"
    assert from_tk(_event(keysym="f5")).obs_key == "OBS_KEY_F5"


def test_from_tk_maps_side_mouse_buttons():
    assert from_tk(_event(num=4)).obs_key == "OBS_KEY_MOUSE4"
    assert from_tk(_event(num=5)).obs_key == "OBS_KEY_MOUSE5"


def test_from_tk_escape_and_left_click_return_none():
    assert from_tk(_event(keysym="escape")) is None
    assert from_tk(_event(num=1)) is None


def test_from_tk_reads_modifier_state():
    key = from_tk(_event(keysym="a", state=0x4 | 0x1))
    assert key.control is True
    assert key.shift is True


def test_default_binds_have_two_ptt_keys():
    assert [k.obs_key for k in DEFAULT_BINDS.ptt_keys()] == ["OBS_KEY_MOUSE4", "OBS_KEY_MOUSE5"]
    assert DEFAULT_BINDS.ptt_enabled is True
