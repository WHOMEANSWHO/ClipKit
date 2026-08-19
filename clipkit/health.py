"""Check that OBS actually opened on ClipKit with clipping running."""

from __future__ import annotations

from pathlib import Path

from .hardware import obs_is_running
from .obs import PROFILE_NAME, _ini_parser, _read_ini, obs_config_dir


def status_file() -> Path:
    return obs_config_dir() / "clipkit-status.txt"


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


def replay_status() -> str | None:
    """Return 'on', 'off', or None if OBS has not reported yet."""
    path = status_file()
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for line in text.splitlines():
        if line.strip().lower() == "replay=1":
            return "on"
        if line.strip().lower() == "replay=0":
            return "off"
    return None


def probe(*, expect_replay: bool = True) -> dict:
    profile = current_profile()
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
    return {
        "obs": "open" if running else "not open",
        "profile": profile or "unknown",
        "replay": replay_label,
        "ok": ok,
        "replay_known": replay,
    }
