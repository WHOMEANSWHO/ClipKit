"""Install ClipKit as a per-user Windows app (Start menu, Apps list, uninstall)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

from . import __version__
from .paths import is_frozen
from .startup import create_shortcut, start_menu_dir

UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ClipKit"
APP_PATHS_KEY = r"Software\Microsoft\Windows\CurrentVersion\App Paths\ClipKit.exe"
PUBLISHER = "WHOISWHO"
HOMEPAGE = "https://github.com/WHOMEANSWHO/ClipKit"
START_FOLDER = "ClipKit"
LEGACY_START_LINK = "ClipKit.lnk"


def install_dir() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return local / "Programs" / "ClipKit"


def installed_exe() -> Path:
    return install_dir() / "ClipKit.exe"


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def running_from_install() -> bool:
    if not is_frozen():
        return False
    return _same_file(Path(sys.executable), installed_exe())


def _desktop_dirs() -> list[Path]:
    found: list[Path] = []
    for path in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        try:
            if path.is_dir() and path not in found:
                found.append(path)
        except OSError:
            continue
    return found


def _write_shortcuts(exe: Path) -> None:
    folder = start_menu_dir() / START_FOLDER
    create_shortcut(
        folder / "ClipKit.lnk",
        exe,
        working_directory=exe.parent,
        icon=exe,
        description="ClipKit OBS clipping setup",
    )
    legacy = start_menu_dir() / LEGACY_START_LINK
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
    for desktop in _desktop_dirs():
        create_shortcut(
            desktop / "ClipKit.lnk",
            exe,
            working_directory=exe.parent,
            icon=exe,
            description="ClipKit OBS clipping setup",
        )


def _register_uninstall(exe: Path) -> None:
    size_kb = 0
    try:
        size_kb = max(1, exe.stat().st_size // 1024)
    except OSError:
        pass
    quoted = f'"{exe}"'
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    try:
        values = {
            "DisplayName": "ClipKit",
            "DisplayVersion": __version__,
            "Publisher": PUBLISHER,
            "InstallLocation": str(exe.parent),
            "DisplayIcon": f"{exe},0",
            "UninstallString": f"{quoted} --uninstall",
            "QuietUninstallString": f"{quoted} --uninstall --quiet",
            "HelpLink": HOMEPAGE,
            "URLInfoAbout": HOMEPAGE,
            "Comments": "One-click OBS clipping setup",
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
    finally:
        winreg.CloseKey(key)

    app_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, APP_PATHS_KEY)
    try:
        winreg.SetValueEx(app_key, "", 0, winreg.REG_SZ, str(exe))
        winreg.SetValueEx(app_key, "Path", 0, winreg.REG_SZ, str(exe.parent))
    finally:
        winreg.CloseKey(app_key)

    aumid = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AppUserModelId\ClipKit.Desktop")
    try:
        winreg.SetValueEx(aumid, "DisplayName", 0, winreg.REG_SZ, "ClipKit")
        winreg.SetValueEx(aumid, "IconUri", 0, winreg.REG_SZ, str(exe))
    finally:
        winreg.CloseKey(aumid)


def _delete_key(root: int, path: str) -> None:
    try:
        winreg.DeleteKey(root, path)
    except OSError:
        pass


def _remove_shortcuts() -> None:
    folder = start_menu_dir() / START_FOLDER
    link = folder / "ClipKit.lnk"
    for path in (link, start_menu_dir() / LEGACY_START_LINK):
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    if folder.is_dir():
        try:
            folder.rmdir()
        except OSError:
            pass
    for desktop in _desktop_dirs():
        extra = desktop / "ClipKit.lnk"
        if extra.is_file():
            try:
                extra.unlink()
            except OSError:
                pass


def _schedule_delete_folder(folder: Path) -> None:
    quoted = str(folder).replace('"', "")
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        flags |= subprocess.CREATE_NO_WINDOW
    startup = None
    if hasattr(subprocess, "STARTUPINFO"):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    subprocess.Popen(
        ["cmd.exe", "/c", f'ping 127.0.0.1 -n 4 >nul & rmdir /s /q "{quoted}"'],
        shell=False,
        creationflags=flags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        startupinfo=startup,
    )


def _copy_into_install(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and _same_file(src, dest):
        return True
    try:
        shutil.copy2(src, dest)
        return dest.is_file()
    except OSError:
        return dest.is_file()


def ensure_windows_app() -> bool:
    """Install or update the Windows app. False means this process should exit."""
    if not is_frozen() or os.environ.get("CLIPKIT_PORTABLE"):
        return True
    src = Path(sys.executable).resolve()
    dest = installed_exe()
    if not _copy_into_install(src, dest):
        return True
    _register_uninstall(dest)
    _write_shortcuts(dest)
    if _same_file(src, dest):
        return True
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([str(dest)], cwd=str(dest.parent), creationflags=flags)
    except OSError:
        return True
    return False


def uninstall_windows_app(*, quiet: bool = False) -> int:
    if not quiet:
        result = ctypes_yes_no(
            "Remove ClipKit from this PC?\n\n"
            "OBS and your clip settings are left alone."
        )
        if not result:
            return 0
    _remove_shortcuts()
    _delete_key(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    _delete_key(winreg.HKEY_CURRENT_USER, APP_PATHS_KEY)
    folder = install_dir()
    running = running_from_install()
    if running:
        _schedule_delete_folder(folder)
    elif folder.is_dir():
        try:
            shutil.rmtree(folder)
        except OSError:
            _schedule_delete_folder(folder)
    if not quiet:
        ctypes_info("ClipKit was removed from Windows.")
    return 0


def ctypes_yes_no(message: str) -> bool:
    import ctypes

    yes = 6
    return ctypes.windll.user32.MessageBoxW(None, message, "ClipKit", 0x04 | 0x20) == yes


def ctypes_info(message: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, message, "ClipKit", 0x40)
