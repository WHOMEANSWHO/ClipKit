"""Check that OBS actually opened on the ClipKit profile."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .hardware import obs_is_running
from .obs import PROFILE_NAME, SCENE_NAME, _ini_parser, _read_ini, obs_config_dir
from .settings import load_settings

CLIP_SUFFIXES = {".mp4", ".mkv", ".mov", ".flv"}


def current_profile(config_dir: Path | None = None) -> str:
    user_ini = (config_dir or obs_config_dir()) / "user.ini"
    if not user_ini.is_file():
        return ""
    parser = _ini_parser()
    try:
        _read_ini(parser, user_ini)
    except Exception:
        return ""
    if not parser.has_section("Basic"):
        return ""
    return parser.get("Basic", "Profile", fallback="").strip()


def _scene_collection(config_dir: Path | None = None) -> dict:
    path = (config_dir or obs_config_dir()) / "basic" / "scenes" / f"{SCENE_NAME}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _label_from_obs_window(window: str) -> str:
    parts = [part.strip() for part in window.split(":")]
    if len(parts) >= 3:
        title = ":".join(parts[:-2]).strip()
        exe = parts[-1]
    elif parts:
        title = ""
        exe = parts[-1]
    else:
        return ""
    exe_name = Path(exe).stem or exe
    if title and title.lower() not in {exe.lower(), exe_name.lower()}:
        return title
    return exe_name or title


def hooked_game_label() -> str:
    """Name from OBS Game Capture, or empty if nothing is selected yet."""
    settings = load_settings()
    if str(settings.get("capture") or "") == "any":
        return "any fullscreen game"
    scene = _scene_collection()
    for source in scene.get("sources") or []:
        if not isinstance(source, dict) or source.get("name") != "Game Capture":
            continue
        source_settings = source.get("settings")
        if not isinstance(source_settings, dict):
            return ""
        if source_settings.get("capture_mode") == "any":
            return "any fullscreen game"
        window = str(source_settings.get("window") or "").strip()
        return _label_from_obs_window(window)
    return ""


def probe(*, expect_replay: bool = True) -> dict:
    profile = current_profile()
    running = obs_is_running()
    ok = running and profile == PROFILE_NAME
    if running:
        replay_label = "started with OBS" if expect_replay else "check OBS"
    else:
        replay_label = "not running"
    return {
        "obs": "open" if running else "not open",
        "profile": profile or "unknown",
        "replay": replay_label,
        "ok": ok,
        "replay_known": "on" if (running and expect_replay) else None,
        "game": hooked_game_label(),
    }


def newest_clip(folder: Path, *, after: float) -> Path | None:
    if not folder.is_dir():
        return None
    newest: Path | None = None
    newest_mtime = after
    try:
        paths = folder.rglob("*")
    except OSError:
        return None
    for path in paths:
        if path.suffix.lower() not in CLIP_SUFFIXES:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= newest_mtime:
            newest = path
            newest_mtime = mtime
    return newest


def reveal_in_explorer(path: Path) -> None:
    path = path.resolve()
    if path.is_file():
        subprocess.Popen(["explorer", f"/select,{path}"], close_fds=True)
        return
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(os.fsdecode(path))
