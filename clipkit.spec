# -*- mode: python ; coding: utf-8 -*-
"""Standalone ClipKit.exe for Discord. Rebuild with: python build.py"""

from pathlib import Path

spec_dir = Path(SPECPATH)

a = Analysis(
    [str(spec_dir / "clipkit.pyw")],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=[(str(spec_dir / "scripts"), "scripts")],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClipKit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ClipKit",
)
