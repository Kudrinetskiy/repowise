"""The vector leg's budget must survive a cold store, and say so when it does not.

#1678: the first vector query in a process pays for the store open, the first
embed and the first ANN probe. Measured at 6.3s + 13.4s on a cold Windows index
where a warm query takes 0.19s. The budget was a hardcoded 8s wrapped in
``contextlib.suppress``, so that first query expired every time, the leg
returned ``[]``, and search silently degraded to full-text with nothing logged
and ``embedder_degraded`` still false.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from repowise.core.persistence.vector_store import InMemoryVectorStore, LanceDBVectorStore
from repowise.core.providers.embedding.base import KeylessEmbedder, MockEmbedder
from repowise.server.mcp_server import _state, tool_search
from repowise.server.mcp_server._helpers import (
    _VECTOR_TIMEOUT_DEFAULT_S,
    _VECTOR_TIMEOUT_ENV,
    _VECTOR_TIMEOUT_MAX_S,
    _resolve_repo_context,
    vector_search_timeout_s,
)


class _SlowStore:
    """A store whose first query takes longer than the old 8s budget."""

    embedder = object()

    def __init__(self, delay: float):
        self.delay = delay
        self.calls = 0

    async def search(self, query, limit=None, **kw):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return ["hit"]


class _Ctx:
    def __init__(self, store):
        self.vector_store = store
        self.fts = None


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(_VECTOR_TIMEOUT_ENV, raising=False)


def test_default_budget_clears_the_measured_cold_path() -> None:
    """13.4s was the measured cold first query. The default has to cover it."""
    assert vector_search_timeout_s() >= 15.0
    assert _VECTOR_TIMEOUT_DEFAULT_S >= 15.0


@pytest.mark.parametrize("raw,expected", [("60", 60.0), ("2.5", 2.5), ("  45  ", 45.0)])
def test_env_override_is_honoured(monkeypatch, raw, expected) -> None:
    monkeypatch.setenv(_VECTOR_TIMEOUT_ENV, raw)
    assert vector_search_timeout_s() == expected


def test_override_is_capped(monkeypatch) -> None:
    monkeypatch.setenv(_VECTOR_TIMEOUT_ENV, "9999")
    assert vector_search_timeout_s() == _VECTOR_TIMEOUT_MAX_S


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "nan", ""])
def test_unusable_override_keeps_the_default(monkeypatch, raw) -> None:
    """An unparseable value must not disable the leg, matching REPOWISE_EMBEDDING_TIMEOUT."""
    monkeypatch.setenv(_VECTOR_TIMEOUT_ENV, raw)
    assert vector_search_timeout_s() == _VECTOR_TIMEOUT_DEFAULT_S


def test_safe_vector_survives_a_query_slower_than_the_old_budget(monkeypatch) -> None:
    """The exact #1678 case: a query past 8s used to return []. It must not now."""
    monkeypatch.setenv(_VECTOR_TIMEOUT_ENV, "30")
    store = _SlowStore(delay=0.05)
    monkeypatch.setattr(tool_search, "store_has_semantic_vectors", lambda _s: True)
    out = asyncio.run(tool_search._safe_vector(_Ctx(store), "q", 5))
    assert out == ["hit"]
    assert store.calls == 1


def test_safe_vector_timeout_is_logged_not_swallowed(monkeypatch, caplog) -> None:
    """A timeout drops the whole semantic leg, so it must not be invisible."""
    monkeypatch.setenv(_VECTOR_TIMEOUT_ENV, "0.01")
    monkeypatch.setattr(tool_search, "store_has_semantic_vectors", lambda _s: True)
    with caplog.at_level(logging.WARNING, logger="repowise.mcp.search"):
        out = asyncio.run(tool_search._safe_vector(_Ctx(_SlowStore(delay=1.0)), "q", 5))
    assert out == []
    assert any(_VECTOR_TIMEOUT_ENV in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("consumer", ["search", "answer_retrieval"])
async def test_first_query_reads_store_loaded_after_single_repo_context_was_created(
    monkeypatch, tmp_path, consumer
) -> None:
    """A readiness wait must bind the completed loader's store, not cached None."""
    store = LanceDBVectorStore(str(tmp_path / "vectors"), MockEmbedder())
    await store.embed_and_upsert(
        "file_page:ready.py",
        "requirements workflow validation state transitions",
        {"title": "Ready page", "page_type": "file_page", "target_path": "ready.py"},
    )
    ready = asyncio.Event()
    monkeypatch.setattr(_state, "_registry", None)
    monkeypatch.setattr(_state, "_repo_path", str(tmp_path))
    monkeypatch.setattr(_state, "_vector_store", None)
    monkeypatch.setattr(_state, "_decision_store", None)
    monkeypatch.setattr(_state, "_vector_store_ready", ready)
    ctx = await _resolve_repo_context()

    async def finish_loading():
        await asyncio.sleep(0)
        _state._vector_store = store
        _state._decision_store = store
        ready.set()

    loading = asyncio.create_task(finish_loading())
    try:
        if consumer == "search":
            await tool_search._wait_for_vector_store(ctx)
            hits = await tool_search._safe_vector(ctx, "requirements workflow validation", 5)
        else:
            from repowise.server.mcp_server._answer_pipeline import _safe_vector_search

            def no_provider(*args, **kwargs):
                raise AssertionError("retrieval must not dispatch a prose provider")

            monkeypatch.setattr("repowise.core.providers.llm.registry.get_provider", no_provider)
            hits = await _safe_vector_search(ctx, "requirements workflow validation")
        assert [hit.page_id for hit in hits] == ["file_page:ready.py"]
        decision_hits = await ctx.decision_store.search("requirements workflow validation", limit=5)
        assert [hit.page_id for hit in decision_hits] == ["file_page:ready.py"]
    finally:
        await loading
        await store.close()


async def _retrieve(ctx, consumer):
    if consumer == "answer_retrieval":
        from repowise.server.mcp_server._answer_pipeline import _safe_vector_search

        return await _safe_vector_search(ctx, "requirements workflow validation")
    await tool_search._wait_for_vector_store(ctx)
    return await tool_search._safe_vector(ctx, "requirements workflow validation", 5)


async def _memory_store(page_id):
    store = InMemoryVectorStore(embedder=MockEmbedder())
    await store.embed_and_upsert(
        page_id,
        "requirements workflow validation",
        {"title": "Ready page", "page_type": "file_page"},
    )
    return store


@pytest.mark.parametrize("consumer", ["search", "answer_retrieval"])
@pytest.mark.parametrize(
    "isolation", ["workspace", "alias", "path", "replaced_event", "session_factory"]
)
async def test_readiness_keeps_other_repo_or_session_resources(
    monkeypatch, tmp_path, consumer, isolation, factory
):
    own = await _memory_store("file_page:own.py")
    other = await _memory_store("file_page:other.py")
    ready = asyncio.Event()
    monkeypatch.setattr(_state, "_registry", None)
    monkeypatch.setattr(_state, "_repo_path", str(tmp_path))
    monkeypatch.setattr(_state, "_vector_store", own)
    monkeypatch.setattr(_state, "_decision_store", own)
    monkeypatch.setattr(_state, "_vector_store_ready", ready)
    monkeypatch.setattr(_state, "_session_factory", factory)
    ctx = await _resolve_repo_context()
    _state._vector_store = other
    _state._decision_store = other
    foreign_engine = None
    if isolation == "workspace":
        # The default workspace alias/root/event may also match the globals.
        monkeypatch.setattr(_state, "_registry", object())
    elif isolation == "alias":
        ctx.alias = "another-repo"
    elif isolation == "path":
        ctx.path = tmp_path / "another-repo"
    elif isolation == "replaced_event":
        replacement = asyncio.Event()
        replacement.set()
        monkeypatch.setattr(_state, "_vector_store_ready", replacement)
    else:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        foreign_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with foreign_engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
        ctx.session_factory = async_sessionmaker(foreign_engine)
    ready.set()
    try:
        hits = await _retrieve(ctx, consumer)
        assert [hit.page_id for hit in hits] == ["file_page:own.py"]
        decision_hits = await ctx.decision_store.search("requirements workflow validation", limit=5)
        assert [hit.page_id for hit in decision_hits] == ["file_page:own.py"]
    finally:
        await own.close()
        await other.close()
        if foreign_engine is not None:
            await foreign_engine.dispose()


@pytest.mark.parametrize("consumer", ["search", "answer_retrieval"])
@pytest.mark.parametrize("readiness", ["no_event", "timeout"])
async def test_unavailable_store_keeps_bounded_empty_fallback(
    monkeypatch, tmp_path, consumer, readiness
):
    from repowise.server.mcp_server import _helpers

    ready = asyncio.Event() if readiness == "timeout" else None
    monkeypatch.setattr(_state, "_registry", None)
    monkeypatch.setattr(_state, "_repo_path", str(tmp_path))
    monkeypatch.setattr(_state, "_vector_store", None)
    monkeypatch.setattr(_state, "_decision_store", None)
    monkeypatch.setattr(_state, "_vector_store_ready", ready)
    ctx = await _resolve_repo_context()
    real_wait = asyncio.wait_for
    budgets = []

    async def short_wait(awaitable, timeout):
        budgets.append(timeout)
        return await real_wait(awaitable, timeout=0.001)

    monkeypatch.setattr(_helpers.asyncio, "wait_for", short_wait)
    hits = await real_wait(_retrieve(ctx, consumer), timeout=0.1)
    assert hits == []
    assert budgets == ([30.0] if readiness == "timeout" else [])


async def test_warm_keyless_answer_retrieval_never_waits_or_embeds(monkeypatch):
    from repowise.server.mcp_server._answer_pipeline import _safe_vector_search

    async def no_embed(*args, **kwargs):
        raise AssertionError("keyless retrieval must not embed")

    monkeypatch.setattr(KeylessEmbedder, "embed", no_embed)
    store = InMemoryVectorStore(embedder=KeylessEmbedder())
    ctx = SimpleNamespace(vector_store=store, vector_store_ready=asyncio.Event())
    try:
        assert await asyncio.wait_for(_safe_vector_search(ctx, "question"), timeout=0.1) == []
    finally:
        await store.close()


def test_no_hardcoded_eight_second_vector_budget() -> None:
    """Pins the fix: every vector site reads the shared budget."""
    from pathlib import Path

    root = Path(tool_search.__file__).parent.parent
    for path in (
        *sorted((root / "tool_search").glob("*.py")),
        *sorted((root / "_answer_pipeline").glob("*.py")),
    ):
        text = path.read_text(encoding="utf-8")
        assert "timeout=8.0" not in text, f"{path.name} still hardcodes the old vector budget"
