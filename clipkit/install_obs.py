"""Find OBS Studio, or download the official Windows installer and set it up."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import time
import urllib.request
import winreg
from collections.abc import Callable, Iterable
from ctypes import wintypes
from pathlib import Path

from .paths import app_dir

GITHUB_LATEST = "https://api.github.com/repos/obsproject/obs-studio/releases/latest"
USER_AGENT = "ClipKit/1.1 (https://github.com/WHOMEANSWHO/ClipKit)"
WINGET_ID = "OBSProject.OBSStudio"
OBS_EXE_NAMES = ("obs64.exe", "obs32.exe")
_SKIP_PATH_PARTS = ("streamlabs", "windowsapps", "$recycle.bin", "system volume information")
_HINT_DIR_NAMES = (
    "obs",
    "program",
    "tool",
    "app",
    "soft",
    "game",
    "portable",
    "util",
    "bin",
    "video",
    "stream",
    "record",
    "capture",
    "media",
)

StatusFn = Callable[[str], None]

_found_obs: Path | None = None


def _noop(_message: str) -> None:
    return None


def _cache_file() -> Path:
    return Path.home() / "AppData" / "Roaming" / "ClipKit" / "obs64-path.txt"


def _remember(path: Path) -> Path:
    global _found_obs
    resolved = path.resolve()
    _found_obs = resolved
    cache = _cache_file()
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(str(resolved), encoding="utf-8")
    except OSError:
        pass
    return resolved


def _looks_like_obs(path: Path) -> bool:
    lower = str(path).lower().replace("/", "\\")
    if any(part in lower for part in _SKIP_PATH_PARTS):
        return False
    return path.is_file() and path.name.lower() in OBS_EXE_NAMES


def _exe_from_guess(value: str | Path | None) -> Path | None:
    if not value:
        return None
    raw = str(value).strip().strip('"')
    if not raw:
        return None
    if "," in raw and not Path(raw).exists():
        raw = raw.rsplit(",", 1)[0].strip().strip('"')
    path = Path(raw)
    try:
        if _looks_like_obs(path):
            return path
        if path.is_dir():
            for name in OBS_EXE_NAMES:
                for rel in (
                    Path("bin") / "64bit" / name,
                    Path("bin") / "32bit" / name,
                    Path(name),
                ):
                    candidate = path / rel
                    if _looks_like_obs(candidate):
                        return candidate
        parent = path.parent
        for rel in (
            Path("bin") / "64bit" / "obs64.exe",
            Path("obs64.exe"),
        ):
            candidate = parent / rel
            if _looks_like_obs(candidate):
                return candidate
    except OSError:
        return None
    return None


def _first_existing(paths: Iterable[Path | None]) -> Path | None:
    for path in paths:
        found = _exe_from_guess(path) if path is not None else None
        if found:
            return found
    return None


def _forget_cached_path() -> None:
    global _found_obs
    _found_obs = None
    cache = _cache_file()
    try:
        cache.unlink(missing_ok=True)
    except OSError:
        pass


def _from_cache() -> Path | None:
    cache = _cache_file()
    if not cache.is_file():
        return None
    try:
        found = _exe_from_guess(cache.read_text(encoding="utf-8").strip())
    except OSError:
        found = None
    if found is None:
        _forget_cached_path()
    return found


def _usual_locations() -> list[Path]:
    env = os.environ
    program_files = Path(env.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local = Path(env.get("LOCALAPPDATA", ""))
    home = Path.home()
    roots = [
        program_files,
        program_files_x86,
        local / "Programs",
        home,
        home / "Documents",
        home / "Desktop",
        home / "Downloads",
        app_dir(),
        app_dir().parent,
        Path(env.get("ProgramData", r"C:\ProgramData")) / "chocolatey" / "lib" / "obs-studio",
        home / "scoop" / "apps" / "obs-studio",
        home / "scoop" / "apps" / "obs-studio-browser",
        program_files_x86 / "Steam" / "steamapps" / "common",
        program_files / "Steam" / "steamapps" / "common",
    ]
    names = ("obs-studio", "OBS", "OBS Studio", "obs")
    candidates: list[Path] = []
    for root in roots:
        for name in names:
            folder = root / name
            candidates.append(folder / "bin" / "64bit" / "obs64.exe")
            candidates.append(folder / "obs64.exe")
        candidates.append(root / "bin" / "64bit" / "obs64.exe")
        candidates.append(root / "obs64.exe")
    which = shutil.which("obs64") or shutil.which("obs32")
    if which:
        candidates.append(Path(which))
    return candidates


def _reg_value(root: int, path: str, name: str = "") -> str | None:
    try:
        key = winreg.OpenKey(root, path)
    except OSError:
        return None
    try:
        value, _typ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    finally:
        winreg.CloseKey(key)
    return str(value) if value else None


def _reg_subkeys(root: int, path: str) -> list[str]:
    try:
        key = winreg.OpenKey(root, path)
    except OSError:
        return []
    names: list[str] = []
    try:
        index = 0
        while True:
            try:
                names.append(winreg.EnumKey(key, index))
            except OSError:
                break
            index += 1
    finally:
        winreg.CloseKey(key)
    return names


def _from_registry() -> Path | None:
    app_paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\obs64.exe"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\obs64.exe"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\OBS Studio"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\OBS Studio"),
    ]
    for root, path in app_paths:
        found = _exe_from_guess(_reg_value(root, path))
        if found:
            return found
        found = _exe_from_guess(_reg_value(root, path, "InstallLocation"))
        if found:
            return found

    uninstall_roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for root, base in uninstall_roots:
        for sub in _reg_subkeys(root, base):
            key_path = f"{base}\\{sub}"
            display = (_reg_value(root, key_path, "DisplayName") or "").lower()
            if "obs studio" not in display and display != "obs":
                continue
            if "streamlabs" in display:
                continue
            for field in ("InstallLocation", "DisplayIcon", "UninstallString", "InstallSource"):
                found = _exe_from_guess(_reg_value(root, key_path, field))
                if found:
                    return found
    return None


def _from_running_process() -> Path | None:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='obs64.exe' OR Name='obs32.exe'\" "
        "| Select-Object -ExpandProperty ExecutablePath"
    )
    try:
        result = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=12)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in result.stdout.splitlines():
        found = _exe_from_guess(line.strip())
        if found:
            return found
    return None


def _shortcut_folders() -> list[Path]:
    home = Path.home()
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    return [
        home / "Desktop",
        home / "OneDrive" / "Desktop",
        home / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu",
        program_data / "Microsoft" / "Windows" / "Start Menu",
        home / "AppData" / "Roaming" / "Microsoft" / "Internet Explorer" / "Quick Launch",
    ]


def _from_shortcuts() -> Path | None:
    links: list[Path] = []
    for folder in _shortcut_folders():
        if not folder.is_dir():
            continue
        try:
            links.extend(folder.rglob("*.lnk"))
        except OSError:
            continue
    obs_links = [
        path
        for path in links
        if "obs" in path.stem.lower() and "streamlabs" not in path.stem.lower()
    ]
    if not obs_links:
        return None
    listed = ",".join(f"'{str(path).replace(chr(39), chr(39)*2)}'" for path in obs_links[:40])
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"@({listed}) | ForEach-Object {{ try {{ $shell.CreateShortcut($_).TargetPath }} catch {{}} }}"
    )
    try:
        result = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in result.stdout.splitlines():
        found = _exe_from_guess(line.strip())
        if found:
            return found
    return None


def _obs_in_folder(folder: Path) -> Path | None:
    try:
        if not folder.is_dir():
            return None
    except OSError:
        return None
    lower = folder.name.lower()
    if any(part in lower for part in ("streamlabs", "$recycle.bin", "windowsapps")):
        return None
    for name in OBS_EXE_NAMES:
        for rel in (Path("bin") / "64bit" / name, Path("bin") / "32bit" / name, Path(name)):
            candidate = folder / rel
            if _looks_like_obs(candidate):
                return candidate
    return None


def _scan_root(root: Path) -> Path | None:
    try:
        children = list(root.iterdir())
    except OSError:
        return None
    for child in children:
        found = _obs_in_folder(child)
        if found:
            return found
    for child in children:
        try:
            if not child.is_dir():
                continue
        except OSError:
            continue
        lower = child.name.lower()
        if not any(hint in lower for hint in _HINT_DIR_NAMES):
            continue
        try:
            nested = list(child.iterdir())
        except OSError:
            continue
        for item in nested:
            found = _obs_in_folder(item)
            if found:
                return found
    return None


def _from_drive_scan() -> Path | None:
    get_drive_type = ctypes.windll.kernel32.GetDriveTypeW
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint
    # 2 = removable, 3 = fixed. Skip network/CD so missing-OBS checks do not hang.
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = f"{letter}:\\"
        if get_drive_type(root) not in {2, 3}:
            continue
        found = _scan_root(Path(root))
        if found:
            return found
    return None


def find_obs_exe() -> Path | None:
    """Find obs64.exe in standard folders, registry, shortcuts, or other drives."""
    global _found_obs
    if _found_obs is not None:
        if _looks_like_obs(_found_obs):
            return _found_obs
        _forget_cached_path()

    for getter in (
        _from_cache,
        lambda: _first_existing(_usual_locations()),
        _from_registry,
        _from_running_process,
        _from_shortcuts,
        _from_drive_scan,
    ):
        found = getter()
        if found:
            return _remember(found)
    _forget_cached_path()
    return None


def obs_is_installed() -> bool:
    return find_obs_exe() is not None


def obs_exe_present() -> bool:
    """Cheap check for the poller. Does not scan other drives."""
    global _found_obs
    if _found_obs is not None:
        if _looks_like_obs(_found_obs):
            return True
        _forget_cached_path()
    if _from_cache() is not None:
        return True
    found = _first_existing(_usual_locations())
    if found:
        _remember(found)
        return True
    return False


def launch_obs_clipkit() -> bool:
    """Start OBS with the ClipKit profile and replay buffer, as a normal window."""
    exe = find_obs_exe()
    if exe is None or not exe.is_file():
        return False
    args = [
        str(exe),
        "--startreplaybuffer",
        "--profile",
        "ClipKit",
        "--collection",
        "ClipKit",
        "--disable-shutdown-check",
    ]
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(args, cwd=str(exe.parent), creationflags=flags)
    except OSError:
        return False
    return True


def _hidden() -> int:
    return subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def _run(command: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=_hidden(),
    )


def _install_with_winget(status: StatusFn) -> bool:
    winget = shutil.which("winget")
    if not winget:
        return False
    status("Installing OBS Studio with winget… Windows may ask for permission.")
    try:
        result = _run(
            [
                winget,
                "install",
                "-e",
                "--id",
                WINGET_ID,
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    # 0 = installed, -1978335189 (0x8A15002B) often means already installed
    if result.returncode in {0, -1978335189}:
        return _wait_for_obs(status, 60) is not None
    return _wait_for_obs(status, 15) is not None


def _latest_installer_url(status: StatusFn) -> str:
    status("Looking up the latest official OBS installer…")
    request = urllib.request.Request(GITHUB_LATEST, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url")
        if name.endswith("Windows-x64-Installer.exe") and url:
            return str(url)
    raise RuntimeError("Could not find the official OBS Windows installer on GitHub.")


def _download(url: str, dest: Path, status: StatusFn) -> None:
    status("Downloading OBS Studio…")
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response, dest.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        read = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            handle.write(chunk)
            read += len(chunk)
            if total:
                status(f"Downloading OBS Studio… {int(read * 100 / total)}%")
    if dest.stat().st_size < 1_000_000:
        raise RuntimeError("OBS download looked incomplete. Check your internet and try again.")


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _installer_path() -> Path:
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return local / "ClipKit" / "OBS-Studio-Installer.exe"


def _run_elevated(path: Path, params: str, status: StatusFn) -> None:
    """Start the installer as admin and wait until that process exits."""
    status("Windows may ask for permission. Click Yes, then wait — ClipKit keeps going.")
    see_mask_nocloseprocess = 0x00000040
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = see_mask_nocloseprocess
    info.lpVerb = "runas"
    info.lpFile = str(path)
    info.lpParameters = params
    info.nShow = 1
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.get_last_error()
        if err in {1223, 5}:
            raise RuntimeError(
                "The Windows permission prompt was closed. Click Apply again and choose Yes."
            )
        raise RuntimeError(f"Could not start the OBS installer (Windows error {err}).")
    handle = info.hProcess
    if not handle:
        return
    try:
        waited = ctypes.windll.kernel32.WaitForSingleObject(handle, 900_000)
        if waited == 0x00000102:
            raise RuntimeError(
                "The OBS installer is still running after 15 minutes. Finish it, then click Apply again."
            )
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _wait_for_obs(status: StatusFn, seconds: int = 180) -> Path | None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _forget_cached_path()
        found = _first_existing(_usual_locations()) or _from_registry()
        if found:
            return _remember(found)
        left = max(0, int(deadline - time.monotonic()))
        status(f"Waiting for OBS to finish installing… {left}s")
        time.sleep(2)
    _forget_cached_path()
    return find_obs_exe()


def _run_official_installer(installer: Path, status: StatusFn) -> Path | None:
    _run_elevated(installer, "/S", status)
    found = _wait_for_obs(status, 90)
    if found:
        return found
    status("Opening the OBS installer window. Finish it; ClipKit will continue after it closes.")
    _run_elevated(installer, "", status)
    return _wait_for_obs(status, 300)


def install_obs(status: StatusFn | None = None) -> Path:
    """Install official OBS Studio if needed. Returns the obs64.exe path."""
    status = status or _noop
    existing = find_obs_exe()
    if existing:
        return existing

    if _install_with_winget(status):
        found = find_obs_exe()
        if found:
            return found

    installer = _installer_path()
    url = _latest_installer_url(status)
    _download(url, installer, status)
    found = _run_official_installer(installer, status)
    if found:
        try:
            installer.unlink(missing_ok=True)
        except OSError:
            pass
        return found

    raise RuntimeError(
        "OBS installer ran, but obs64.exe was not found. "
        "Open OBS once from the Start menu, then run ClipKit again."
    )
