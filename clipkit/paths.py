"""Folders that work from source and from ClipKit.exe."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write a file in one step so a crash cannot leave it half-written.

    The text goes to a temporary file in the same folder, is flushed to disk,
    then atomically renamed over the target. A partially written temp file is
    cleaned up on failure so it never shadows the real file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder with ClipKit.exe, or the repo root when running from source."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def leave_extract_dir() -> None:
    """Onefile PyInstaller cannot delete _MEI* if our working directory is inside it."""
    if not is_frozen():
        return
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = [
        app_dir(),
        Path.home(),
        Path(os.environ.get("SystemRoot", r"C:\Windows")),
    ]
    for target in candidates:
        try:
            resolved = target.resolve()
            if meipass and resolved == Path(meipass).resolve():
                continue
            os.chdir(resolved)
            return
        except OSError:
            continue


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


def _registry_videos_dir() -> Path | None:
    """Windows Videos library path from Explorer shell folders (OneDrive-aware)."""
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    keys = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"),
    )
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as handle:
                value, _ = winreg.QueryValueEx(handle, "My Video")
        except OSError:
            continue
        text = str(value or "").strip().strip('"')
        if not text:
            continue
        expanded = os.path.expandvars(text).strip()
        if expanded:
            return Path(expanded)
    return None


def videos_dir() -> Path:
    """Best Videos folder for this PC (registry known folder, else ~/Videos)."""
    known = _registry_videos_dir()
    if known is not None:
        return known
    return Path.home() / "Videos"


def appdata_dir() -> Path:
    """%APPDATA% (Roaming), with a home fallback when the env var is missing."""
    raw = (os.environ.get("APPDATA") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Roaming"


def local_appdata_dir() -> Path:
    """%LOCALAPPDATA%, with a home fallback when the env var is missing."""
    raw = (os.environ.get("LOCALAPPDATA") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Local"


def same_path(left: Path | str | None, right: Path | str | None) -> bool:
    """True when two paths point at the same place (case/slash-insensitive on Windows)."""
    if left is None or right is None:
        return False
    a = str(left).strip()
    b = str(right).strip()
    if not a or not b:
        return False

    def _norm(text: str) -> str:
        text = text.replace("\\", "/")
        while "//" in text:
            text = text.replace("//", "/")
        if len(text) > 1 and text.endswith("/"):
            text = text.rstrip("/")
        return text.lower()

    if _norm(a) == _norm(b):
        return True
    try:
        return _norm(str(Path(a).resolve())) == _norm(str(Path(b).resolve()))
    except OSError:
        return False


def ensure_directory(path: Path) -> Path:
    """Create a folder (and parents). Raises OSError if it cannot be made."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise FileNotFoundError(2, "The system cannot find the file specified", str(path))
    return path


def ensure_clips_dir(preferred: Path | str | None = None) -> Path:
    """
    Create the clips folder. Prefer the path the user chose; if Videos (or
    OneDrive Videos) is missing or broken, fall back to Documents\\ClipKit,
    then %USERPROFILE%\\ClipKit.
    """
    candidates: list[Path] = []
    if preferred is not None and str(preferred).strip():
        candidates.append(Path(str(preferred).strip()))
    for fallback in (
        videos_dir() / "ClipKit",
        Path.home() / "Videos" / "ClipKit",
        Path.home() / "Documents" / "ClipKit",
        Path.home() / "ClipKit",
    ):
        if fallback not in candidates:
            candidates.append(fallback)

    errors: list[OSError] = []
    for candidate in candidates:
        try:
            return ensure_directory(candidate)
        except OSError as exc:
            errors.append(exc)
    if errors:
        first = errors[0]
        wanted = candidates[0]
        raise OSError(
            getattr(first, "errno", 2),
            (
                f"Could not create the clips folder '{wanted}'. "
                "Your Videos folder may be missing or moved by OneDrive. "
                "Click Browse and pick another folder (for example Documents)."
            ),
            str(wanted),
        ) from first
    raise FileNotFoundError(2, "No clips folder path was given", "")
