"""Deferred deletion must reconcile intent against current SQL ownership."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select, text

from repowise.core.persistence import create_engine, create_session_factory, get_session, init_db
from repowise.core.persistence.crud import upsert_page
from repowise.core.persistence.database import resolve_db_url
from repowise.core.persistence.models import Page
from repowise.core.persistence.search import FullTextSearch
from repowise.core.persistence.vector_store import LanceDBVectorStore
from repowise.core.pipeline.cleanup_debt import (
    CleanupDebtError,
    has_pending_cleanup,
    load_cleanup_debt,
    record_cleanup_debt,
)
from repowise.core.pipeline.cleanup_replay import replay_cleanup_debt
from repowise.core.providers.embedding.base import MockEmbedder
from tests.unit.persistence.helpers import insert_repo, make_page_kwargs


@pytest.fixture
async def cleanup_store(tmp_path, request, monkeypatch):
    (tmp_path / ".repowise").mkdir()
    if getattr(request, "param", None) == "configured":
        monkeypatch.setenv("REPOWISE_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'shared.sqlite'}")
    engine = create_engine(resolve_db_url(tmp_path))
    store = LanceDBVectorStore(str(tmp_path / ".repowise/lancedb"), MockEmbedder())
    try:
        await init_db(engine)
        sf = create_session_factory(engine)
        async with get_session(sf) as session:
            repo = await insert_repo(session, local_path=str(tmp_path))
            owner = repo.id
        fts = FullTextSearch(engine)
        await fts.ensure_index()
        yield tmp_path, engine, sf, store, fts, owner
    finally:
        await store.close()
        await engine.dispose()


async def _seed_search(fts, store, ids):
    for pid in ids:
        await fts.index(
            pid, "Stored evidence", "Stored evidence", summary="Evidence", target_path=pid
        )
    await store.embed_batch([(pid, "Stored evidence", {}) for pid in ids])


async def _fts_ids(engine):
    async with engine.connect() as conn:
        return set((await conn.execute(text("SELECT page_id FROM page_fts"))).scalars())


@pytest.mark.parametrize("cleanup_store", ["configured"], indirect=True)
async def test_replay_uses_existing_configured_database_without_creating_local_store(cleanup_store):
    root, engine, _sf, store, fts, _owner = cleanup_store
    ghost = "scc_page:gone"
    await _seed_search(fts, store, [ghost])
    for kind in ("fts", "vectors"):
        record_cleanup_debt(root, kind, {ghost})
    assert await replay_cleanup_debt(root) == 2
    await store.close()
    assert not await store.list_page_ids()
    assert not await _fts_ids(engine)
    assert not (root / ".repowise/wiki.db").exists()


async def test_replay_does_not_create_missing_configured_database(tmp_path, monkeypatch):
    missing = tmp_path / "missing.sqlite"
    monkeypatch.setenv("REPOWISE_DB_URL", f"sqlite+aiosqlite:///{missing}")
    record_cleanup_debt(tmp_path, "vectors", {"scc_page:gone"})
    with pytest.raises(CleanupDebtError, match="existing SQLite database"):
        await replay_cleanup_debt(tmp_path)
    assert not missing.exists()
    assert load_cleanup_debt(tmp_path)["vectors"] == {"scc_page:gone"}


@pytest.mark.parametrize("case", ["revived", "tombstone", "foreign", "decision", "unknown"])
async def test_replay_protects_current_ownership_and_unrelated_search_rows(
    cleanup_store, monkeypatch, case
):
    root, engine, sf, store, fts, owner = cleanup_store
    ghost = "scc_page:gone"
    current = {
        "revived": "module_page:revived",
        "tombstone": "module_page:retired",
        "foreign": "file_page:other.py",
        "decision": "decision:queued",
        "unknown": "episode:queued",
    }[case]
    unrelated = "decision:unrelated"
    page_before = None
    if case in {"revived", "tombstone", "foreign"}:
        async with get_session(sf) as session:
            if case == "foreign":
                other = await insert_repo(session, name="other", local_path=str(root / "other"))
                owner = other.id
            kwargs = make_page_kwargs(
                owner,
                page_id=current,
                target_path="revived",
                page_type="module_page" if case == "revived" else "file_page",
            )
            kwargs.update(
                provider_name="codex_cli",
                model_name="codex_cli/gpt-6-luna",
                content="Model-written evidence must stay unchanged",
                digest="Kept digest",
                input_tokens=123,
                output_tokens=17,
            )
            if case == "tombstone":
                kwargs["freshness_status"] = "tombstone"
            await upsert_page(session, **kwargs)
        async with engine.connect() as conn:
            page_before = tuple((await conn.execute(select(Page.__table__))).one())
    await _seed_search(fts, store, [ghost, current, unrelated])
    for kind in ("fts", "vectors"):
        record_cleanup_debt(root, kind, {ghost, current})
    ledger = root / ".repowise/cleanup-debt.json"
    ledger_before = ledger.read_bytes()

    async def no_embedding(*args, **kwargs):
        pytest.fail("Cleanup must not compute embeddings")

    monkeypatch.setattr(MockEmbedder, "embed", no_embedding)
    if case in {"revived", "tombstone"}:
        assert await replay_cleanup_debt(root) == 4
        expected = {current, unrelated} if case == "revived" else {unrelated}
        assert not has_pending_cleanup(root)
    else:
        with pytest.raises(CleanupDebtError):
            await replay_cleanup_debt(root)
        expected = {ghost, current, unrelated}
        assert ledger.read_bytes() == ledger_before
    # Replay writes through its own handle; reload the committed table version.
    await store.close()
    assert await store.list_page_ids() == expected
    assert await _fts_ids(engine) == expected
    if page_before is not None:
        async with engine.connect() as conn:
            assert tuple((await conn.execute(select(Page.__table__))).one()) == page_before


@pytest.mark.parametrize("failed_store", ["fts", "vectors"])
async def test_replay_retains_failed_ids_and_retries_without_embedding(
    cleanup_store, monkeypatch, failed_store
):
    root, engine, _sf, store, fts, _owner = cleanup_store
    ghost, unrelated = "scc_page:gone", "decision:unrelated"
    await _seed_search(fts, store, [ghost, unrelated])
    for kind in ("fts", "vectors"):
        record_cleanup_debt(root, kind, {ghost})

    async def unavailable(*args, **kwargs):
        raise OSError("fixture cleanup unavailable")

    async def no_embedding(*args, **kwargs):
        pytest.fail("Retry must not compute embeddings")

    monkeypatch.setattr(MockEmbedder, "embed", no_embedding)
    with monkeypatch.context() as failure:
        if failed_store == "fts":
            failure.setattr("repowise.core.pipeline.cleanup_replay._delete_page_ids", unavailable)
        else:
            failure.setattr(LanceDBVectorStore, "delete_many", unavailable)
        with pytest.raises(CleanupDebtError, match="preserved cleanup-debt"):
            await replay_cleanup_debt(root)
    debt = load_cleanup_debt(root)
    assert debt["vectors"] == {ghost}
    assert debt["fts"] == ({ghost} if failed_store == "fts" else set())
    await store.close()
    assert await store.list_page_ids() == {ghost, unrelated}
    await replay_cleanup_debt(root)
    await store.close()
    assert await store.list_page_ids() == {unrelated}
    assert await _fts_ids(engine) == {unrelated}
    assert not has_pending_cleanup(root)


@pytest.mark.parametrize("case", ["json", "wrong-shape", "dangling-link"])
def test_unreadable_debt_is_not_an_up_to_date_shortcut(tmp_path, case):
    (tmp_path / ".repowise").mkdir()
    ledger = tmp_path / ".repowise/cleanup-debt.json"
    if case == "dangling-link":
        ledger.symlink_to(tmp_path / "missing")
    else:
        ledger.write_text("{bad" if case == "json" else json.dumps({"vectors": [123]}))
    assert has_pending_cleanup(tmp_path)
    with pytest.raises(CleanupDebtError):
        load_cleanup_debt(tmp_path, strict=True)
