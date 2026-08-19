"""Folders that work from source and from ClipKit.exe."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder with ClipKit.exe, or the repo root when running from source."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Bundled files (PyInstaller extract dir, or the repo)."""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return app_dir()


def scripts_dir() -> Path:
    bundled = resource_dir() / "scripts"
    if bundled.is_dir():
        return bundled
    return app_dir() / "scripts"


def _first_file(*parts: Path) -> Path | None:
    for path in parts:
        if path.is_file():
            return path
    return None


def icon_file() -> Path | None:
    root = resource_dir()
    return _first_file(
        root / "packaging" / "clipkit.ico",
        app_dir() / "packaging" / "clipkit.ico",
    )


def mark_file() -> Path | None:
    root = resource_dir()
    return _first_file(
        root / "packaging" / "clipkit-mark.png",
        root / "packaging" / "clipkit-icon.png",
        app_dir() / "packaging" / "clipkit-mark.png",
        app_dir() / "packaging" / "clipkit-icon.png",
    )
