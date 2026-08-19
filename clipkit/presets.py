"""Low / Medium / High clipping presets, plus auto-recommend from PC specs."""

from __future__ import annotations

from dataclasses import dataclass

from .hardware import Hardware

PRESET_ORDER = ("low", "medium", "high")
CLIP_LENGTHS = (
    (30, "30 seconds"),
    (60, "1 minute"),
    (120, "2 minutes"),
    (300, "5 minutes"),
)
FPS_CHOICES = (30, 60)
RECORD_BITRATES = (
    (8000, "8 Mbps"),
    (10000, "10 Mbps"),
    (12000, "12 Mbps"),
    (14000, "14 Mbps"),
    (20000, "20 Mbps"),
    (25000, "25 Mbps"),
)
DEFAULT_BITRATE = 14000
CAPTURE_CHOICES = (
    ("window", "This game — pick the window in OBS"),
    ("any", "Any fullscreen game"),
)
MIC_CHOICES = (
    ("open", "Always on"),
    ("ptt", "Push to talk"),
    ("off", "Mic off"),
)


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    summary: str
    canvas_width: int
    canvas_height: int
    output_width: int
    output_height: int
    fps: int
    encoder_id: str
    encoder_label: str
    rate_control: str
    quality: int
    bitrate_kbps: int
    replay_seconds: int
    replay_memory_mb: int
    encoder_settings: dict


def _fit(width: int, height: int, max_w: int, max_h: int) -> tuple[int, int]:
    if width <= max_w and height <= max_h:
        return _even(width), _even(height)
    scale = min(max_w / width, max_h / height)
    return _even(int(width * scale)), _even(int(height * scale))


def _even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def _encoder_for(hw: Hardware) -> tuple[str, str]:
    if hw.gpu_vendor == "nvidia":
        return "obs_nvenc_h264_tex", "NVIDIA NVENC H.264"
    if hw.gpu_vendor == "amd":
        return "h264_texture_amf", "AMD HW H.264"
    if hw.gpu_vendor == "intel":
        return "obs_qsv11_v2", "Intel Quick Sync H.264"
    return "obs_x264", "x264 (CPU)"


def _cbr_settings(encoder_id: str, bitrate_kbps: int) -> dict:
    if encoder_id == "obs_nvenc_h264_tex":
        return {
            "rate_control": "CBR",
            "bitrate": bitrate_kbps,
            "keyint_sec": 2,
            "preset": "p5",
            "tune": "hq",
            "profile": "high",
            "lookahead": False,
            "psycho_aq": True,
            "bf": 2,
        }
    if encoder_id == "h264_texture_amf":
        return {
            "rate_control": "cbr",
            "bitrate": bitrate_kbps,
            "preset": "quality",
            "profile": "high",
            "keyint_sec": 2,
        }
    if encoder_id == "obs_qsv11_v2":
        return {
            "rate_control": "CBR",
            "bitrate": bitrate_kbps,
            "target_usage": "TU4",
            "profile": "high",
            "keyint_sec": 2,
        }
    return {
        "rate_control": "CBR",
        "bitrate": bitrate_kbps,
        "preset": "veryfast",
        "profile": "high",
        "keyint_sec": 2,
    }


def _replay_buffer_mb(bitrate_kbps: int, seconds: int, encoder_id: str) -> int:
    # bitrate kbps × seconds / 8 / 1024, plus headroom so the buffer holds the full clip.
    megabytes = int(bitrate_kbps * seconds / 8192 * 1.3)
    megabytes = max(512, megabytes)
    cap = 2048 if encoder_id == "obs_x264" else 8192
    return min(megabytes, cap)


def recommend_id(hw: Hardware) -> str:
    encoder_id, _ = _encoder_for(hw)
    vram = hw.vram_gb
    ram = hw.ram_gb
    pixels = hw.display_width * hw.display_height

    if encoder_id == "obs_x264" or ram and ram < 12:
        return "low"
    if hw.gpu_vendor == "intel" and "arc" not in hw.gpu_name.lower():
        return "low"
    if vram and vram < 4:
        return "low"
    if encoder_id == "obs_x264":
        return "low"
    if ram and ram < 16:
        return "medium"
    if vram and vram < 6:
        return "medium"
    if pixels >= 2560 * 1440 and vram >= 8:
        return "high"
    if vram >= 8:
        return "high"
    return "medium"


def build_preset(
    hw: Hardware,
    preset_id: str,
    *,
    replay_seconds: int = 300,
    fps: int = 60,
    bitrate_kbps: int = DEFAULT_BITRATE,
) -> Preset:
    preset_id = preset_id.lower()
    if preset_id not in PRESET_ORDER:
        raise ValueError(f"Unknown preset: {preset_id}")
    if replay_seconds not in {seconds for seconds, _label in CLIP_LENGTHS}:
        raise ValueError(f"Unknown clip length: {replay_seconds}")
    if fps not in FPS_CHOICES:
        raise ValueError(f"Unknown fps: {fps}")
    allowed = {kbps for kbps, _label in RECORD_BITRATES}
    if bitrate_kbps not in allowed:
        bitrate_kbps = DEFAULT_BITRATE

    encoder_id, encoder_label = _encoder_for(hw)
    canvas_w, canvas_h = _even(hw.display_width), _even(hw.display_height)

    if preset_id == "low":
        out_w, out_h = _fit(canvas_w, canvas_h, 1920, 1080)
        quality = 23
        summary = "Smaller files. Best on laptops or older PCs."
        label = "Low"
    elif preset_id == "medium":
        out_w, out_h = _fit(canvas_w, canvas_h, 2560, 1440)
        quality = 20
        summary = "Good quality. The usual pick for most PCs."
        label = "Medium"
    else:
        out_w, out_h = canvas_w, canvas_h
        quality = 18
        summary = "Highest quality. Needs a decent GPU."
        label = "High"

    replay_memory_mb = _replay_buffer_mb(bitrate_kbps, replay_seconds, encoder_id)
    encoder_settings = _cbr_settings(encoder_id, bitrate_kbps)
    return Preset(
        id=preset_id,
        label=label,
        summary=summary,
        canvas_width=canvas_w,
        canvas_height=canvas_h,
        output_width=out_w,
        output_height=out_h,
        fps=fps,
        encoder_id=encoder_id,
        encoder_label=encoder_label,
        rate_control="CBR",
        quality=quality,
        bitrate_kbps=bitrate_kbps,
        replay_seconds=replay_seconds,
        replay_memory_mb=replay_memory_mb,
        encoder_settings=encoder_settings,
    )


def all_presets(
    hw: Hardware,
    *,
    replay_seconds: int = 300,
    fps: int = 60,
    bitrate_kbps: int = DEFAULT_BITRATE,
) -> dict[str, Preset]:
    return {
        pid: build_preset(
            hw, pid, replay_seconds=replay_seconds, fps=fps, bitrate_kbps=bitrate_kbps
        )
        for pid in PRESET_ORDER
    }
