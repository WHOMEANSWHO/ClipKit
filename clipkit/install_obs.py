"""Find OBS Studio, or download the official Windows installer and set it up."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import winreg
from collections.abc import Callable, Iterable
from pathlib import Path

from .paths import app_dir

GITHUB_LATEST = "https://api.github.com/repos/obsproject/obs-studio/releases/latest"
USER_AGENT = "ClipKit/0.3 (https://obsproject.com)"
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


def _from_cache() -> Path | None:
    cache = _cache_file()
    if not cache.is_file():
        return None
    try:
        return _exe_from_guess(cache.read_text(encoding="utf-8").strip())
    except OSError:
        return None


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
    if _found_obs is not None and _looks_like_obs(_found_obs):
        return _found_obs

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
    return None


def obs_is_installed() -> bool:
    return find_obs_exe() is not None


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
            timeout=900,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    # 0 = installed, -1978335189 (0x8A15002B) often means already installed
    if result.returncode in {0, -1978335189} or find_obs_exe():
        return True
    return False


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


def _silent_install(installer: Path, status: StatusFn) -> None:
    status("Installing OBS Studio… Windows may ask for permission.")
    # NSIS silent install. /S must be capital S.
    result = subprocess.run(
        [str(installer), "/S"],
        timeout=900,
    )
    if result.returncode not in {0, None} and not find_obs_exe():
        raise RuntimeError(
            "OBS installer did not finish. If a permission prompt appeared, accept it and try again."
        )


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

    url = _latest_installer_url(status)
    with tempfile.TemporaryDirectory(prefix="clipkit-obs-") as tmp:
        installer = Path(tmp) / "OBS-Studio-Installer.exe"
        _download(url, installer, status)
        _silent_install(installer, status)

    found = find_obs_exe()
    if not found:
        raise RuntimeError(
            "OBS installed, but obs64.exe was not found. Open OBS once from the Start menu, then run ClipKit again."
        )
    return found
