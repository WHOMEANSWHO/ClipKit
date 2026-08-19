"""Pick a real WASAPI microphone so OBS is not left on Windows Default."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SKIP = (
    "chat mix",
    "voicemeeter",
    "vb-audio",
    "vb cable",
    "cable input",
    "cable output",
    "stereo mix",
    "what u hear",
    "steam streaming",
    "nvidia output",
    "discord",
    "oculus",
)


@dataclass(frozen=True)
class CaptureDevice:
    name: str
    device_id: str

    @property
    def short_name(self) -> str:
        name = self.name.strip()
        lower = name.lower()
        if lower.startswith("microphone (") and name.endswith(")"):
            name = name[12:-1]
        elif lower.startswith("mic in (") and name.endswith(")"):
            name = name[8:-1]
        if name.lower().startswith("2- "):
            name = name[3:]
        if len(name) > 36:
            return name[:33] + "…"
        return name


def obs_device_id(pnp_id: str) -> str | None:
    raw = str(pnp_id or "").strip()
    if not raw:
        return None
    marker = "MMDEVAPI\\"
    upper = raw.upper()
    index = upper.find(marker)
    if index >= 0:
        raw = raw[index + len(marker) :]
    if "{0.0.1." not in raw.lower():
        return None
    return raw


def _score(name: str) -> int:
    lower = name.lower()
    score = 10
    if any(token in lower for token in _SKIP):
        score -= 200
    if "virtual audio" in lower and "mic in" not in lower and "wave" not in lower:
        score -= 80
    if "wave:xlr" in lower or "wave xlr" in lower:
        score += 140
    if "mic in" in lower:
        score += 90
    if "xlr" in lower:
        score += 40
    if "microphone" in lower:
        score += 50
    if "headset" in lower:
        score += 15
    if any(token in lower for token in ("yeti", "rode", "shure", "hyperx", "fifine", "blue ", "steelseries", "arctis")):
        score += 25
    return score


def pick_microphone(
    devices: list[CaptureDevice],
    preferred_id: str = "",
) -> CaptureDevice | None:
    if not devices:
        return None
    wanted = preferred_id.strip().lower()
    if wanted:
        for device in devices:
            if device.device_id.lower() == wanted:
                return device
    ranked = sorted(devices, key=lambda item: _score(item.name), reverse=True)
    return ranked[0]


def list_capture_devices() -> list[CaptureDevice]:
    script = r"""
$ErrorActionPreference = 'Stop'
$mics = @(Get-CimInstance Win32_PnPEntity -Filter "PNPClass='AudioEndpoint'" | Where-Object {
    $_.Status -eq 'OK' -and $_.Name -and $_.DeviceID -like '*0.0.1.00000000*'
} | ForEach-Object {
    [pscustomobject]@{ name = $_.Name; device_id = $_.DeviceID }
})
if ($mics.Count -eq 0) { '[]' } else { $mics | ConvertTo-Json -Compress -Depth 3 }
"""
    hidden = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
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
            timeout=15,
            cwd=str(Path.home()),
            creationflags=hidden,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0 or not (completed.stdout or "").strip():
        return []
    try:
        payload = json.loads(completed.stdout.strip())
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    devices: list[CaptureDevice] = []
    seen: set[str] = set()
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        device_id = obs_device_id(str(item.get("device_id") or ""))
        if not name or not device_id or device_id.lower() in seen:
            continue
        seen.add(device_id.lower())
        devices.append(CaptureDevice(name=name, device_id=device_id))
    return devices
