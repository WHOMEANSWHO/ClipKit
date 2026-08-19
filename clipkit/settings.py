"""Remember the last ClipKit options so people do not set them twice."""

from __future__ import annotations

import json
from pathlib import Path

from .keys import DEFAULT_BINDS, Hotkey, UserBinds
from .presets import CLIP_LENGTHS, DEFAULT_BITRATE, FPS_CHOICES, PRESET_ORDER, RECORD_BITRATES


def settings_path() -> Path:
    return Path.home() / "AppData" / "Roaming" / "ClipKit" / "settings.json"


def obs_scripts_dir() -> Path:
    return Path.home() / "AppData" / "Roaming" / "obs-studio" / "clipkit-scripts"


def legacy_clipkit_dir() -> Path:
    return Path.home() / "AppData" / "Roaming" / "ClipKit"


def last_game_path() -> Path:
    return obs_scripts_dir() / "last-game.json"


def ptt_config_path() -> Path:
    return obs_scripts_dir() / "ptt.json"


def save_ptt_config(binds: UserBinds) -> None:
    path = ptt_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "enabled": binds.ptt_enabled,
                "keys": [key.obs_key for key in binds.ptt_keys()[:2]],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def migrate_obs_sidecars() -> None:
    """Copy last-game / PTT files out of the old ClipKit AppData folder into OBS."""
    dest_dir = obs_scripts_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    legacy = legacy_clipkit_dir()
    for name in ("last-game.json", "ptt.json"):
        dest = dest_dir / name
        src = legacy / name
        if dest.is_file() or not src.is_file():
            continue
        try:
            dest.write_bytes(src.read_bytes())
        except OSError:
            continue


def load_last_game() -> dict:
    for path in (last_game_path(), legacy_clipkit_dir() / "last-game.json"):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        exe = str(data.get("exe") or "").strip()
        if not exe:
            continue
        return {
            "exe": exe,
            "class": str(data.get("class") or "").strip(),
            "title": str(data.get("title") or "").strip(),
            "family": str(data.get("family") or "").strip(),
        }
    return {}


def _hotkey_to_dict(key: Hotkey) -> dict:
    return {
        "obs_key": key.obs_key,
        "control": key.control,
        "alt": key.alt,
        "shift": key.shift,
        "command": key.command,
    }


def _hotkey_from_dict(data: object, fallback: Hotkey) -> Hotkey:
    if not isinstance(data, dict):
        return fallback
    obs_key = str(data.get("obs_key") or fallback.obs_key)
    if not obs_key.startswith("OBS_KEY_"):
        return fallback
    return Hotkey(
        obs_key,
        control=bool(data.get("control")),
        alt=bool(data.get("alt")),
        shift=bool(data.get("shift")),
        command=bool(data.get("command")),
    )


def load_settings() -> dict:
    path = settings_path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_settings(data: dict) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def binds_from_settings(data: dict) -> UserBinds:
    saved = data.get("binds") if isinstance(data.get("binds"), dict) else {}
    ptt_raw = saved.get("ptt") if isinstance(saved, dict) else None
    defaults = DEFAULT_BINDS.ptt_keys()
    ptt = []
    if isinstance(ptt_raw, list) and ptt_raw:
        for index, item in enumerate(ptt_raw[:2]):
            ptt.append(_hotkey_from_dict(item, defaults[min(index, len(defaults) - 1)]))
    while len(ptt) < 2:
        ptt.append(defaults[len(ptt)])
    if {key.obs_key for key in ptt[:2]} == {"OBS_KEY_MOUSE3", "OBS_KEY_MOUSE4"}:
        ptt = list(defaults)
    mic = str(data.get("mic_mode") or DEFAULT_BINDS.mic_mode)
    if mic not in {"open", "ptt", "off"}:
        mic = DEFAULT_BINDS.mic_mode
    return UserBinds(
        save=_hotkey_from_dict(saved.get("save") if isinstance(saved, dict) else None, DEFAULT_BINDS.save),
        replay_toggle=_hotkey_from_dict(
            saved.get("replay_toggle") if isinstance(saved, dict) else None,
            DEFAULT_BINDS.replay_toggle,
        ),
        record_toggle=_hotkey_from_dict(
            saved.get("record_toggle") if isinstance(saved, dict) else None,
            DEFAULT_BINDS.record_toggle,
        ),
        mic_mode=mic,
        mic_device_id=str(data.get("mic_device_id") or ""),
        mic_device_name=str(data.get("mic_device_name") or ""),
        ptt=ptt,
    )


def settings_from_app(
    *,
    output: str,
    preset: str,
    clip_seconds: int,
    fps: int,
    bitrate: int,
    capture: str,
    binds: UserBinds,
    start_with_windows: bool,
    enable_recording: bool,
) -> dict:
    allowed_bitrate = {kbps for kbps, _label in RECORD_BITRATES}
    allowed_seconds = {seconds for seconds, _label in CLIP_LENGTHS}
    return {
        "output": output,
        "preset": preset if preset in PRESET_ORDER else "medium",
        "clip_seconds": clip_seconds if clip_seconds in allowed_seconds else 300,
        "fps": fps if fps in FPS_CHOICES else 60,
        "bitrate": bitrate if bitrate in allowed_bitrate else DEFAULT_BITRATE,
        "capture": "any" if capture == "any" else "window",
        "mic_mode": binds.mic_mode,
        "mic_device_id": binds.mic_device_id,
        "mic_device_name": binds.mic_device_name,
        "start_with_windows": start_with_windows,
        "enable_recording": enable_recording,
        "binds": {
            "save": _hotkey_to_dict(binds.save),
            "replay_toggle": _hotkey_to_dict(binds.replay_toggle),
            "record_toggle": _hotkey_to_dict(binds.record_toggle),
            "ptt": [_hotkey_to_dict(key) for key in binds.ptt_keys()[:2]],
        },
    }
