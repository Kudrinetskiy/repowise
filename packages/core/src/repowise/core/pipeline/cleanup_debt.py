"""Durable retry ledger for post-transaction search-index cleanup."""

from __future__ import annotations

import json
from pathlib import Path

from repowise.core.fsutils import atomic_write_text

_KINDS = ("fts", "vectors")


def _path(repo_path: Path) -> Path:
    return repo_path / ".repowise" / "cleanup-debt.json"


class CleanupDebtError(RuntimeError):
    """Deferred search cleanup could not be safely completed."""


def load_cleanup_debt(repo_path: Path, *, strict: bool = False) -> dict[str, set[str]]:
    path = _path(repo_path)
    try:
        if strict and (
            path.is_symlink()
            or (path.exists() and (not path.is_file() or path.stat().st_size > 16 * 1024 * 1024))
        ):
            raise CleanupDebtError("Unsafe or oversized deferred cleanup ledger")
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if strict and (
            not isinstance(raw, dict)
            or set(raw) - set(_KINDS)
            or any(
                not isinstance(raw.get(kind, []), list)
                or any(not isinstance(pid, str) or not pid for pid in raw.get(kind, []))
                for kind in _KINDS
            )
        ):
            raise CleanupDebtError("Malformed deferred cleanup ledger")
    except (OSError, ValueError, TypeError) as exc:
        if strict:
            raise CleanupDebtError("Cannot read deferred cleanup ledger") from exc
        raw = {}
    return {kind: set(raw.get(kind) or []) for kind in _KINDS}


def has_pending_cleanup(repo_path: Path) -> bool:
    """Unreadable debt must reach error reporting, never an up-to-date shortcut."""
    try:
        return any(load_cleanup_debt(repo_path, strict=True).values())
    except CleanupDebtError:
        return True


def record_cleanup_debt(repo_path: Path, kind: str, page_ids: set[str]) -> None:
    if not page_ids:
        return
    debt = load_cleanup_debt(repo_path)
    debt[kind].update(page_ids)
    path = _path(repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps({key: sorted(values) for key, values in debt.items()}, indent=2),
    )


def clear_cleanup_debt(
    repo_path: Path, kind: str, page_ids: set[str], *, strict: bool = False
) -> None:
    if not page_ids:
        return
    debt = load_cleanup_debt(repo_path, strict=strict)
    debt[kind].difference_update(page_ids)
    path = _path(repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps({key: sorted(values) for key, values in debt.items()}, indent=2),
    )
