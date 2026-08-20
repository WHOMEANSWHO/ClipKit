"""Install a hidden Medal folder watcher that copies clips into FiveM server folders."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .paths import scripts_dir
from .startup import create_shortcut, windows_startup_dir

STARTUP_NAME = "ClipKit Medal sorter.lnk"
SORTER_SCRIPT = "clipkit_medal_sorter.ps1"
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PATH_RE = re.compile(r"[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]*")
SKIP_PATH_HINTS = (
    "medalsetup",
    "node_modules",
    r"appdata\local\medal\app-",
    r"appdata\local\medal\recorder-",
    r"\downloads\\",
)


def clipkit_data_dir() -> Path:
    path = Path.home() / "AppData" / "Roaming" / "ClipKit"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sorter_script_path() -> Path:
    return clipkit_data_dir() / SORTER_SCRIPT


def sorter_config_path() -> Path:
    return clipkit_data_dir() / "medal-sorter.json"


def powershell_exe() -> Path:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def find_medal_exe() -> Path | None:
    local = Path.home() / "AppData" / "Local" / "Medal" / "Medal.exe"
    if local.is_file():
        return local
    programs = Path.home() / "AppData" / "Local" / "Programs" / "Medal" / "Medal.exe"
    if programs.is_file():
        return programs
    return None


def medal_is_installed() -> bool:
    return find_medal_exe() is not None or bool(default_medal_folders())


def default_medal_folders() -> list[Path]:
    folders: list[Path] = []
    for path in (
        Path(r"D:\vids\medal"),
        Path(r"C:\Medal"),
        Path.home() / "Videos" / "Medal",
        Path(r"D:\Medal"),
    ):
        if path.is_dir() and path not in folders:
            folders.append(path)
    return folders


def _skip_discovered_path(path: Path) -> bool:
    text = str(path).lower()
    return any(hint in text for hint in SKIP_PATH_HINTS)


def _paths_from_json_file(path: Path) -> list[Path]:
    if not path.is_file() or path.stat().st_size > 2_000_000:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    found: list[Path] = []
    for match in PATH_RE.findall(text):
        candidate = Path(match)
        if _skip_discovered_path(candidate):
            continue
        if candidate.is_dir() and candidate not in found:
            found.append(candidate)
    return found


def find_medal_capture_folders() -> list[Path]:
    folders = default_medal_folders()
    search_roots = (
        Path.home() / "AppData" / "Roaming" / "Medal" / "store",
        Path.home() / "AppData" / "Local" / "Medal",
    )
    discovered: list[Path] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        try:
            files = list(root.glob("*.json"))
        except OSError:
            continue
        for json_file in files:
            for path in _paths_from_json_file(json_file):
                name = path.name.lower()
                if "medal" in name or "clip" in name or "video" in name:
                    if path not in discovered:
                        discovered.append(path)
    for path in discovered:
        if path not in folders:
            folders.append(path)
    if not folders:
        return [Path(r"D:\vids\medal")]
    folders.sort(
        key=lambda path: (
            (path / "Clips").is_dir(),
            "medal" in path.name.lower(),
        ),
        reverse=True,
    )
    best = folders[0]
    if (best / "Clips").is_dir():
        return [best]
    return folders


def _run_hidden(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=HIDDEN,
    )


def stop_medal_sorter() -> None:
    script = str(sorter_script_path()).replace("'", "''")
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -match 'powershell' -and $_.CommandLine -like "
        f"'*{script}*' }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        _run_hidden(
            [
                str(powershell_exe()),
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-Command",
                command,
            ]
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def start_medal_sorter() -> bool:
    ps1 = sorter_script_path()
    if not ps1.is_file():
        return False
    exe = powershell_exe()
    if not exe.is_file():
        return False
    try:
        subprocess.Popen(
            [
                str(exe),
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
            ],
            cwd=str(clipkit_data_dir()),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=HIDDEN,
            close_fds=True,
        )
    except OSError:
        return False
    time.sleep(0.4)
    return True


def remove_medal_startup() -> None:
    path = windows_startup_dir() / STARTUP_NAME
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def disable_medal_sorter() -> None:
    """Stop the watcher and remove it from Windows Startup. Opt in later with Set up Medal sorting."""
    stop_medal_sorter()
    remove_medal_startup()


def install_medal_startup() -> Path | None:
    ps1 = sorter_script_path()
    exe = powershell_exe()
    if not ps1.is_file() or not exe.is_file():
        return None
    return create_shortcut(
        windows_startup_dir() / STARTUP_NAME,
        exe,
        arguments=(
            "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass "
            f'-File "{ps1}"'
        ),
        working_directory=clipkit_data_dir(),
        icon=exe,
        description="ClipKit Medal clip sorter",
        minimized=True,
    )


def write_medal_sorter_config(output_dir: Path, watch: list[Path] | None = None) -> dict:
    folders = [str(path) for path in (watch or find_medal_capture_folders())]
    payload = {
        "watch": folders,
        "output": str(Path(output_dir)),
    }
    path = sorter_config_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def install_medal_sorter(output_dir: Path | None = None) -> dict:
    """Copy the watcher into AppData, start it, and keep it on Windows Startup."""
    watch = find_medal_capture_folders()
    dest = watch[0] if watch else Path(output_dir or r"D:\vids\medal")
    dest.mkdir(parents=True, exist_ok=True)
    source = scripts_dir() / SORTER_SCRIPT
    if not source.is_file():
        raise FileNotFoundError(f"Medal sorter script is missing: {source}")
    shutil.copy2(source, sorter_script_path())
    seen = clipkit_data_dir() / "medal-sorter-seen.json"
    try:
        seen.unlink(missing_ok=True)
    except OSError:
        pass
    config = write_medal_sorter_config(dest, watch=[dest])
    stop_medal_sorter()
    started = start_medal_sorter()
    startup = install_medal_startup()
    watch_paths = [Path(item) for item in config.get("watch") or []]
    existing = [path for path in watch_paths if path.is_dir()]
    return {
        "watch": [str(path) for path in watch_paths],
        "watch_existing": [str(path) for path in existing],
        "output_dir": str(dest),
        "started": started,
        "startup": bool(startup),
        "medal_installed": find_medal_exe() is not None,
    }
