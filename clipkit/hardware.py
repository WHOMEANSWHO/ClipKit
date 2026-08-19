"""Detect GPU, CPU, RAM, display, and whether OBS is installed/running."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .install_obs import find_obs_exe


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

    @property
    def display_label(self) -> str:
        return f"{self.display_width}x{self.display_height}"


def _powershell(script: str) -> str:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=30,
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
            timeout=10,
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
} | Select-Object Name, AdapterRAM, PNPDeviceID)
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$obsProc = @(Get-Process -Name obs64,obs32,obs -ErrorAction SilentlyContinue)
$config = Join-Path $env:APPDATA 'obs-studio'
[pscustomobject]@{
    cpu = $cpu.Trim()
    ram_gb = $ram
    gpus = @($gpus | ForEach-Object {
        [pscustomobject]@{
            name = $_.Name
            adapter_ram = [int64]($_.AdapterRAM)
            pnp = $_.PNPDeviceID
        }
    })
    width = [int]$screen.Width
    height = [int]$screen.Height
    obs_running = ($obsProc.Count -gt 0)
    obs_config = $config
} | ConvertTo-Json -Compress -Depth 4
"""
    try:
        payload: dict[str, Any] = json.loads(_powershell(script))
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        hw.notes.append(f"Could not fully detect hardware: {exc}")
        return hw

    hw.cpu_name = str(payload.get("cpu") or hw.cpu_name)
    hw.ram_gb = float(payload.get("ram_gb") or 0)
    hw.display_width = int(payload.get("width") or 1920)
    hw.display_height = int(payload.get("height") or 1080)
    hw.obs_running = bool(payload.get("obs_running"))
    hw.obs_exe = find_obs_exe()
    hw.obs_installed = hw.obs_exe is not None
    config = payload.get("obs_config")
    if config:
        hw.obs_config_dir = Path(config)

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

    return hw


def obs_is_running() -> bool:
    hidden = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    for name in ("obs64.exe", "obs32.exe", "obs.exe"):
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=hidden,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        out = (result.stdout or "").lower()
        if name in out and "no tasks" not in out:
            return True
    return False
