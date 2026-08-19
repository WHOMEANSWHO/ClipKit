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

from . import __version__
from .paths import app_dir

GITHUB_LATEST = "https://api.github.com/repos/obsproject/obs-studio/releases/latest"
USER_AGENT = f"ClipKit/{__version__} (https://github.com/WHOMEANSWHO/ClipKit)"
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


def _cheap_locations() -> list[Path]:
    """Standard install paths only — safe to check on a timer."""
    env = os.environ
    program_files = Path(env.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local = Path(env.get("LOCALAPPDATA") or "")
    return [
        program_files / "obs-studio" / "bin" / "64bit" / "obs64.exe",
        program_files / "obs-studio" / "bin" / "32bit" / "obs32.exe",
        program_files_x86 / "obs-studio" / "bin" / "64bit" / "obs64.exe",
        program_files_x86 / "obs-studio" / "bin" / "32bit" / "obs32.exe",
        local / "Programs" / "obs-studio" / "bin" / "64bit" / "obs64.exe",
    ]


def _usual_locations() -> list[Path]:
    env = os.environ
    program_files = Path(env.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local = Path(env.get("LOCALAPPDATA") or "")
    home = Path.home()
    roots = [
        program_files,
        program_files_x86,
        local / "Programs",
        app_dir(),
        app_dir().parent,
        Path(env.get("ProgramData", r"C:\ProgramData")) / "chocolatey" / "lib" / "obs-studio",
        home / "scoop" / "apps" / "obs-studio",
        home / "scoop" / "apps" / "obs-studio-browser",
        program_files_x86 / "Steam" / "steamapps" / "common",
        program_files / "Steam" / "steamapps" / "common",
    ]
    names = ("obs-studio", "OBS", "OBS Studio", "obs")
    candidates: list[Path] = list(_cheap_locations())
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


def find_obs_exe(*, deep: bool = False) -> Path | None:
    """Find obs64.exe. Deep scan (shortcuts / other drives) is for background use only."""
    global _found_obs
    if _found_obs is not None:
        if _looks_like_obs(_found_obs):
            return _found_obs
        _forget_cached_path()

    getters = [
        _from_cache,
        lambda: _first_existing(_usual_locations()),
        _from_registry,
    ]
    if deep:
        getters.extend((_from_running_process, _from_shortcuts, _from_drive_scan))
    for getter in getters:
        found = getter()
        if found:
            return _remember(found)
    _forget_cached_path()
    return None


def obs_is_installed() -> bool:
    return find_obs_exe(deep=False) is not None


def obs_exe_present() -> bool:
    """Cheap check for the poller. Cache + Program Files only."""
    global _found_obs
    if _found_obs is not None:
        if _looks_like_obs(_found_obs):
            return True
        _forget_cached_path()
    if _from_cache() is not None:
        return True
    found = _first_existing(_cheap_locations())
    if found:
        _remember(found)
        return True
    return False


def _obs_popen(args: list[str], exe: Path) -> bool:
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


def launch_obs_plain() -> bool:
    """Start OBS with no ClipKit profile, so a first run can finish loading."""
    exe = find_obs_exe()
    if exe is None or not exe.is_file():
        return False
    if not _obs_popen([str(exe), "--disable-shutdown-check"], exe):
        return False
    reveal_obs_window()
    return True


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
    if not _obs_popen(args, exe):
        return False
    reveal_obs_window()
    return True


def obs_window_is_open() -> bool:
    """True when the OBS Studio window exists (not the ClipKit app)."""
    return bool(_obs_hwnds())


def _obs_hwnds() -> list[int]:
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        lower = title.lower()
        if "clipkit" in lower:
            return True
        if title.startswith("OBS") or "obs studio" in lower or "auto-configuration" in lower:
            found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return found


def wait_until_obs_ready(status: StatusFn | None = None, *, timeout: float = 90.0) -> bool:
    """Wait until OBS is running and its window has stayed open for a moment."""
    from .hardware import obs_is_running

    status = status or _noop
    deadline = time.monotonic() + timeout
    ready_since: float | None = None
    while time.monotonic() < deadline:
        reveal_obs_window()
        running = obs_is_running()
        window = obs_window_is_open()
        if running and window:
            if ready_since is None:
                ready_since = time.monotonic()
                status("OBS is open. Waiting until it finishes starting…")
            elif time.monotonic() - ready_since >= 2.0:
                return True
        else:
            ready_since = None
            status("Waiting for OBS to open…")
        time.sleep(0.3)
    return obs_is_running() and obs_window_is_open()


def prepare_obs_then_close(status: StatusFn | None = None) -> None:
    """Open OBS until it is fully up, then close it so ClipKit can write files."""
    from .hardware import obs_is_running, wait_until_obs_closed

    status = status or _noop
    if not obs_is_running():
        status("Starting OBS…")
        if not launch_obs_plain():
            raise RuntimeError("OBS is installed, but it would not start.")
    if not wait_until_obs_ready(status, timeout=90):
        raise RuntimeError("OBS started, but the window never finished opening.")
    status("OBS is running. Closing it so ClipKit can write settings…")
    close_obs()
    if not wait_until_obs_closed(timeout=20):
        raise RuntimeError(
            "OBS would not close. Check the tray icon, then click Apply again. FiveM can stay open."
        )


def reveal_obs_window() -> bool:
    """Bring the OBS window out of the tray / minimized state."""
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    SW_SHOW = 5
    shown = False
    for hwnd in _obs_hwnds():
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetForegroundWindow(hwnd)
        shown = True
    return shown


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


def _latest_installer(status: StatusFn) -> tuple[str, str]:
    status("Looking up the latest official OBS installer…")
    request = urllib.request.Request(GITHUB_LATEST, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    version = str(payload.get("tag_name") or payload.get("name") or "latest")
    for asset in payload.get("assets") or []:
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url")
        if name.endswith("Windows-x64-Installer.exe") and "arm64" not in name.lower() and url:
            return str(url), version
    raise RuntimeError("Could not find the official OBS Windows x64 installer on GitHub.")


def _download(url: str, dest: Path, status: StatusFn, *, label: str = "OBS Studio") -> None:
    status(f"Downloading {label}…")
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        read = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            handle.write(chunk)
            read += len(chunk)
            if total:
                status(f"Downloading {label}… {int(read * 100 / total)}%")
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


def _run_elevated(path: Path, params: str, status: StatusFn, *, show: bool = False) -> None:
    """Start a program as admin and wait until that process exits."""
    status("Windows may ask for permission. Click Yes, then wait — ClipKit keeps going.")
    see_mask_nocloseprocess = 0x00000040
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = see_mask_nocloseprocess
    info.lpVerb = "runas"
    info.lpFile = str(path)
    info.lpParameters = params
    info.nShow = 1 if show else 0
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
    return find_obs_exe(deep=True)


def _run_official_installer(installer: Path, status: StatusFn) -> Path | None:
    _run_elevated(installer, "/S", status, show=False)
    found = _wait_for_obs(status, 90)
    if found:
        return found
    status("Opening the OBS installer window. Finish it; ClipKit will continue after it closes.")
    _run_elevated(installer, "", status, show=True)
    return _wait_for_obs(status, 300)


def close_obs() -> None:
    hidden = _hidden()
    for name in ("obs64.exe", "obs32.exe", "obs.exe"):
        try:
            subprocess.run(
                ["taskkill", "/IM", name, "/F"],
                capture_output=True,
                timeout=15,
                creationflags=hidden,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _user_purge_obs() -> None:
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    local = Path(os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local"))
    leftovers = [
        appdata / "obs-studio",
        local / "obs-studio",
        appdata / "ClipKit" / "obs64-path.txt",
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "ClipKit OBS.lnk",
        appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "OBS Studio.lnk",
        home / "Desktop" / "OBS Studio.lnk",
        home / "OneDrive" / "Desktop" / "OBS Studio.lnk",
    ]
    for path in leftovers:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
        except OSError:
            pass
    _forget_cached_path()


def _elevated_purge_obs(status: StatusFn) -> None:
    status("Removing leftover OBS files… Windows may ask for permission.")
    script = r"""
$ErrorActionPreference = "Continue"
foreach ($p in @("C:\Program Files\obs-studio", "C:\Program Files (x86)\obs-studio")) {
  if (Test-Path -LiteralPath $p) {
    cmd /c "takeown /f `"$p`" /r /d Y >nul 2>&1"
    cmd /c "icacls `"$p`" /grant administrators:F /t /c /q >nul 2>&1"
    Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
  }
}
Remove-Item -LiteralPath "HKLM:\SOFTWARE\OBS Studio" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "HKLM:\SOFTWARE\WOW6432Node\OBS Studio" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\OBS Studio" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\OBS Studio" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\obs64.exe" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\OBS Studio.lnk" -Force -ErrorAction SilentlyContinue
exit 0
"""
    temp = Path(os.environ.get("TEMP") or ".") / "clipkit-purge-obs.ps1"
    temp.write_text(script, encoding="utf-8")
    try:
        _run_elevated(
            Path(shutil.which("powershell.exe") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"),
            f'-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{temp}"',
            status,
            show=False,
        )
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def purge_obs(status: StatusFn | None = None) -> None:
    """Close OBS and delete the app, settings, shortcuts, and leftover registry."""
    status = status or _noop
    status("Closing OBS…")
    close_obs()
    time.sleep(1)
    winget = shutil.which("winget")
    if winget:
        status("Uninstalling OBS Studio…")
        try:
            _run(
                [
                    winget,
                    "uninstall",
                    "-e",
                    "--id",
                    WINGET_ID,
                    "--disable-interactivity",
                    "--accept-source-agreements",
                ],
                timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    _user_purge_obs()
    try:
        _elevated_purge_obs(status)
    except RuntimeError as exc:
        if "permission prompt was closed" in str(exc).lower():
            raise
    close_obs()
    _forget_cached_path()
    time.sleep(1)


def _install_from_github(status: StatusFn) -> Path | None:
    installer = _installer_path()
    url, version = _latest_installer(status)
    _download(url, installer, status, label=f"OBS Studio {version}")
    found = _run_official_installer(installer, status)
    if found:
        try:
            installer.unlink(missing_ok=True)
        except OSError:
            pass
    return found


def install_obs(status: StatusFn | None = None, *, force: bool = False) -> Path:
    """Install official OBS Studio if needed. Returns the obs64.exe path."""
    status = status or _noop
    if not force:
        existing = find_obs_exe(deep=True)
        if existing:
            return existing
    _forget_cached_path()

    found = _install_from_github(status)
    if found:
        return found

    if _install_with_winget(status):
        found = find_obs_exe()
        if found:
            return found

    raise RuntimeError(
        "OBS installer ran, but obs64.exe was not found. "
        "Open OBS once from the Start menu, then run ClipKit again."
    )


def fresh_install_obs(status: StatusFn | None = None) -> Path:
    """Wipe OBS, then install the newest official Windows build."""
    status = status or _noop
    purge_obs(status)
    status("Installing the latest official OBS Studio…")
    return install_obs(status, force=True)
