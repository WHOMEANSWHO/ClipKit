"""Check that OBS actually opened on ClipKit with clipping running."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .hardware import obs_is_running
from .obs import PROFILE_NAME, _ini_parser, _read_ini, obs_config_dir
from .settings import load_last_game, load_settings

CLIP_SUFFIXES = {".mp4", ".mkv", ".mov", ".flv"}


def status_file() -> Path:
    return obs_config_dir() / "clipkit-status.txt"


def command_file() -> Path:
    return obs_config_dir() / "clipkit-command.txt"


def save_result_file() -> Path:
    return obs_config_dir() / "clipkit-save-result.txt"


def clear_status() -> None:
    path = status_file()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


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


def _status_fields() -> dict[str, str]:
    path = status_file()
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        fields[key.strip().lower()] = value.strip()
    return fields


def replay_status() -> str | None:
    """Return 'on', 'off', or None if OBS has not reported yet."""
    replay = _status_fields().get("replay", "").lower()
    if replay == "1":
        return "on"
    if replay == "0":
        return "off"
    return None


def hooked_game_label(fields: dict[str, str] | None = None, last_game: dict | None = None) -> str:
    """Human name for the hooked game, or empty if nothing is remembered."""
    fields = fields if fields is not None else _status_fields()
    last_game = last_game if last_game is not None else load_last_game()
    settings = load_settings()
    if str(settings.get("capture") or "") == "any":
        return "any fullscreen game"
    family = str(fields.get("family") or last_game.get("family") or "").strip().lower()
    title = str(fields.get("title") or last_game.get("title") or "").strip()
    exe = str(fields.get("exe") or last_game.get("exe") or "").strip()
    if not exe and not title:
        return ""
    exe_l = exe.lower()
    if family == "fivem" or "fivem" in exe_l or "gtaprocess" in exe_l:
        if title and "fivem" not in title.lower():
            return f"FiveM — {title}"
        return "FiveM"
    if title and title.lower() not in {exe.lower(), Path(exe).stem.lower()}:
        return title
    return Path(exe).stem or title


def probe(*, expect_replay: bool = True) -> dict:
    profile = current_profile()
    fields = _status_fields()
    replay = replay_status()
    running = obs_is_running()
    if replay == "on":
        replay_label = "on"
    elif replay == "off":
        replay_label = "off"
    else:
        replay_label = "starting…" if running else "not running"
    ok = running and profile == PROFILE_NAME
    if expect_replay:
        ok = bool(ok and replay == "on")
    game = hooked_game_label(fields)
    return {
        "obs": "open" if running else "not open",
        "profile": profile or "unknown",
        "replay": replay_label,
        "ok": ok,
        "replay_known": replay,
        "game": game,
    }


def request_test_clip() -> None:
    result = save_result_file()
    try:
        result.unlink(missing_ok=True)
    except OSError:
        pass
    command_file().parent.mkdir(parents=True, exist_ok=True)
    command_file().write_text("save\n", encoding="utf-8")


def read_save_result() -> dict | None:
    path = save_result_file()
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        fields[key.strip().lower()] = value.strip()
    if "ok" not in fields:
        return None
    return {
        "ok": fields.get("ok") == "1",
        "path": fields.get("path") or "",
        "error": fields.get("error") or "",
    }


def wait_for_save_result(*, timeout: float = 12.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = read_save_result()
        if result is not None:
            return result
        time.sleep(0.2)
    return {
        "ok": False,
        "path": "",
        "error": "OBS did not save a clip. Apply ClipKit once, keep OBS open, and make sure clipping is on.",
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
