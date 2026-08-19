"""Write a ClipKit OBS profile, scene, scripts, and hotkeys."""

from __future__ import annotations

import json
import shutil
import uuid
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

from .install_obs import find_obs_exe
from .keys import DEFAULT_BINDS, Hotkey, UserBinds
from .notifications import register_toast_app
from .paths import scripts_dir as repo_scripts_dir
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
RecFormat2=hybrid_mp4
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
RecFormat2=hybrid_mp4
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


def _capture_source(kind: str, source_uuid: str, binds: UserBinds) -> dict:
    # Game only. "hotkey" hooks whichever game is in front when they press the key,
    # so switching FiveM / Fortnite / etc. does not mean opening OBS properties.
    if kind == "any":
        capture_mode = "any"
        start_binds: list[dict] = []
    else:
        capture_mode = "hotkey"
        start_binds = [binds.hook_game.binding()]
    return {
        "prev_ver": 537001985,
        "name": "Game Capture",
        "uuid": source_uuid,
        "id": "game_capture",
        "versioned_id": "game_capture",
        "settings": {
            "capture_mode": capture_mode,
            "capture_audio": True,
            "priority": 1,
        },
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
            "hotkey_start": start_binds,
            "hotkey_stop": [],
        },
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {},
    }


def _scene_collection(
    preset: Preset,
    script_paths: list[Path],
    binds: UserBinds,
    capture: str = "hotkey",
    *,
    show_notifications: bool = True,
    show_popup: bool = True,
) -> dict:
    game_uuid = _new_uuid()
    scene_uuid = _new_uuid()
    desktop_uuid = _new_uuid()
    mic_uuid = _new_uuid()
    capture_name = "Game Capture"
    scripts = []
    for path in script_paths:
        posix = path.as_posix()
        if path.name == "obs_game_clip_sorter.lua":
            settings = {
                "refresh_hotkey": [],
                "debug_enabled": False,
                "show_notifications": show_notifications,
                "show_popup": show_popup,
            }
        else:
            settings = {}
        scripts.append({"path": posix, "settings": settings})

    def audio_source(
        name: str,
        source_uuid: str,
        source_id: str,
        *,
        push_to_talk: bool = False,
        ptt_hotkeys: list[Hotkey] | None = None,
        muted: bool = False,
        mixers: int = 0,
        filters: list[dict] | None = None,
        device_id: str = "default",
        enabled: bool = True,
    ) -> dict:
        ptt_binds = [key.binding() for key in (ptt_hotkeys or [])] if push_to_talk else []
        data = {
            "prev_ver": 537001985,
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
            "push-to-talk": push_to_talk,
            "push-to-talk-delay": 0,
            "hotkeys": {
                "libobs.mute": [],
                "libobs.unmute": [],
                "libobs.push-to-mute": [],
                "libobs.push-to-talk": ptt_binds,
            },
            "deinterlace_mode": 0,
            "deinterlace_field_order": 0,
            "monitoring_type": 0,
            "private_settings": {},
        }
        if filters:
            data["filters"] = filters
        return data

    mic_on = binds.mic_mode != "off"
    mic_filters = []
    if mic_on:
        mic_filters.append(
            {
                "prev_ver": 537001985,
                "name": "Noise Suppression",
                "uuid": _new_uuid(),
                "id": "noise_suppress_filter_v2",
                "versioned_id": "noise_suppress_filter_v2",
                "settings": {"method": "rnnoise"},
                "enabled": True,
            }
        )

    return {
        "name": SCENE_NAME,
        "DesktopAudioDevice1": audio_source(
            "Desktop Audio",
            desktop_uuid,
            "wasapi_output_capture",
            muted=True,
            mixers=0,
            device_id="disabled",
            enabled=False,
        ),
        "DesktopAudioDevice2": audio_source(
            "Desktop Audio 2",
            _new_uuid(),
            "wasapi_output_capture",
            muted=True,
            mixers=0,
            device_id="disabled",
            enabled=False,
        ),
        "AuxAudioDevice1": audio_source(
            "Mic",
            mic_uuid,
            "wasapi_input_capture",
            push_to_talk=binds.ptt_enabled,
            ptt_hotkeys=binds.ptt_keys() if binds.ptt_enabled else None,
            muted=not mic_on,
            mixers=TRACK_MIC if mic_on else 0,
            filters=mic_filters,
        ),
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
            "scripts-tool": scripts,
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
            _capture_source(capture, game_uuid, binds),
            {
                "prev_ver": 537001985,
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
                "canvas_uuid": "6c69626f-6273-4c00-9d88-c5136d61696e",
                "private_settings": {},
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
SysTrayEnabled=true
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
    parser.set("BasicWindow", "SysTrayEnabled", "true")
    parser.set("BasicWindow", "SysTrayMinimizeToTray", "false")
    parser.set("BasicWindow", "SysTrayWhenStarted", "false")
    with user_ini.open("w", encoding="utf-8", newline="\r\n") as handle:
        parser.write(handle, space_around_delimiters=False)


def apply_setup(
    preset: Preset,
    output_dir: Path,
    *,
    install_sorter: bool = True,
    install_autostart: bool = True,
    make_default: bool = True,
    config_dir: Path | None = None,
    binds: UserBinds | None = None,
    capture: str = "hotkey",
    enable_recording: bool = True,
    show_notifications: bool = True,
    show_popup: bool = True,
    start_with_windows: bool = False,
) -> dict:
    binds = binds or DEFAULT_BINDS
    if start_with_windows:
        install_autostart = True
    config_dir = Path(config_dir) if config_dir else obs_config_dir()
    _bootstrap_config(config_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = config_dir / "clipkit-backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    user_ini = config_dir / "user.ini"
    if user_ini.exists():
        shutil.copy2(user_ini, backup_dir / "user.ini")

    installed_scripts_dir = config_dir / "clipkit-scripts"
    installed_scripts_dir.mkdir(parents=True, exist_ok=True)
    source_scripts = repo_scripts_dir()
    script_paths: list[Path] = []
    copied = []

    if install_sorter:
        dest = installed_scripts_dir / "obs_game_clip_sorter.lua"
        shutil.copy2(source_scripts / "obs_game_clip_sorter.lua", dest)
        script_paths.append(dest)
        copied.append(str(dest))
        shutil.copy2(source_scripts / "clipkit_toast.ps1", installed_scripts_dir / "clipkit_toast.ps1")
    if install_autostart:
        dest = installed_scripts_dir / "clipkit_autostart.lua"
        shutil.copy2(source_scripts / "clipkit_autostart.lua", dest)
        script_paths.append(dest)
        copied.append(str(dest))

    profile_dir = config_dir / "basic" / "profiles" / PROFILE_NAME
    profile_dir.mkdir(parents=True, exist_ok=True)
    _write_ini(
        profile_dir / "basic.ini",
        _profile_ini(
            preset,
            output_dir,
            binds,
            enable_recording=enable_recording,
            record_mic_track=binds.mic_mode != "off",
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
    scene_path.write_text(
        json.dumps(
            _scene_collection(
                preset,
                script_paths,
                binds,
                capture,
                show_notifications=show_notifications,
                show_popup=show_popup,
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

    if show_notifications:
        register_toast_app()

    mic_label = {"open": "always on", "ptt": "off", "off": "muted"}.get(binds.mic_mode, binds.mic_mode)
    if binds.ptt_enabled:
        labels = ", ".join(key.label for key in binds.ptt_keys())
        mic_label = f"push to talk ({labels})"

    return {
        "profile": PROFILE_NAME,
        "scene": SCENE_NAME,
        "output_dir": str(output_dir),
        "scripts": copied,
        "backup_dir": str(backup_dir),
        "save_hotkey": binds.save.label,
        "clip_toggle": binds.replay_toggle.label,
        "record_toggle": binds.record_toggle.label if enable_recording else "off",
        "start_hotkey": binds.replay_toggle.label,
        "ptt": mic_label,
        "mic": mic_label,
        "capture": (
            f"This game (press {binds.hook_game.label} to switch)"
            if capture != "any"
            else "Any fullscreen game"
        ),
        "clip_seconds": preset.replay_seconds,
        "fps": preset.fps,
        "quality": preset.label,
        "bitrate_kbps": preset.bitrate_kbps,
        "notifications": show_notifications,
        "popup": show_popup,
        "recording": enable_recording,
        "audio": (
            "game track 1, mic track 2"
            if binds.mic_mode != "off"
            else "game track 1 (mic off)"
        ),
        "windows_startup": bool(startup_path),
        "windows_startup_path": str(startup_path) if startup_path else "",
    }
