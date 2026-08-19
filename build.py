"""Build a standalone ClipKit folder (no Python needed for Discord members)."""

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
    exe = ROOT / "dist" / "ClipKit" / "ClipKit.exe"
    readme = ROOT / "packaging" / "read_me.txt"
    if readme.is_file() and exe.is_file():
        (exe.parent / "Read me.txt").write_text(readme.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Built {exe}")
    print("Zip the dist\\ClipKit folder and share that. They double-click ClipKit.exe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
