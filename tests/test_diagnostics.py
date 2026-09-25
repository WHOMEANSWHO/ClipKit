"""Tests for the crash-safe diagnostics log."""

from __future__ import annotations

import logging
from pathlib import Path

from clipkit import diagnostics


def _reset_logger() -> None:
    diagnostics._configured = False
    logger = logging.getLogger("clipkit")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass


def test_log_path_uses_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert diagnostics.log_path() == tmp_path / "ClipKit" / "clipkit.log"


def test_log_writes_message_to_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    _reset_logger()
    try:
        diagnostics.log("hello-clipkit-marker")
        for handler in logging.getLogger("clipkit").handlers:
            handler.flush()
        content = (tmp_path / "ClipKit" / "clipkit.log").read_text(encoding="utf-8")
        assert "hello-clipkit-marker" in content
    finally:
        _reset_logger()


def test_log_never_raises_even_when_path_fails(monkeypatch):
    _reset_logger()

    def boom() -> Path:
        raise OSError("no appdata")

    monkeypatch.setattr(diagnostics, "log_path", boom)
    try:
        diagnostics.log("should not raise")
        diagnostics.log_exception("still should not raise")
    finally:
        _reset_logger()
