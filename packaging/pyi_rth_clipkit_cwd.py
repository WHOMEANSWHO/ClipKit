# PyInstaller runtime hook: leave the onefile extract folder immediately.
# If the process cwd stays inside _MEI*, Windows cannot delete it on exit
# and shows "Failed to remove temporary directory".

import os
import sys

if getattr(sys, "frozen", False):
    exe_dir = os.path.dirname(sys.executable)
    try:
        os.chdir(exe_dir)
    except OSError:
        fallback = os.environ.get("USERPROFILE") or os.environ.get("SystemRoot") or r"C:\Windows"
        try:
            os.chdir(fallback)
        except OSError:
            pass
