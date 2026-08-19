"""Build a single ClipKit.exe (no Python needed for Discord members)."""

from __future__ import annotations

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
    print(f"Built {exe}")
    print("Send that one file. They double-click ClipKit.exe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
