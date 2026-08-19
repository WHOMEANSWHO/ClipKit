"""Build a single ClipKit.exe (no Python needed for Discord members)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    spec = ROOT / "clipkit.spec"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec)]
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    exe = ROOT / "dist" / "ClipKit.exe"
    if not exe.is_file():
        raise SystemExit("Build finished, but dist\\ClipKit.exe was not found.")
    release_dir = ROOT / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    shipped = release_dir / "ClipKit.exe"
    shutil.copy2(exe, shipped)
    print(f"Built {exe}")
    print(f"Copied {shipped}")
    print("That is the finished app. They double-click ClipKit.exe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
