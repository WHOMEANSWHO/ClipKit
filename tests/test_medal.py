"""Tests for the Medal sorter config writer."""

from __future__ import annotations

import json
from pathlib import Path

from clipkit import medal


def test_write_medal_sorter_config_writes_atomically(tmp_path, monkeypatch):
    cfg = tmp_path / "medal-sorter.json"
    monkeypatch.setattr(medal, "sorter_config_path", lambda: cfg)
    output = tmp_path / "clips"
    watch = [tmp_path / "w1", tmp_path / "w2"]

    payload = medal.write_medal_sorter_config(output, watch=watch)

    assert cfg.is_file()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data == payload
    assert data["output"] == str(output)
    assert data["watch"] == [str(p) for p in watch]
    # Atomic write must not leave a temp file behind.
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())
