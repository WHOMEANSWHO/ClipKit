"""Toast identity for clip-saved notifications — tied to OBS, not ClipKit.exe."""

from __future__ import annotations

import subprocess
import winreg
from pathlib import Path

from .paths import icon_file
from .startup import create_shortcut, start_menu_dir

AUMID = "ClipKit.Clips"
TOAST_SHORTCUT = "ClipKit Clips.lnk"


def register_toast_app(*, icon: Path | None = None) -> None:
    """Allow Windows toasts named ClipKit without ClipKit.exe staying installed."""
    id_path = rf"Software\Classes\AppUserModelId\{AUMID}"
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, id_path)
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "ClipKit")
        if icon is not None and icon.is_file():
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))
    finally:
        winreg.CloseKey(key)

    notify_path = rf"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings\{AUMID}"
    nkey = winreg.CreateKey(winreg.HKEY_CURRENT_USER, notify_path)
    try:
        winreg.SetValueEx(nkey, "Enabled", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(nkey, "ShowInActionCenter", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(nkey, "AllowContentAboveLock", 0, winreg.REG_DWORD, 1)
    finally:
        winreg.CloseKey(nkey)


def _stamp_shortcut_aumid(path: Path, aumid: str) -> None:
    """Set System.AppUserModel.ID on a .lnk so toasts work without ClipKit installed."""
    import tempfile

    script = r"""
param($LinkPath, $AppId)
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
public class CShellLink {}

[StructLayout(LayoutKind.Sequential, Pack = 4)]
public struct PropertyKey {
    public Guid fmtid;
    public uint pid;
}

[StructLayout(LayoutKind.Explicit)]
public struct PropVariant {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr pointerValue;
}

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
public interface IPropertyStore {
    void GetCount(out uint cProps);
    void GetAt(uint iProp, out PropertyKey pkey);
    void GetValue(ref PropertyKey key, out PropVariant pv);
    void SetValue(ref PropertyKey key, ref PropVariant pv);
    void Commit();
}

public static class ShortcutAumid {
    public static void Set(string path, string aumid) {
        var file = (IPersistFile)new CShellLink();
        file.Load(path, 2);
        var store = (IPropertyStore)file;
        var key = new PropertyKey {
            fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
            pid = 5
        };
        var value = new PropVariant { vt = 31, pointerValue = Marshal.StringToCoTaskMemUni(aumid) };
        store.SetValue(ref key, ref value);
        store.Commit();
        file.Save(path, true);
        Marshal.FreeCoTaskMem(value.pointerValue);
    }
}
"@
[ShortcutAumid]::Set($LinkPath, $AppId)
"""
    hidden = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        ps1 = handle.name
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps1,
                "-LinkPath",
                str(path),
                "-AppId",
                aumid,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=hidden,
        )
    finally:
        try:
            Path(ps1).unlink(missing_ok=True)
        except OSError:
            pass


def _visible_toast_shortcut_dirs() -> list[Path]:
    home = Path.home()
    return [
        start_menu_dir(),
        start_menu_dir() / "Startup",
        home / "Desktop",
        home / "OneDrive" / "Desktop",
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
    ]


def remove_obs_toast_shortcut() -> None:
    """Remove the old Start Menu 'ClipKit Clips' shortcut that used the OBS icon."""
    for folder in _visible_toast_shortcut_dirs():
        path = folder / TOAST_SHORTCUT
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def install_toast_identity(obs_exe: Path | None, *, refresh_shortcut: bool = False) -> None:
    """Register clip toasts in the registry. Do not create or rename an OBS shortcut."""
    del obs_exe, refresh_shortcut
    register_toast_app(icon=icon_file())
    remove_obs_toast_shortcut()
    powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    if not powershell.is_file():
        return
    hidden = Path.home() / "AppData" / "Roaming" / "ClipKit" / TOAST_SHORTCUT
    created = create_shortcut(
        hidden,
        powershell,
        working_directory=powershell.parent,
        icon=icon_file() or powershell,
        description="ClipKit clip saved notifications",
    )
    if created is not None:
        try:
            _stamp_shortcut_aumid(created, AUMID)
        except (OSError, subprocess.TimeoutExpired):
            pass
