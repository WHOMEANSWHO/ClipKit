"""Write a ClipKit OBS profile, scene, and hotkeys."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

from .audio import list_capture_devices, resolve_microphone
from .install_obs import find_obs_exe
from .keys import DEFAULT_BINDS, UserBinds
from .paths import scripts_dir
from .presets import Preset
from .startup import install_obs_windows_startup, remove_obs_windows_startup

PROFILE_NAME = "ClipKit"
SCENE_NAME = "ClipKit"
# OBS mixers / RecTracks are bitmasks: bit 0 = track 1, bit 1 = track 2.
TRACK_GAME = 1
TRACK_MIC = 2
REC_TRACKS_GAME_AND_MIC = TRACK_GAME | TRACK_MIC


def default_output_dir() -> Path:
    videos = Path.home() / "Videos" / "ClipKit"
    existing = Path("D:/vids/obs")
    if existing.is_dir():
        return existing
    return videos


def obs_config_dir() -> Path:
    return Path.home() / "AppData" / "Roaming" / "obs-studio"


def obs_is_configured() -> bool:
    return (obs_config_dir() / "global.ini").exists() or (obs_config_dir() / "user.ini").exists()


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _write_ini(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\n", "\r\n"), encoding="utf-8")


def _write_profile(path: Path, text: str) -> None:
    """Update the existing ClipKit profile in place instead of replacing it."""
    incoming = _ini_parser()
    incoming.read_string(text.replace("\r\n", "\n"))
    parser = _ini_parser()
    if path.is_file():
        _read_ini(parser, path)
    for section in incoming.sections():
        if not parser.has_section(section):
            parser.add_section(section)
        for key, value in incoming.items(section):
            parser.set(section, key, value)
    if not parser.has_section("General"):
        parser.add_section("General")
    parser.set("General", "Name", PROFILE_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\r\n") as handle:
        parser.write(handle, space_around_delimiters=False)


def _ini_parser() -> ConfigParser:
    parser = ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    parser.optionxform = str
    return parser


def _collapse_ini_duplicates(text: str) -> str:
    """OBS may write the same key twice. Keep the last value in each section."""
    sections: list[tuple[str, dict[str, str]]] = []
    current = ""
    values: dict[str, str] = {}

    def flush() -> None:
        if current or values:
            sections.append((current, dict(values)))

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            flush()
            current = line[1:-1].strip()
            values = {}
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    flush()

    chunks: list[str] = []
    for name, items in sections:
        if name:
            chunks.append(f"[{name}]")
        for key, value in items.items():
            chunks.append(f"{key}={value}")
        chunks.append("")
    return "\n".join(chunks).strip() + "\n"


def _read_ini(parser: ConfigParser, path: Path) -> None:
    # OBS often writes a UTF-8 BOM, and sometimes the same key twice.
    text = path.read_text(encoding="utf-8-sig").lstrip("\ufeff")
    if not text.strip():
        return
    try:
        parser.read_string(text)
    except Exception:
        parser.read_string(_collapse_ini_duplicates(text))


def _profile_ini(
    preset: Preset,
    output_dir: Path,
    binds: UserBinds,
    *,
    enable_recording: bool = True,
    record_mic_track: bool = True,
) -> str:
    rec_path = str(output_dir).replace("/", "\\")
    save_ini = binds.save.replay_save_ini()
    replay_ini = binds.replay_toggle.frontend_ini()
    record_ini = binds.record_toggle.frontend_ini()
    rec_tracks = REC_TRACKS_GAME_AND_MIC if record_mic_track else TRACK_GAME
    recording_keys = ""
    if enable_recording:
        recording_keys = f"""OBSBasic.StartRecording={record_ini}
OBSBasic.StopRecording={record_ini}
"""
    return f"""[General]
Name={PROFILE_NAME}

[Output]
Mode=Advanced
FilenameFormatting=%CCYY-%MM-%DD %hh-%mm-%ss
DelayEnable=false
DelaySec=20
DelayPreserve=true
Reconnect=true
RetryDelay=2
MaxRetries=25
BindIP=default
IPFamily=IPv4+IPv6
NewSocketLoopEnable=false
LowLatencyEnable=false

[Stream1]
IgnoreRecommended=false
EnableMultitrackVideo=false
MultitrackVideoMaximumAggregateBitrateAuto=true
MultitrackVideoMaximumVideoTracksAuto=true

[SimpleOutput]
FilePath={rec_path}
RecFormat2=mp4
VBitrate={preset.bitrate_kbps}
ABitrate=160
UseAdvanced=false
Preset=veryfast
NVENCPreset2=p5
RecQuality=Small
RecRB=true
RecRBTime={preset.replay_seconds}
RecRBSize={preset.replay_memory_mb}
RecRBPrefix=Replay
StreamAudioEncoder=aac
RecAudioEncoder=aac
RecTracks={rec_tracks}
StreamEncoder=nvenc
RecEncoder=nvenc

[AdvOut]
ApplyServiceSettings=true
UseRescale=false
TrackIndex=1
VodTrackIndex=2
Encoder=obs_x264
RecType=Standard
RecFilePath={rec_path}
RecFormat2=mp4
RecUseRescale=false
RecTracks={rec_tracks}
RecEncoder={preset.encoder_id}
Track1Name=Game
Track2Name=Mic
FLVTrack=1
StreamMultiTrackAudioMixes=1
FFOutputToFile=true
FFFilePath={rec_path}
FFVBitrate=6000
FFVGOPSize=250
FFUseRescale=false
FFIgnoreCompat=false
FFABitrate=160
FFAudioMixes=1
Track1Bitrate=160
Track2Bitrate=160
Track3Bitrate=160
Track4Bitrate=160
Track5Bitrate=160
Track6Bitrate=160
RecSplitFileTime=15
RecSplitFileSize=2048
RecRB=true
RecRBTime={preset.replay_seconds}
RecRBSize={preset.replay_memory_mb}
AudioEncoder=ffmpeg_aac
RecAudioEncoder=ffmpeg_aac
RecSplitFileType=Time
FFFormat=
FFFormatMimeType=
FFVEncoderId=0
FFVEncoder=
FFAEncoderId=0
FFAEncoder=
FFExtension=mp4

[Video]
BaseCX={preset.canvas_width}
BaseCY={preset.canvas_height}
OutputCX={preset.output_width}
OutputCY={preset.output_height}
FPSType=0
FPSCommon={preset.fps}
FPSInt={preset.fps}
FPSNum={preset.fps}
FPSDen=1
ScaleType=bicubic
ColorFormat=NV12
ColorSpace=709
ColorRange=Partial
SdrWhiteLevel=300
HdrNominalPeakLevel=1000

[Audio]
MonitoringDeviceId=default
MonitoringDeviceName=Default
SampleRate=48000
ChannelSetup=Stereo
MeterDecayRate=23.53
PeakMeterType=0

[Hotkeys]
{recording_keys}OBSBasic.StartReplayBuffer={replay_ini}
OBSBasic.StopReplayBuffer={replay_ini}
ReplayBuffer={save_ini}
"""


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _named_source(existing: dict | None, name: str) -> dict | None:
    if not existing:
        return None
    for source in existing.get("sources") or []:
        if isinstance(source, dict) and source.get("name") == name:
            return source
    return None


def _keep_uuid(existing: dict | None) -> str:
    value = str((existing or {}).get("uuid") or "").strip()
    return value or _new_uuid()


def _keep_prev_ver(existing: dict | None) -> int:
    try:
        return int((existing or {}).get("prev_ver") or 537001985)
    except (TypeError, ValueError):
        return 537001985


def _capture_source(
    kind: str,
    source_uuid: str,
    existing: dict | None = None,
) -> dict:
    # "any" grabs whichever fullscreen game is in front.
    # "This game" uses a normal OBS Game Capture window list. People pick
    # FiveM / Fortnite / etc. in OBS themselves.
    existing_settings = existing.get("settings") if isinstance(existing, dict) else None
    if not isinstance(existing_settings, dict):
        existing_settings = {}
    settings: dict = {
        "capture_audio": True,
        "priority": 2,
    }
    if kind == "any":
        settings["capture_mode"] = "any"
    else:
        settings["capture_mode"] = "window"
        if existing_settings.get("window"):
            settings["window"] = existing_settings["window"]
            if existing_settings.get("priority") is not None:
                settings["priority"] = existing_settings["priority"]
    return {
        "prev_ver": _keep_prev_ver(existing),
        "name": "Game Capture",
        "uuid": source_uuid,
        "id": "game_capture",
        "versioned_id": "game_capture",
        "settings": settings,
        "mixers": TRACK_GAME,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {
            "libobs.mute": [],
            "libobs.unmute": [],
            "libobs.push-to-mute": [],
            "libobs.push-to-talk": [],
            "hotkey_start": [],
            "hotkey_stop": [],
        },
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
        "filters": [],
    }


def _stock_audio(
    name: str,
    source_uuid: str,
    source_id: str,
    *,
    mixers: int = 0,
    device_id: str = "default",
    muted: bool = False,
    enabled: bool = True,
    existing: dict | None = None,
) -> dict:
    return {
        "prev_ver": _keep_prev_ver(existing),
        "name": name,
        "uuid": source_uuid,
        "id": source_id,
        "versioned_id": source_id,
        "settings": {"device_id": device_id},
        "mixers": mixers,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": enabled,
        "muted": muted,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {
            "libobs.mute": [],
            "libobs.unmute": [],
            "libobs.push-to-mute": [],
            "libobs.push-to-talk": [],
        },
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
        "filters": [],
    }


def _existing_mic_device_id(existing_mic: dict) -> str:
    settings = existing_mic.get("settings")
    if not isinstance(settings, dict):
        return ""
    return str(settings.get("device_id") or "").strip()


def _chosen_microphone(existing_mic: dict, preferred_id: str = "") -> tuple[str, str]:
    device = resolve_microphone(
        list_capture_devices(),
        preferred_id=preferred_id,
        existing_id=_existing_mic_device_id(existing_mic),
    )
    if device is None:
        return "default", "Windows default"
    return device.device_id, device.short_name


def _remove_helper_scripts(config_dir: Path) -> None:
    folder = config_dir / "clipkit-scripts"
    for name in (
        "clipkit_autostart.lua",
        "clipkit_toast.ps1",
        "last-game.json",
        "ptt.json",
    ):
        path = folder / name
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue
    for name in ("clipkit-command.txt", "clipkit-status.txt", "clipkit-save-result.txt"):
        path = config_dir / name
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _install_clip_sorter(config_dir: Path) -> Path:
    dest_dir = config_dir / "clipkit-scripts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "obs_game_clip_sorter.lua"
    source = scripts_dir() / "obs_game_clip_sorter.lua"
    if not source.is_file():
        raise FileNotFoundError(f"Clip sorter script is missing: {source}")
    shutil.copy2(source, dest)
    return dest


def _scene_collection(
    preset: Preset,
    capture: str = "window",
    existing: dict | None = None,
    mic_device_id: str = "default",
    sorter_path: Path | None = None,
) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    existing_mic = existing.get("AuxAudioDevice1") if isinstance(existing.get("AuxAudioDevice1"), dict) else {}
    existing_game = _named_source(existing, "Game Capture")
    existing_scene = _named_source(existing, "Game")
    game_uuid = _keep_uuid(existing_game)
    scene_uuid = _keep_uuid(existing_scene)
    mic_uuid = _keep_uuid(existing_mic)
    capture_name = "Game Capture"
    existing_desktop = existing.get("DesktopAudioDevice1") if isinstance(existing.get("DesktopAudioDevice1"), dict) else {}

    mic_source = _stock_audio(
        "Mic",
        mic_uuid,
        "wasapi_input_capture",
        mixers=TRACK_MIC,
        device_id=mic_device_id,
        muted=False,
        enabled=True,
        existing=existing_mic,
    )

    desktop_source = _stock_audio(
        "Desktop Audio",
        _keep_uuid(existing_desktop),
        "wasapi_output_capture",
        mixers=0,
        muted=True,
        enabled=False,
        existing=existing_desktop,
    )

    scripts_tool: list[dict] = []
    if sorter_path is not None:
        scripts_tool.append(
            {
                "path": Path(sorter_path).resolve().as_posix(),
                "settings": {
                    "refresh_hotkey": [],
                    "debug_enabled": False,
                },
            }
        )

    return {
        "name": SCENE_NAME,
        "DesktopAudioDevice1": desktop_source,
        "AuxAudioDevice1": mic_source,
        "current_scene": "Game",
        "current_program_scene": "Game",
        "scene_order": [{"name": "Game"}],
        "groups": [],
        "canvases": [],
        "current_transition": "Fade",
        "transition_duration": 300,
        "transitions": [],
        "quick_transitions": [],
        "saved_projectors": [],
        "preview_locked": False,
        "scaling_enabled": False,
        "scaling_level": 0,
        "scaling_off_x": 0.0,
        "scaling_off_y": 0.0,
        "virtual-camera": {"type2": 3},
        "modules": {
            "scripts-tool": scripts_tool,
            "output-timer": {
                "streamTimerHours": 0,
                "streamTimerMinutes": 0,
                "streamTimerSeconds": 30,
                "recordTimerHours": 0,
                "recordTimerMinutes": 0,
                "recordTimerSeconds": 30,
                "autoStartStreamTimer": False,
                "autoStartRecordTimer": False,
                "pauseRecordTimer": True,
            },
        },
        "resolution": {"x": preset.canvas_width, "y": preset.canvas_height},
        "version": 2,
        "sources": [
            _capture_source(capture, game_uuid, existing_game),
            {
                "prev_ver": _keep_prev_ver(existing_scene),
                "name": "Game",
                "uuid": scene_uuid,
                "id": "scene",
                "versioned_id": "scene",
                "settings": {
                    "id_counter": 1,
                    "custom_size": False,
                    "items": [
                        {
                            "name": capture_name,
                            "source_uuid": game_uuid,
                            "visible": True,
                            "locked": False,
                            "rot": 0.0,
                            "scale_ref": {
                                "x": float(preset.canvas_width),
                                "y": float(preset.canvas_height),
                            },
                            "align": 5,
                            "bounds_type": 0,
                            "bounds_align": 0,
                            "bounds_crop": False,
                            "crop_left": 0,
                            "crop_top": 0,
                            "crop_right": 0,
                            "crop_bottom": 0,
                            "id": 1,
                            "group_item_backup": False,
                            "pos": {"x": 0.0, "y": 0.0},
                            "scale": {"x": 1.0, "y": 1.0},
                            "bounds": {"x": 0.0, "y": 0.0},
                            "scale_filter": "disable",
                            "blend_method": "default",
                            "blend_type": "normal",
                            "show_transition": {"duration": 300},
                            "hide_transition": {"duration": 300},
                            "private_settings": {},
                        }
                    ],
                },
                "mixers": 0,
                "sync": 0,
                "flags": 0,
                "volume": 1.0,
                "balance": 0.5,
                "enabled": True,
                "muted": False,
                "push-to-mute": False,
                "push-to-mute-delay": 0,
                "push-to-talk": False,
                "push-to-talk-delay": 0,
                "hotkeys": {
                    "OBSBasic.SelectScene": [],
                    "libobs.show_scene_item.1": [],
                    "libobs.hide_scene_item.1": [],
                },
                "deinterlace_mode": 0,
                "deinterlace_field_order": 0,
                "monitoring_type": 0,
                "canvas_uuid": str((existing_scene or {}).get("canvas_uuid") or "6c69626f-6273-4c00-9d88-c5136d61696e"),
                "private_settings": {},
                "filters": [],
            },
        ],
    }


def _bootstrap_config(config_dir: Path) -> None:
    """Create enough OBS config that first launch skips the empty wizard."""
    config_dir.mkdir(parents=True, exist_ok=True)
    global_ini = config_dir / "global.ini"
    if not global_ini.exists():
        _write_ini(
            global_ini,
            """[General]
MaxLogs=10
InfoIncrement=-1
ProcessPriority=Normal
EnableAutoUpdates=true
BrowserHWAccel=true

[Video]
Renderer=Direct3D 11

[Audio]
DisableAudioDucking=true
""",
        )
    user_ini = config_dir / "user.ini"
    if not user_ini.exists():
        _write_ini(
            user_ini,
            """[General]
Pre19Defaults=false
Pre21Defaults=false
Pre23Defaults=false
Pre24.1Defaults=false
ConfirmOnExit=true
HotkeyFocusType=NeverDisableHotkeys
FirstRun=false

[BasicWindow]
PreviewEnabled=true
SysTrayEnabled=false
SysTrayWhenStarted=false
SysTrayMinimizeToTray=false

[Basic]
Profile=ClipKit
ProfileDir=ClipKit
SceneCollection=ClipKit
SceneCollectionFile=ClipKit.json
""",
        )


def _set_current_profile(parser: ConfigParser) -> None:
    if not parser.has_section("Basic"):
        parser.add_section("Basic")
    parser.set("Basic", "Profile", PROFILE_NAME)
    parser.set("Basic", "ProfileDir", PROFILE_NAME)
    parser.set("Basic", "SceneCollection", SCENE_NAME)
    parser.set("Basic", "SceneCollectionFile", f"{SCENE_NAME}.json")


def _upsert_ini_key(text: str, section: str, key: str, value: str) -> str:
    section_re = re.compile(rf"^\[{re.escape(section)}\][ \t]*$", re.M)
    match = section_re.search(text)
    line = f"{key}={value}"
    if not match:
        stripped = text.rstrip()
        extra = f"\n[{section}]\n{line}\n"
        return (stripped + extra + ("\n" if text.endswith("\n") else "")) if stripped else f"[{section}]\n{line}\n"
    start = match.end()
    next_sec = re.search(r"^\[", text[start:], re.M)
    end = start + next_sec.start() if next_sec else len(text)
    body = text[start:end]
    key_re = re.compile(rf"(?im)^{re.escape(key)}[ \t]*=.*$", re.M)
    if key_re.search(body):
        body = key_re.sub(line, body, count=1)
    else:
        body = "\n" + line + body
        if not body.endswith("\n"):
            body += "\n"
    return text[:start] + body + text[end:]


def _update_user_ini(config_dir: Path) -> None:
    user_ini = config_dir / "user.ini"
    parser = _ini_parser()
    if user_ini.exists():
        _read_ini(parser, user_ini)
    _set_current_profile(parser)
    if not parser.has_section("General"):
        parser.add_section("General")
    parser.set("General", "HotkeyFocusType", "NeverDisableHotkeys")
    parser.set("General", "FirstRun", "false")
    if not parser.has_section("BasicWindow"):
        parser.add_section("BasicWindow")
    parser.set("BasicWindow", "SysTrayEnabled", "false")
    parser.set("BasicWindow", "SysTrayMinimizeToTray", "false")
    parser.set("BasicWindow", "SysTrayWhenStarted", "false")
    parser.set("BasicWindow", "PreviewEnabled", "true")
    parser.set("BasicWindow", "MixerShowInactive", "true")
    parser.set("BasicWindow", "MixerShowHidden", "false")
    with user_ini.open("w", encoding="utf-8", newline="\r\n") as handle:
        parser.write(handle, space_around_delimiters=False)
    # OBS first-run can ignore ConfigParser writes. Force the tray keys in the raw file too.
    try:
        text = user_ini.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    except OSError:
        return
    for section, key, value in (
        ("General", "HotkeyFocusType", "NeverDisableHotkeys"),
        ("General", "FirstRun", "false"),
        ("BasicWindow", "SysTrayEnabled", "false"),
        ("BasicWindow", "SysTrayWhenStarted", "false"),
        ("BasicWindow", "SysTrayMinimizeToTray", "false"),
        ("BasicWindow", "PreviewEnabled", "true"),
        ("BasicWindow", "MixerShowInactive", "true"),
        ("BasicWindow", "MixerShowHidden", "false"),
    ):
        text = _upsert_ini_key(text, section, key, value)
    user_ini.write_text(text.replace("\n", "\r\n"), encoding="utf-8")


def apply_setup(
    preset: Preset,
    output_dir: Path,
    *,
    make_default: bool = True,
    config_dir: Path | None = None,
    binds: UserBinds | None = None,
    capture: str = "window",
    enable_recording: bool = True,
    start_with_windows: bool = False,
) -> dict:
    binds = binds or DEFAULT_BINDS
    capture = "any" if capture == "any" else "window"
    config_dir = Path(config_dir) if config_dir else obs_config_dir()
    _bootstrap_config(config_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = config_dir / "clipkit-backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    user_ini = config_dir / "user.ini"
    if user_ini.exists():
        shutil.copy2(user_ini, backup_dir / "user.ini")

    _remove_helper_scripts(config_dir)
    sorter_path = _install_clip_sorter(config_dir)

    profile_dir = config_dir / "basic" / "profiles" / PROFILE_NAME
    profile_dir.mkdir(parents=True, exist_ok=True)
    _write_profile(
        profile_dir / "basic.ini",
        _profile_ini(
            preset,
            output_dir,
            binds,
            enable_recording=enable_recording,
            record_mic_track=True,
        ),
    )
    (profile_dir / "recordEncoder.json").write_text(
        json.dumps(preset.encoder_settings, indent=2),
        encoding="utf-8",
    )
    (profile_dir / "streamEncoder.json").write_text("{}", encoding="utf-8")

    scenes_dir = config_dir / "basic" / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    scene_path = scenes_dir / f"{SCENE_NAME}.json"
    existing_scene = _load_json(scene_path)
    existing_mic = {}
    if isinstance(existing_scene, dict):
        maybe_mic = existing_scene.get("AuxAudioDevice1")
        if isinstance(maybe_mic, dict):
            existing_mic = maybe_mic
    mic_device_id, mic_name = _chosen_microphone(existing_mic, binds.mic_device_id)
    scene_path.write_text(
        json.dumps(
            _scene_collection(
                preset,
                capture,
                existing=existing_scene,
                mic_device_id=mic_device_id,
                sorter_path=sorter_path,
            ),
            indent=4,
        ),
        encoding="utf-8",
    )

    _update_user_ini(config_dir)

    startup_path = None
    if start_with_windows:
        startup_path = install_obs_windows_startup(find_obs_exe())
    else:
        remove_obs_windows_startup()

    return {
        "profile": PROFILE_NAME,
        "scene": SCENE_NAME,
        "output_dir": str(output_dir),
        "backup_dir": str(backup_dir),
        "save_hotkey": binds.save.label,
        "clip_toggle": binds.replay_toggle.label,
        "record_toggle": binds.record_toggle.label if enable_recording else "off",
        "start_hotkey": binds.replay_toggle.label,
        "mic": mic_name,
        "mic_device_id": mic_device_id,
        "capture": (
            "This game (pick the window in OBS Game Capture)"
            if capture != "any"
            else "Any fullscreen game"
        ),
        "clip_seconds": preset.replay_seconds,
        "fps": preset.fps,
        "quality": preset.label,
        "bitrate_kbps": preset.bitrate_kbps,
        "recording": enable_recording,
        "audio": "game track 1, mic track 2",
        "windows_startup": bool(startup_path),
        "windows_startup_path": str(startup_path) if startup_path else "",
    }
