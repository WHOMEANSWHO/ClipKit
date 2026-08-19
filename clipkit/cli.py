"""Command-line entry for ClipKit."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from .paths import leave_extract_dir

    leave_extract_dir()
    parser = argparse.ArgumentParser(description="ClipKit OBS clipping setup")
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Print PC specs and the recommended preset, then exit",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove ClipKit from the Start menu and Windows Apps list",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Uninstall without asking",
    )
    parser.add_argument(
        "--portable",
        action="store_true",
        help="Run this exe without installing it as a Windows app",
    )
    parser.add_argument(
        "--dry-run",
        metavar="DIR",
        help="Write a ClipKit profile into DIR instead of the real OBS config",
    )
    args = parser.parse_args(argv)

    if args.uninstall:
        from .windows_app import uninstall_windows_app

        return uninstall_windows_app(quiet=args.quiet)

    if args.portable:
        import os

        os.environ["CLIPKIT_PORTABLE"] = "1"

    if args.dry_run:
        from pathlib import Path

        from .hardware import detect
        from .obs import apply_setup
        from .presets import build_preset, recommend_id

        hw = detect()
        preset = build_preset(hw, recommend_id(hw))
        target = Path(args.dry_run)
        target.mkdir(parents=True, exist_ok=True)
        (target / "global.ini").write_text("[General]\n", encoding="utf-8")
        result = apply_setup(preset, target / "clips", config_dir=target, make_default=True)
        print(f"Wrote dry-run profile to {target}")
        for key, value in result.items():
            print(f"  {key}: {value}")
        return 0

    if args.detect:
        from .hardware import detect
        from .presets import all_presets, recommend_id

        hw = detect()
        rec = recommend_id(hw)
        presets = all_presets(hw)
        print(f"GPU:      {hw.gpu_name}")
        print(f"VRAM:     {hw.vram_gb:g} GB")
        print(f"CPU:      {hw.cpu_name}")
        print(f"RAM:      {hw.ram_gb:g} GB")
        print(f"Display:  {hw.display_label}")
        print(
            f"OBS:      {'running' if hw.obs_running else 'not running'}"
            f" / {'installed' if hw.obs_installed else 'not installed'}"
        )
        if hw.obs_exe:
            print(f"          {hw.obs_exe}")
        print(f"Recommend: {rec}")
        for pid, preset in presets.items():
            mark = " <==" if pid == rec else ""
            print(
                f"  {preset.label}: {preset.output_width}x{preset.output_height} "
                f"{preset.fps}fps {preset.encoder_label} "
                f"{preset.bitrate_kbps} kbps "
                f"{preset.replay_seconds // 60} min{mark}"
            )
        for note in hw.notes:
            print(f"note: {note}")
        return 0

    from .app import run

    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
