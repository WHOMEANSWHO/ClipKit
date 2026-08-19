"""Detect GPU, CPU, RAM, display, and whether OBS is installed/running."""

from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio import CaptureDevice, list_capture_devices
from .install_obs import obs_exe_present


@dataclass
class Hardware:
    cpu_name: str = "Unknown CPU"
    ram_gb: float = 0.0
    gpu_name: str = "Unknown GPU"
    gpu_vendor: str = "unknown"  # nvidia, amd, intel, unknown
    vram_gb: float = 0.0
    display_width: int = 1920
    display_height: int = 1080
    obs_installed: bool = False
    obs_running: bool = False
    obs_exe: Path | None = None
    obs_config_dir: Path | None = None
    notes: list[str] = field(default_factory=list)
    mics: list[CaptureDevice] = field(default_factory=list)

    @property
    def display_label(self) -> str:
        return f"{self.display_width}x{self.display_height}"


def _hardware_cache_path() -> Path:
    return Path.home() / "AppData" / "Roaming" / "ClipKit" / "hardware.json"


def load_cached_hardware() -> Hardware | None:
    path = _hardware_cache_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("gpu_name"):
        return None
    hw = Hardware()
    hw.cpu_name = str(data.get("cpu_name") or hw.cpu_name)
    hw.ram_gb = float(data.get("ram_gb") or 0)
    hw.gpu_name = str(data.get("gpu_name") or hw.gpu_name)
    hw.gpu_vendor = str(data.get("gpu_vendor") or hw.gpu_vendor)
    hw.vram_gb = float(data.get("vram_gb") or 0)
    hw.display_width = int(data.get("display_width") or 1920)
    hw.display_height = int(data.get("display_height") or 1080)
    hw.obs_running = obs_is_running()
    hw.obs_installed = obs_exe_present()
    return hw


def save_cached_hardware(hw: Hardware) -> None:
    path = _hardware_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "cpu_name": hw.cpu_name,
                    "ram_gb": hw.ram_gb,
                    "gpu_name": hw.gpu_name,
                    "gpu_vendor": hw.gpu_vendor,
                    "vram_gb": hw.vram_gb,
                    "display_width": hw.display_width,
                    "display_height": hw.display_height,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


_kernel32 = ctypes.windll.kernel32
_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_TH32CS_SNAPPROCESS = 0x00000002
_INVALID_HANDLE = ctypes.c_void_p(-1).value


def obs_is_running() -> bool:
    """True if OBS is running. Uses a process snapshot, not tasklist."""
    wanted = {"obs64.exe", "obs32.exe", "obs.exe"}
    snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snap or int(snap) == _INVALID_HANDLE:
        return _obs_running_tasklist()
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not _kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return False
        while True:
            if entry.szExeFile.lower() in wanted:
                return True
            if not _kernel32.Process32NextW(snap, ctypes.byref(entry)):
                return False
    finally:
        _kernel32.CloseHandle(snap)


def _obs_running_tasklist() -> bool:
    hidden = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=hidden,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    out = (result.stdout or "").lower()
    return "obs64.exe" in out or "obs32.exe" in out


def _powershell(script: str) -> str:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(Path.home()),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "PowerShell query failed")
    return completed.stdout.strip()


def _nvidia_smi() -> tuple[str, float] | None:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return None
    try:
        out = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        line = out.stdout.strip().splitlines()[0]
        name, mem = [part.strip() for part in line.split(",", 1)]
        return name, round(float(mem) / 1024.0, 1)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _vendor_from_name(name: str) -> str:
    lower = name.lower()
    if any(token in lower for token in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
        return "nvidia"
    if any(token in lower for token in ("amd", "radeon", "rx ")):
        return "amd"
    if any(token in lower for token in ("intel", "arc ", "uhd", "iris")):
        return "intel"
    return "unknown"


def _is_igpu(name: str) -> bool:
    lower = name.lower()
    return any(
        token in lower
        for token in (
            "radeon(tm) graphics",
            "radeon graphics",
            "uhd graphics",
            "iris",
            "vega",
        )
    ) and "rx " not in lower and "arc " not in lower


def detect() -> Hardware:
    hw = Hardware()
    script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$gpus = @(Get-CimInstance Win32_VideoController | Where-Object {
    $_.Name -and $_.Name -notmatch 'Oray|Remote|Basic Display|Microsoft Basic'
} | Select-Object Name, AdapterRAM)
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
[pscustomobject]@{
    cpu = $cpu.Trim()
    ram_gb = $ram
    gpus = @($gpus | ForEach-Object {
        [pscustomobject]@{
            name = $_.Name
            adapter_ram = [int64]($_.AdapterRAM)
        }
    })
    width = [int]$screen.Width
    height = [int]$screen.Height
} | ConvertTo-Json -Compress -Depth 4
"""
    try:
        payload: dict[str, Any] = json.loads(_powershell(script))
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        hw.notes.append(f"Could not fully detect hardware: {exc}")
        hw.obs_running = obs_is_running()
        hw.obs_installed = obs_exe_present()
        try:
            hw.mics = list_capture_devices()
        except Exception:
            hw.mics = []
        return hw

    hw.cpu_name = str(payload.get("cpu") or hw.cpu_name)
    hw.ram_gb = float(payload.get("ram_gb") or 0)
    hw.display_width = int(payload.get("width") or 1920)
    hw.display_height = int(payload.get("height") or 1080)
    hw.obs_running = obs_is_running()
    hw.obs_installed = obs_exe_present()

    gpus = payload.get("gpus") or []
    if isinstance(gpus, dict):
        gpus = [gpus]

    nvidia = _nvidia_smi()
    chosen = None
    discrete = []
    for gpu in gpus:
        name = str(gpu.get("name") or "")
        if not name:
            continue
        entry = {
            "name": name,
            "vendor": _vendor_from_name(name),
            "igpu": _is_igpu(name),
            "vram_gb": max(gpu.get("adapter_ram") or 0, 0) / (1024 ** 3),
        }
        if nvidia and entry["vendor"] == "nvidia":
            entry["name"] = nvidia[0]
            entry["vram_gb"] = nvidia[1]
        if not entry["igpu"]:
            discrete.append(entry)
        if chosen is None:
            chosen = entry

    if discrete:
        chosen = max(discrete, key=lambda item: item["vram_gb"])
    if nvidia and (chosen is None or chosen["vendor"] != "nvidia"):
        chosen = {"name": nvidia[0], "vendor": "nvidia", "igpu": False, "vram_gb": nvidia[1]}

    if chosen:
        hw.gpu_name = chosen["name"]
        hw.gpu_vendor = chosen["vendor"]
        hw.vram_gb = round(float(chosen["vram_gb"] or 0), 1)
        if hw.vram_gb <= 0 and hw.gpu_vendor == "nvidia" and nvidia:
            hw.vram_gb = nvidia[1]

    if hw.gpu_vendor == "unknown":
        hw.notes.append("No dedicated GPU detected. ClipKit will use software encoding (heavier on CPU).")
    if hw.ram_gb and hw.ram_gb < 12:
        hw.notes.append("Low system RAM. The Low preset is safer.")

    try:
        hw.mics = list_capture_devices()
    except Exception:
        hw.mics = []

    save_cached_hardware(hw)
    return hw
