"""Delete-only recovery of committed search cleanup under the caller's update lock."""

from __future__ import annotations

from pathlib import Path
from typing import get_args
from urllib.parse import unquote, urlsplit

from sqlalchemy import select
from sqlalchemy.engine import make_url

from repowise.core.generation.models import PageType
from repowise.core.persistence import create_engine
from repowise.core.persistence.database import resolve_db_url
from repowise.core.persistence.models import Page, Repository
from repowise.core.persistence.search import _delete_page_ids

from .cleanup_debt import CleanupDebtError, clear_cleanup_debt, load_cleanup_debt


async def replay_cleanup_debt(repo_path: Path) -> int:
    """Resolve queued entries without rendering/embedding or changing SQL page rows.

    The caller owns the repo's writer lock. SQL admission and FTS deletion share
    a transaction; LanceDB is a separate store, so partial failure retains debt
    for an idempotent retry. This is not synchronization with concurrent init,
    generate or reindex writers outside that lock.
    """
    debt = load_cleanup_debt(repo_path, strict=True)
    if not any(debt.values()):
        return 0
    db_url = resolve_db_url(repo_path)
    parsed_url = make_url(db_url)
    if parsed_url.get_backend_name() == "sqlite":
        filename = parsed_url.database or ""
        if filename.startswith("file:"):
            filename = unquote(urlsplit(filename).path)
        if not filename or not Path(filename).is_file():
            raise CleanupDebtError("Deferred cleanup requires an existing SQLite database")
    engine = create_engine(db_url)
    cleared = {kind: set() for kind in debt}
    vector_error: Exception | None = None
    try:
        async with engine.begin() as conn:
            if engine.dialect.name == "sqlite":
                await conn.exec_driver_sql("BEGIN IMMEDIATE")
            repo_ids = list(
                (
                    await conn.execute(
                        select(Repository.id).where(Repository.local_path == str(repo_path))
                    )
                ).scalars()
            )
            if len(repo_ids) != 1:
                raise CleanupDebtError("Deferred cleanup repository identity does not match")
            repo_id = repo_ids[0]
            pending = sorted(set().union(*debt.values()))
            existing = {}
            for offset in range(0, len(pending), 500):
                rows = await conn.execute(
                    select(Page.id, Page.repository_id, Page.freshness_status).where(
                        Page.id.in_(pending[offset : offset + 500])
                    )
                )
                existing.update({pid: (owner, freshness) for pid, owner, freshness in rows})
            blocked = {
                pid
                for pid in pending
                if ":" not in pid
                or pid.partition(":")[0] not in get_args(PageType)
                or (pid in existing and existing[pid][0] != repo_id)
            }
            if blocked:
                raise CleanupDebtError(
                    f"Deferred cleanup blocked for {len(blocked)} foreign/unsupported IDs; "
                    "preserved cleanup-debt.json"
                )
            revived = {
                pid for pid in pending if pid in existing and existing[pid][1] != "tombstone"
            }
            eligible = {kind: ids - revived for kind, ids in debt.items()}
            if eligible["fts"]:
                await _delete_page_ids(conn, sorted(eligible["fts"]))
            cleared["fts"] = debt["fts"]
            cleared["vectors"] = debt["vectors"] & revived
            if eligible["vectors"]:
                lance_dir = repo_path / ".repowise" / "lancedb"
                if lance_dir.exists():
                    from repowise.core.persistence.vector_store import LanceDBVectorStore
                    from repowise.core.providers.embedding.base import MockEmbedder

                    store = LanceDBVectorStore(str(lance_dir), embedder=MockEmbedder())
                    try:
                        await store.delete_many(sorted(eligible["vectors"]))
                    except Exception as exc:
                        vector_error = exc
                    finally:
                        await store.close()
                if vector_error is None:
                    cleared["vectors"] = debt["vectors"]
        # Commit the FTS transaction before clearing its durable retry intent.
        for kind, ids in cleared.items():
            clear_cleanup_debt(repo_path, kind, ids, strict=True)
        if vector_error is not None:
            raise CleanupDebtError(
                f"Deferred vector cleanup failed for {len(eligible['vectors'])} IDs; "
                f"preserved cleanup-debt.json: {vector_error}"
            ) from vector_error
        return sum(map(len, cleared.values()))
    except CleanupDebtError:
        raise
    except Exception as exc:
        raise CleanupDebtError(
            f"Deferred cleanup failed; preserved cleanup-debt.json: {exc}"
        ) from exc
    finally:
        await engine.dispose()
