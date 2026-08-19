# -*- mode: python ; coding: utf-8 -*-
"""Single ClipKit.exe for Discord. Rebuild with: python build.py"""

from pathlib import Path

spec_dir = Path(SPECPATH)

a = Analysis(
    [str(spec_dir / "clipkit.pyw")],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=[
        (str(spec_dir / "scripts"), "scripts"),
        (str(spec_dir / "packaging" / "clipkit.ico"), "packaging"),
        (str(spec_dir / "packaging" / "clipkit-icon.png"), "packaging"),
        (str(spec_dir / "packaging" / "clipkit-mark.png"), "packaging"),
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ClipKit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(spec_dir / "packaging" / "clipkit.ico"),
)
