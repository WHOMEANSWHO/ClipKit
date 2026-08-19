"""Map keyboard / mouse input to OBS hotkey JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass

SPECIAL = {
    "space": "SPACE",
    "return": "RETURN",
    "tab": "TAB",
    "backspace": "BACKSPACE",
    "delete": "DELETE",
    "insert": "INSERT",
    "home": "HOME",
    "end": "END",
    "prior": "PAGEUP",
    "next": "PAGEDOWN",
    "left": "LEFT",
    "right": "RIGHT",
    "up": "UP",
    "down": "DOWN",
    "plus": "PLUS",
    "minus": "MINUS",
    "equal": "EQUAL",
    "comma": "COMMA",
    "period": "PERIOD",
    "slash": "SLASH",
    "backslash": "BACKSLASH",
    "semicolon": "SEMICOLON",
    "quote": "QUOTE",
    "bracketleft": "BRACKETLEFT",
    "bracketright": "BRACKETRIGHT",
    "grave": "DEAD_GRAVE",
    "pause": "PAUSE",
    "print": "PRINT",
    "scroll_lock": "SCROLLLOCK",
    "caps_lock": "CAPSLOCK",
    "num_lock": "NUMLOCK",
    "kp_add": "NUMPLUS",
    "kp_subtract": "NUMMINUS",
    "kp_multiply": "NUMMULTIPLY",
    "kp_divide": "NUMDIVIDE",
    "kp_decimal": "NUMPERIOD",
    "kp_enter": "NUMENTER",
    "kp_0": "NUM0",
    "kp_1": "NUM1",
    "kp_2": "NUM2",
    "kp_3": "NUM3",
    "kp_4": "NUM4",
    "kp_5": "NUM5",
    "kp_6": "NUM6",
    "kp_7": "NUM7",
    "kp_8": "NUM8",
    "kp_9": "NUM9",
}

PRETTY = {
    "MOUSE4": "Mouse 4",
    "MOUSE5": "Mouse 5",
    "MOUSE3": "Mouse 3",
    "PAGEUP": "Page Up",
    "PAGEDOWN": "Page Down",
    "NUMPLUS": "Num +",
    "NUMMINUS": "Num -",
    "SPACE": "Space",
    "RETURN": "Enter",
    "DEAD_GRAVE": "`",
}


@dataclass
class Hotkey:
    obs_key: str
    control: bool = False
    alt: bool = False
    shift: bool = False
    command: bool = False

    @property
    def short_name(self) -> str:
        name = self.obs_key.removeprefix("OBS_KEY_")
        return PRETTY.get(name, name.replace("_", " ").title() if len(name) > 1 else name)

    @property
    def label(self) -> str:
        parts: list[str] = []
        if self.control:
            parts.append("Ctrl")
        if self.alt:
            parts.append("Alt")
        if self.shift:
            parts.append("Shift")
        parts.append(self.short_name)
        return " + ".join(parts)

    def binding(self) -> dict:
        data: dict = {"key": self.obs_key}
        if self.control:
            data["control"] = True
        if self.alt:
            data["alt"] = True
        if self.shift:
            data["shift"] = True
        if self.command:
            data["command"] = True
        return data

    def frontend_ini(self) -> str:
        return json.dumps({"bindings": [self.binding()]}, separators=(",", ":"))

    def replay_save_ini(self) -> str:
        return json.dumps({"ReplayBuffer.Save": [self.binding()]}, separators=(",", ":"))


@dataclass
class UserBinds:
    save: Hotkey
    replay_toggle: Hotkey
    record_toggle: Hotkey
    hook_game: Hotkey
    mic_mode: str = "ptt"  # open, ptt, off
    ptt: list[Hotkey] | None = None

    @property
    def ptt_enabled(self) -> bool:
        return self.mic_mode == "ptt"

    def ptt_keys(self) -> list[Hotkey]:
        if self.ptt:
            return list(self.ptt)
        return [Hotkey("OBS_KEY_MOUSE3"), Hotkey("OBS_KEY_MOUSE4")]


DEFAULT_BINDS = UserBinds(
    save=Hotkey("OBS_KEY_PAGEUP"),
    replay_toggle=Hotkey("OBS_KEY_NUMMINUS"),
    record_toggle=Hotkey("OBS_KEY_NUMPLUS"),
    hook_game=Hotkey("OBS_KEY_F7"),
    mic_mode="ptt",
    ptt=[Hotkey("OBS_KEY_MOUSE3"), Hotkey("OBS_KEY_MOUSE4")],
)


def from_tk(event) -> Hotkey | None:
    """Convert a Tk key or mouse event into an OBS hotkey. Escape cancels."""
    keysym = str(getattr(event, "keysym", "") or "").lower()
    num = int(getattr(event, "num", 0) or 0)
    if keysym in {"escape", "control_l", "control_r", "alt_l", "alt_r", "shift_l", "shift_r"}:
        return None if keysym == "escape" else from_modifiers_only(event)

    obs = None
    if keysym.startswith("f") and keysym[1:].isdigit():
        obs = f"OBS_KEY_F{keysym[1:]}"
    elif len(keysym) == 1 and keysym.isalnum():
        obs = f"OBS_KEY_{keysym.upper()}"
    elif keysym in SPECIAL:
        obs = f"OBS_KEY_{SPECIAL[keysym]}"
    elif num == 4:
        obs = "OBS_KEY_MOUSE4"
    elif num == 5:
        obs = "OBS_KEY_MOUSE5"
    elif num == 2:
        obs = "OBS_KEY_MOUSE3"
    elif num == 3:
        obs = "OBS_KEY_MOUSE2"
    elif num == 1:
        return None
    elif keysym:
        # Any other key OBS understands, including OEM / extra keys.
        token = keysym.upper().replace("-", "_")
        obs = f"OBS_KEY_{token}"

    if not obs:
        return None
    return Hotkey(
        obs,
        control=bool(int(getattr(event, "state", 0)) & 0x4),
        alt=bool(int(getattr(event, "state", 0)) & 0x20000) or bool(int(getattr(event, "state", 0)) & 0x8),
        shift=bool(int(getattr(event, "state", 0)) & 0x1),
    )


def from_modifiers_only(event) -> Hotkey | None:
    return None


def mouse_hotkey(button: int) -> Hotkey:
    if button == 4:
        return Hotkey("OBS_KEY_MOUSE4")
    if button == 5:
        return Hotkey("OBS_KEY_MOUSE5")
    return Hotkey("OBS_KEY_MOUSE3")
