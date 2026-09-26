"""Collect a troubleshooting report so 'Apply did nothing to OBS' can be diagnosed.

Run with ``ClipKit.exe --diagnose``. It writes a report to
``%APPDATA%\\ClipKit\\clipkit-diagnose.txt`` and opens it. The report shows where
OBS keeps its config, which profiles exist, which profile OBS is set to, whether
a valid ClipKit profile was written, whether OBS is in portable mode (a common
reason Apply appears to do nothing), and the tail of the ClipKit logs.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import __version__


def _obs_base_dir(obs_exe: Path | None) -> Path | None:
    # obs_exe is ...\obs-studio\bin\64bit\obs64.exe -> base is the obs-studio folder.
    if obs_exe is None:
        return None
    try:
        return Path(obs_exe).parents[2]
    except IndexError:
        return None


def _portable_markers(base: Path | None) -> list[str]:
    if base is None:
        return []
    found = []
    for name in ("obs_portable_mode", "portable_mode", "portable_mode.txt"):
        if (base / name).is_file():
            found.append(name)
    if (base / "config" / "obs-studio").is_dir():
        found.append("config/obs-studio present")
    return found


def _tail(path: Path, lines: int = 40) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(not found)"
    rows = text.splitlines()
    return "\n".join(rows[-lines:]) if rows else "(empty)"


def build_report() -> str:
    from .health import current_profile, verify_apply
    from .install_obs import find_obs_exe
    from .obs import existing_profile_dirs, obs_config_dir
    from .paths import appdata_dir

    out: list[str] = []
    add = out.append
    add(f"ClipKit {__version__} — diagnose report")
    add("=" * 48)

    try:
        from .hardware import detect

        hw = detect()
        add(f"GPU: {hw.gpu_name}  CPU: {hw.cpu_name}  RAM: {hw.ram_gb:g} GB")
        add(f"OBS installed={hw.obs_installed}  running={hw.obs_running}")
        add(f"OBS exe (quick): {hw.obs_exe}")
        for note in hw.notes:
            add(f"note: {note}")
    except Exception as exc:  # noqa: BLE001
        add(f"hardware detect failed: {exc}")

    obs_exe = None
    try:
        obs_exe = find_obs_exe(deep=True)
    except Exception as exc:  # noqa: BLE001
        add(f"find_obs_exe failed: {exc}")
    add(f"OBS exe (deep):  {obs_exe}")

    base = _obs_base_dir(obs_exe)
    markers = _portable_markers(base)
    if markers:
        add("")
        add(f"*** OBS PORTABLE MODE markers found in {base}: {markers}")
        add("    Portable OBS reads its config next to the exe, NOT %APPDATA%\\obs-studio,")
        add("    so ClipKit writing to %APPDATA% would not affect it. This is a likely cause.")

    # Config locations ClipKit might write to vs. OBS might read from.
    candidates = [("roaming (%APPDATA%)", obs_config_dir())]
    if base is not None:
        candidates.append(("portable (next to OBS)", base / "config" / "obs-studio"))

    for label, cfg in candidates:
        add("")
        add(f"[{label}] {cfg}")
        add(f"  exists: {cfg.exists()}")
        if not cfg.exists():
            continue
        try:
            add(f"  profiles: {existing_profile_dirs(cfg)}")
        except Exception as exc:  # noqa: BLE001
            add(f"  profiles: error {exc}")
        try:
            add(f"  OBS current profile (user.ini): {current_profile(cfg) or '(none)'}")
        except Exception as exc:  # noqa: BLE001
            add(f"  current profile: error {exc}")
        try:
            checks = verify_apply(cfg)
            add(f"  ClipKit profile valid here: {checks}")
        except Exception as exc:  # noqa: BLE001
            add(f"  verify_apply error: {exc}")

    add("")
    add("--- clipkit.log (last 40 lines) ---")
    add(_tail(appdata_dir() / "ClipKit" / "clipkit.log"))
    add("")
    add("--- clip-saved.log (last 20 lines) ---")
    add(_tail(appdata_dir() / "obs-studio" / "clipkit-scripts" / "clip-saved.log", 20))
    add("")
    add("--- game clip sorter log (last 20 lines) ---")
    add(_tail(appdata_dir() / "obs-studio" / "clipkit-scripts" / "obs_game_clip_sorter.log", 20))

    return "\n".join(out) + "\n"


def run_diagnose() -> int:
    from .paths import appdata_dir

    report = build_report()
    report_path = appdata_dir() / "ClipKit" / "clipkit-diagnose.txt"
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    except OSError:
        report_path = None

    print(report)
    if report_path is not None:
        print(f"\nSaved report to: {report_path}")
        try:
            os.startfile(os.fsdecode(report_path))  # type: ignore[attr-defined]  # opens Notepad on Windows
        except Exception:  # noqa: BLE001
            pass
    return 0
