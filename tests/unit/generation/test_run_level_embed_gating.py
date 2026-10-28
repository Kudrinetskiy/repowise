"""Embed gating in ``_GenerationRun.run_level``.

Pages whose content was reused verbatim from the prior run (prompt-hash /
content-hash cache hit) already have an identical vector in any store that
persists across runs; re-embedding them re-bills the embedder for every
unchanged page on every update. run_level therefore skips them, but ONLY when
the store persists across runs: the in-memory store starts empty each run and
still needs every page embedded.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from repowise.core.generation.models import GeneratedPage
from repowise.core.generation.page_generator.orchestrate import _GenerationRun


def _page(page_id: str, *, reused: bool = False) -> GeneratedPage:
    now = datetime.now(UTC).isoformat()
    page = GeneratedPage(
        page_id=page_id,
        page_type="file_page",
        title=page_id,
        content=f"# {page_id}",
        source_hash="deadbeef",
        model_name="mock-model",
        provider_name="mock",
        input_tokens=0 if reused else 1,
        output_tokens=0 if reused else 1,
        cached_tokens=0,
        generation_level=2,
        target_path=page_id,
        created_at=now,
        updated_at=now,
    )
    if reused:
        page.metadata["reused_from_prior_run"] = True
    return page


class _RecordingStore:
    def __init__(self, *, persists: bool) -> None:
        self.persists_across_runs = persists
        self.batches: list[list[tuple]] = []

    async def embed_batch(self, items):
        self.batches.append(list(items))


def _fake_run(store) -> SimpleNamespace:
    return SimpleNamespace(
        semaphore=asyncio.Semaphore(4),
        job_system=None,
        job_id=None,
        on_page_done=None,
        on_page_ready=None,
        on_embed=None,
        vector_store=store,
        completed_page_summaries={},
        timings=None,
    )


def _run_level(store) -> list[str]:
    async def _go():
        async def fresh():
            return _page("fresh.py")

        async def reused():
            return _page("reused.py", reused=True)

        run = _fake_run(store)
        await _GenerationRun.run_level(run, [("p1", fresh()), ("p2", reused())], level=2)
        return [pid for batch in store.batches for (pid, *_rest) in batch]

    return asyncio.run(_go())


def test_persistent_store_skips_reused_pages() -> None:
    store = _RecordingStore(persists=True)
    embedded = _run_level(store)
    assert "fresh.py" in embedded
    assert "reused.py" not in embedded


def test_ephemeral_store_still_embeds_reused_pages() -> None:
    """In-memory stores are rebuilt every run: reuse must not starve them."""
    store = _RecordingStore(persists=False)
    embedded = _run_level(store)
    assert "fresh.py" in embedded
    assert "reused.py" in embedded


class _FailingStore:
    persists_across_runs = True

    async def embed_batch(self, items):
        raise AttributeError("module 'lancedb' has no attribute 'connect_async'")


@pytest.mark.parametrize(
    ("recovery", "failed_count"), [("success", 0), ("partial", 1), ("outage", 2)]
)
@pytest.mark.parametrize("stage", ["embedding", "persistence"])
def test_partial_batch_retries_only_failed_ids_once(recovery, failed_count, stage) -> None:
    from repowise.core.persistence.vector_store import BatchChunkFailure, BatchEmbeddingError

    class PartialStore(_RecordingStore):
        async def embed_batch(self, items):
            self.batches.append(list(items))
            if len(self.batches) == 1:
                failed = items[1:]
            elif recovery == "success":
                return
            elif recovery == "partial":
                failed = items[1:]
            else:
                failed = items
            raise BatchEmbeddingError(
                failures=[
                    BatchChunkFailure(tuple(failed), stage, RuntimeError("service unavailable"))
                ],
                total_items=len(items),
            )

    store = PartialStore(persists=True)
    warnings = []
    gen = SimpleNamespace(embed_failed_pages=0)

    async def go():
        async def page(page_id):
            return _page(page_id)

        run = _fake_run(store)
        run.gen = gen
        run.on_warning = warnings.append
        await _GenerationRun.run_level(
            run, [(pid, page(pid)) for pid in ("ok.py", "retry.py", "last.py")], level=2
        )

    asyncio.run(go())
    assert [[item[0] for item in batch] for batch in store.batches] == [
        ["ok.py", "retry.py", "last.py"],
        ["retry.py", "last.py"],
    ]
    assert gen.embed_failed_pages == failed_count
    if failed_count:
        assert len(warnings) == 1
        assert "last.py" in warnings[0]
        assert ("retry.py" in warnings[0]) == (failed_count == 2)
        assert "ok.py" not in warnings[0]
    else:
        assert warnings == []


def test_a_failed_embed_is_counted_on_the_generator() -> None:
    """Callers read the count to refuse calling semantic search healthy.

    A warning string alone left init and update exiting 0 with a semantic
    index that held none of the pages.
    """
    warnings: list[str] = []
    gen = SimpleNamespace(embed_failed_pages=0)

    async def _go():
        async def fresh():
            return _page("fresh.py")

        run = _fake_run(_FailingStore())
        run.gen = gen
        run.on_warning = warnings.append
        await _GenerationRun.run_level(run, [("p1", fresh())], level=2)

    asyncio.run(_go())

    assert gen.embed_failed_pages == 1
    assert warnings and "Embedding failed for 1 page(s)" in warnings[0]


def test_each_embed_batch_is_bracketed_for_the_display() -> None:
    """Embedding is its own step on screen: start before the batch, done after."""
    calls: list[tuple[int, bool]] = []

    async def _go():
        async def fresh():
            return _page("fresh.py")

        async def other():
            return _page("other.py")

        run = _fake_run(_RecordingStore(persists=False))
        run.on_embed = lambda count, finished: calls.append((count, finished))
        await _GenerationRun.run_level(run, [("p1", fresh()), ("p2", other())], level=2)

    asyncio.run(_go())
    assert calls == [(2, False), (2, True)]


def test_a_failed_embed_batch_is_never_reported_finished() -> None:
    calls: list[tuple[int, bool]] = []

    async def _go():
        async def fresh():
            return _page("fresh.py")

        run = _fake_run(_FailingStore())
        run.gen = SimpleNamespace(embed_failed_pages=0)
        run.on_warning = lambda _text: None
        run.on_embed = lambda count, finished: calls.append((count, finished))
        await _GenerationRun.run_level(run, [("p1", fresh())], level=2)

    asyncio.run(_go())
    assert calls == [(1, False)]


class _Phases:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def on_phase_start(self, phase, total):
        self.events.append(("start", phase, total))

    def on_item_done(self, phase):
        self.events.append(("item", phase))

    def on_phase_done(self, phase):
        self.events.append(("done", phase))

    def on_phase_failed(self, phase):
        self.events.append(("failed", phase))


class _Embedder:
    pass


def _display(store):
    from repowise.core.pipeline.phases.generation import _GenerationDisplay

    progress = _Phases()
    return progress, _GenerationDisplay(progress, store, None)


def test_embedding_shows_as_its_own_step_with_a_real_embedder() -> None:
    progress, display = _display(SimpleNamespace(_embedder=_Embedder()))
    display.on_embed(2, False)
    display.on_embed(2, True)
    display.close_embedding()
    assert progress.events == [
        ("start", "embedding", 2),
        ("item", "embedding"),
        ("item", "embedding"),
        ("done", "embedding"),
    ]


def test_a_failed_embed_closes_the_step_without_a_done_row() -> None:
    progress, display = _display(SimpleNamespace(_embedder=_Embedder()))
    display.on_embed(3, False)
    display.close_embedding()
    assert progress.events[-1] == ("failed", "embedding")


def test_the_keyless_embedder_gets_no_embedding_step() -> None:
    from repowise.core.providers.embedding import KeylessEmbedder

    progress, display = _display(SimpleNamespace(_embedder=KeylessEmbedder()))
    display.on_embed(2, False)
    display.on_embed(2, True)
    display.close_embedding()
    assert progress.events == []
