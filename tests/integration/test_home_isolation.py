from __future__ import annotations

from pathlib import Path


def test_integration_suite_uses_isolated_home(tmp_path: Path) -> None:
    """Integration tests must never write editor config into the real HOME."""
    assert Path.home().resolve() == (tmp_path / "home").resolve()
