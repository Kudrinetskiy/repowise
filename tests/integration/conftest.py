"""Integration-test isolation for user-level editor configuration."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch):
    """Never let an end-to-end CLI invocation mutate the developer's HOME."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    return fake_home
