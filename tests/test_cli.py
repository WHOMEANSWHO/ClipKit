"""Tests for the ClipKit command-line entry point."""

from __future__ import annotations

import pytest

from clipkit import __version__
from clipkit.cli import main


def test_version_flag_prints_version_and_exits(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert __version__ in out
    assert "ClipKit" in out
