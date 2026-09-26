"""A small on-disk log so a failed Apply can be diagnosed after the fact.

ClipKit only ever surfaced errors in a dialog that vanished when closed. This
writes a rolling log to ``%APPDATA%\\ClipKit\\clipkit.log`` that users can share
when something goes wrong. Logging never raises: if the file cannot be opened we
fall back to a no-op handler so it can't break the app.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .paths import appdata_dir

_LOGGER_NAME = "clipkit"
_configured = False


def log_path() -> Path:
    return appdata_dir() / "ClipKit" / "clipkit.log"


def get_logger() -> logging.Logger:
    """Return the shared ClipKit logger, configuring its file handler once."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    except OSError:
        handler = logging.NullHandler()
    logger.addHandler(handler)
    _configured = True
    return logger


def log(message: str) -> None:
    """Best-effort info log; swallows any logging error."""
    try:
        get_logger().info(message)
    except Exception:  # noqa: BLE001 - logging must never break the app
        pass


def log_exception(message: str) -> None:
    """Best-effort error log including the current traceback."""
    try:
        get_logger().exception(message)
    except Exception:  # noqa: BLE001 - logging must never break the app
        pass
