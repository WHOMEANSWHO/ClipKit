"""Tests for Windows app registration metadata."""

from __future__ import annotations

from clipkit.windows_app import HOMEPAGE, PUBLISHER


def test_publisher_matches_github_org():
    # Publisher shows up in Windows "Apps & features"; keep it consistent with the repo owner.
    assert PUBLISHER == "WHOMEANSWHO"
    assert PUBLISHER in HOMEPAGE
