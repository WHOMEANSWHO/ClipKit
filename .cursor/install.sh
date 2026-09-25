#!/usr/bin/env bash
#
# Cloud Agent setup for ClipKit.
#
# ClipKit is a Windows-only Python desktop app (it uses winreg, ctypes.windll,
# OBS, and PowerShell). The supported developer workflow is Windows-native:
#   python -m pip install -r requirements.txt
#   python clipkit.py            # Tkinter GUI
#   python clipkit.py --detect   # print PC specs / recommended preset
#   python build.py              # PyInstaller -> dist/ClipKit.exe
#
# To run and build it on a Linux Cloud Agent we use Wine plus a real Windows
# Python. This is the standard way to cross-build Windows PyInstaller exes.
#
# The script is idempotent: it skips work that is already done, so it is safe to
# re-run and to bake into an environment snapshot/build.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Pinned Windows Python. tkinter (Include_tcltk) is required for the GUI.
PYVER="3.12.8"
export WINEPREFIX="${WINEPREFIX:-$HOME/.wine-clipkit}"
export WINEARCH="win64"
export WINEDEBUG="-all"

log() { printf '\n=== %s ===\n' "$*"; }

# ---------------------------------------------------------------------------
# 1. System packages: Wine (64 + 32 bit), Xvfb (headless display), helpers.
# ---------------------------------------------------------------------------
if ! command -v wine >/dev/null 2>&1; then
  log "Installing Wine and supporting packages (needs sudo)"
  sudo dpkg --add-architecture i386
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    wine wine64 wine32:i386 winbind xvfb cabextract
else
  log "Wine already installed: $(wine --version)"
fi

# xvfb-run gives Wine a display without a real desktop.
if ! command -v xvfb-run >/dev/null 2>&1; then
  sudo apt-get install -y --no-install-recommends xvfb
fi

# ---------------------------------------------------------------------------
# 2. Wine prefix.
# ---------------------------------------------------------------------------
if [ ! -f "$WINEPREFIX/system.reg" ]; then
  log "Initialising Wine prefix at $WINEPREFIX"
  xvfb-run -a wineboot --init
  # Give wineserver a moment to settle before the next Wine command.
  sleep 3
else
  log "Wine prefix already initialised at $WINEPREFIX"
fi

# ---------------------------------------------------------------------------
# 3. Windows Python (installed inside the Wine prefix).
# ---------------------------------------------------------------------------
WINPY="$WINEPREFIX/drive_c/Program Files/Python312/python.exe"
if [ ! -f "$WINPY" ]; then
  log "Installing Windows Python $PYVER into the Wine prefix"
  INSTALLER="/tmp/python-${PYVER}-amd64.exe"
  if [ ! -f "$INSTALLER" ]; then
    curl -fsSL -o "$INSTALLER" \
      "https://www.python.org/ftp/python/${PYVER}/python-${PYVER}-amd64.exe"
  fi
  xvfb-run -a wine "$INSTALLER" /quiet \
    InstallAllUsers=1 PrependPath=1 Include_tcltk=1 Include_pip=1 \
    Include_test=0 Shortcuts=0 AssociateFiles=0
  sleep 3
else
  log "Windows Python already installed"
fi

# ---------------------------------------------------------------------------
# 4. Project Python dependencies (PyInstaller etc.) into the Wine Python.
# ---------------------------------------------------------------------------
log "Installing Python requirements into the Wine Python"
xvfb-run -a wine "$WINPY" -m pip install --no-warn-script-location \
  -r "$REPO_ROOT/requirements.txt"

# ---------------------------------------------------------------------------
# 5. Smoke test: run the app's cross-platform CLI path.
# ---------------------------------------------------------------------------
log "Smoke test: clipkit --detect"
xvfb-run -a wine "$WINPY" "$REPO_ROOT/clipkit.py" --detect || true

cat <<EOF

ClipKit dev environment is ready.

Wine prefix : $WINEPREFIX
Windows Py  : $WINPY

Common commands (run from the repo root):
  export WINEPREFIX="$WINEPREFIX"
  xvfb-run -a wine python.exe clipkit.py            # launch the GUI (or: pythonw.exe clipkit.pyw)
  xvfb-run -a wine python.exe clipkit.py --detect   # print specs / recommended preset
  xvfb-run -a wine python.exe build.py              # build dist/ClipKit.exe with PyInstaller
EOF
