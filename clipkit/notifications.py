"""Register ClipKit as a Windows notification app so toasts can show over games."""

from __future__ import annotations

import winreg

AUMID = "ClipKit.Desktop"


def register_toast_app() -> None:
    """Allow Windows toasts named ClipKit (needed for fullscreen exclusive)."""
    id_path = rf"Software\Classes\AppUserModelId\{AUMID}"
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, id_path)
    try:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "ClipKit")
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
