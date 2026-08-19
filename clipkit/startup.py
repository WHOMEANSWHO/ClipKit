"""Normal Windows shortcuts for ClipKit and OBS — no .bat / .cmd files."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .install_obs import find_obs_exe
from .paths import app_dir, is_frozen

STARTUP_NAME = "ClipKit OBS.lnk"
LEGACY_STARTUP_NAMES = (
    "ClipKit OBS.cmd",
    "ClipKit OBS.bat",
)
LAUNCHER_NAME = "ClipKit.lnk"


def windows_startup_dir() -> Path:
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def start_menu_dir() -> Path:
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
    )


def _ps_single(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcut(
    path: Path,
    target: Path,
    *,
    arguments: str = "",
    working_directory: Path | None = None,
    icon: Path | None = None,
    description: str = "",
    minimized: bool = False,
) -> Path | None:
    """Create a .lnk shortcut. Returns the path, or None if it could not be written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    work = working_directory or Path(target).parent
    icon_path = icon or target
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$link = $shell.CreateShortcut({_ps_single(path)}); "
        f"$link.TargetPath = {_ps_single(target)}; "
        f"$link.WorkingDirectory = {_ps_single(work)}; "
        f"$link.Arguments = {_ps_single(arguments)}; "
        f"$link.IconLocation = {_ps_single(str(icon_path) + ',0')}; "
        f"$link.Description = {_ps_single(description)}; "
        f"$link.WindowStyle = {7 if minimized else 1}; "
        "$link.Save()"
    )
    hidden = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=hidden,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not path.exists():
        return None
    return path


def pythonw_exe() -> Path:
    if is_frozen():
        return Path(sys.executable)
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        candidate = exe.with_name("pythonw.exe")
        if candidate.is_file():
            return candidate
    return exe


def install_clipkit_launcher_shortcuts() -> list[Path]:
    """Put a normal ClipKit shortcut in the Start menu (and this folder, from source)."""
    root = app_dir()
    pythonw = pythonw_exe()
    if is_frozen():
        target = pythonw
        arguments = ""
        icon = target
        dests = [start_menu_dir() / LAUNCHER_NAME]
    else:
        launcher = root / "clipkit.pyw"
        if not launcher.is_file():
            launcher = root / "clipkit.py"
        target = pythonw
        arguments = _quoted(launcher)
        icon = pythonw
        dests = [root / LAUNCHER_NAME, start_menu_dir() / LAUNCHER_NAME]

    created: list[Path] = []
    for dest in dests:
        path = create_shortcut(
            dest,
            target,
            arguments=arguments,
            working_directory=root,
            icon=icon,
            description="ClipKit OBS clipping setup",
        )
        if path:
            created.append(path)
    return created


def _quoted(path: Path) -> str:
    text = str(path)
    if " " in text and not text.startswith('"'):
        return f'"{text}"'
    return text


def remove_obs_windows_startup() -> None:
    folder = windows_startup_dir()
    for name in (*LEGACY_STARTUP_NAMES, STARTUP_NAME):
        path = folder / name
        if path.exists():
            path.unlink()


def migrate_legacy_obs_startup() -> None:
    """Replace an old Startup .cmd with a normal OBS shortcut."""
    folder = windows_startup_dir()
    if not any((folder / name).exists() for name in LEGACY_STARTUP_NAMES):
        return
    if install_obs_windows_startup() is None:
        for name in LEGACY_STARTUP_NAMES:
            path = folder / name
            if path.exists():
                path.unlink()


def install_obs_windows_startup(obs_exe: Path | None = None) -> Path | None:
    """Put a normal OBS shortcut in Windows Startup (tray + replay buffer)."""
    exe = Path(obs_exe) if obs_exe else find_obs_exe()
    if exe is None or not exe.is_file():
        return None

    remove_obs_windows_startup()
    return create_shortcut(
        windows_startup_dir() / STARTUP_NAME,
        exe,
        arguments=(
            "--minimize-to-tray --startreplaybuffer "
            "--profile ClipKit --collection ClipKit --disable-shutdown-check"
        ),
        working_directory=exe.parent,
        icon=exe,
        description="OBS Studio",
        minimized=True,
    )
