"""`repowise update` must retire the cycles a fixed engine no longer finds.

The engine fix for #1294 only changes what the in-memory graph says. Three
persisted artifacts had no path back to agreement with it on an incremental
update, so a user who upgraded and ran `update` would keep being served the
false cycles: the `scc_page` rows, the `graph_node_membership` rows behind the
Stats "largest cycle" record, and the `graph_edges` rows the health engine
rehydrates. These cover all three.
"""

from __future__ import annotations

import networkx as nx
import pytest

from repowise.core.generation.models import compute_page_id, scc_page_slug
from repowise.core.persistence import (
    batch_upsert_graph_node_membership,
    get_scc_members,
)
from repowise.core.persistence.models import GraphNodeMembership, Page
from repowise.core.pipeline.persist import sweep_absent_cycle_pages
from tests.unit.persistence.helpers import insert_repo, make_page_kwargs


@pytest.fixture
async def repo_id(async_session) -> str:
    repo = await insert_repo(async_session)
    return repo.id


class _FakeBuilder:
    """Minimal stand-in exposing only what the sweep reads."""

    def __init__(self, sccs: list[set[str]], graph: nx.DiGraph | None = None) -> None:
        self._sccs = sccs
        self._graph = graph if graph is not None else nx.DiGraph()

    def strongly_connected_components(self):
        return [frozenset(s) for s in self._sccs]

    def graph(self):
        return self._graph


async def _add_scc_page(async_session, repo_id: str, members: list[str]) -> str:
    from repowise.core.persistence.crud import upsert_page

    slug = scc_page_slug(sorted(members))
    await upsert_page(
        async_session,
        **make_page_kwargs(
            repo_id,
            page_id=compute_page_id("scc_page", slug),
            page_type="scc_page",
            target_path=slug,
            title="Circular Dependency",
        ),
    )
    await async_session.flush()
    return compute_page_id("scc_page", slug)


@pytest.mark.asyncio
class TestCyclePageSweep:
    @pytest.mark.parametrize(
        "pass_vector_store", [True, False], ids=["passed-store", "delete-only-open"]
    )
    @pytest.mark.parametrize("fail_delete", [False, True], ids=["success", "retry-debt"])
    async def test_incremental_sweep_removes_vectors_without_embedding(
        self, tmp_path, monkeypatch, pass_vector_store, fail_delete
    ) -> None:
        from sqlalchemy import select, text

        from repowise.core.persistence import (
            create_engine,
            create_session_factory,
            get_session,
            init_db,
        )
        from repowise.core.persistence.database import resolve_db_url
        from repowise.core.persistence.search import FullTextSearch
        from repowise.core.persistence.vector_store import LanceDBVectorStore
        from repowise.core.pipeline.cleanup_debt import load_cleanup_debt
        from repowise.core.pipeline.incremental import persist_incremental_index
        from repowise.core.providers.embedding.base import MockEmbedder

        (tmp_path / ".repowise").mkdir()
        engine = create_engine(resolve_db_url(tmp_path))
        store = LanceDBVectorStore(str(tmp_path / ".repowise" / "lancedb"), MockEmbedder())
        try:
            await init_db(engine)
            sf = create_session_factory(engine)
            async with get_session(sf) as session:
                repo = await insert_repo(session, name=tmp_path.name, local_path=str(tmp_path))
                ghost = await _add_scc_page(session, repo.id, ["gone/a.py", "gone/b.py"])
                live = await _add_scc_page(session, repo.id, ["live/a.py", "live/b.py"])

            fts = FullTextSearch(engine)
            await fts.ensure_index()
            for pid in (ghost, live):
                await fts.index(
                    pid,
                    "Circular Dependency",
                    "Mutual imports connect both modules into a circular dependency. " * 10,
                    summary="Mutual imports",
                    target_path=pid,
                )
            async with engine.connect() as conn:
                assert set(
                    (await conn.execute(text("SELECT page_id FROM page_fts"))).scalars()
                ) == {ghost, live}
            decision = "decision:kept"
            await store.embed_batch(
                [(pid, "Circular dependency evidence", {}) for pid in (ghost, live, decision)]
            )
            assert await store.list_page_ids() == {ghost, live, decision}
            if not pass_vector_store:
                await store.close()

            async def forbidden_embedding(*args, **kwargs):
                pytest.fail("Cycle cleanup must not embed")

            monkeypatch.setattr(MockEmbedder, "embed", forbidden_embedding)
            degraded: list[str] = []

            async def persist_once():
                await persist_incremental_index(
                    tmp_path,
                    _FakeBuilder([{"live/a.py", "live/b.py"}]),
                    {},
                    None,
                    None,
                    [],
                    parsed_files=[],
                    vector_store=store if pass_vector_store else None,
                    degraded=degraded,
                )

            if fail_delete:

                async def unavailable_delete(*args, **kwargs):
                    raise RuntimeError("vector delete unavailable")

                with monkeypatch.context() as failure:
                    failure.setattr(LanceDBVectorStore, "delete_many", unavailable_delete)
                    await persist_once()
                assert await store.list_page_ids() == {ghost, live, decision}
                assert load_cleanup_debt(tmp_path)["vectors"] == {ghost}
                assert "Tombstone vector removal: vector delete unavailable" in degraded
                degraded.clear()
            await persist_once()
            if not pass_vector_store:
                # The cleanup used a separate handle; read its committed version.
                await store.close()

            async with get_session(sf) as session:
                assert set((await session.execute(select(Page.id))).scalars()) == {live}
            async with engine.connect() as conn:
                assert set(
                    (await conn.execute(text("SELECT page_id FROM page_fts"))).scalars()
                ) == {live}
            assert await store.list_page_ids() == {live, decision}
            assert load_cleanup_debt(tmp_path)["vectors"] == set()
            assert not [entry for entry in degraded if entry.startswith("Tombstone vector")]
        finally:
            await store.close()
            await engine.dispose()

    async def test_page_for_a_vanished_cycle_is_deleted(self, async_session, repo_id) -> None:
        ghost = await _add_scc_page(async_session, repo_id, ["acl/acl.go", "acl/user.go"])
        # The rebuilt graph finds no cycle at all.
        swept = await sweep_absent_cycle_pages(async_session, repo_id, _FakeBuilder([]))
        assert swept == [ghost]
        remaining = (await async_session.execute(Page.__table__.select())).fetchall()
        assert not [r for r in remaining if r.page_type == "scc_page"]

    async def test_page_for_a_surviving_cycle_is_kept(self, async_session, repo_id) -> None:
        members = ["a.py", "b.py"]
        live = await _add_scc_page(async_session, repo_id, members)
        swept = await sweep_absent_cycle_pages(async_session, repo_id, _FakeBuilder([set(members)]))
        assert swept == []
        rows = (await async_session.execute(Page.__table__.select())).fetchall()
        assert [r.id for r in rows if r.page_type == "scc_page"] == [live]

    async def test_shrunken_cycle_retires_the_old_id(self, async_session, repo_id) -> None:
        # Membership is the page's identity, so a cycle that loses a member is
        # a different page: the old row must not linger as a duplicate.
        old = await _add_scc_page(async_session, repo_id, ["a.py", "b.py", "c.py"])
        swept = await sweep_absent_cycle_pages(
            async_session, repo_id, _FakeBuilder([{"a.py", "b.py"}])
        )
        assert swept == [old]

    async def test_missing_builder_is_a_no_op(self, async_session, repo_id) -> None:
        page = await _add_scc_page(async_session, repo_id, ["a.py", "b.py"])
        assert await sweep_absent_cycle_pages(async_session, repo_id, None) == []
        rows = (await async_session.execute(Page.__table__.select())).fetchall()
        assert [r.id for r in rows] == [page]


@pytest.mark.asyncio
class TestMembershipPrune:
    async def test_node_that_left_a_cycle_loses_its_row(self, async_session, repo_id) -> None:
        await batch_upsert_graph_node_membership(
            async_session,
            repo_id,
            {
                "a.go": {"node_type": "file", "scc_id": 0, "scc_size": 2},
                "b.go": {"node_type": "file", "scc_id": 0, "scc_size": 2},
            },
        )
        assert set((await get_scc_members(async_session, repo_id)).get(0, [])) == {"a.go", "b.go"}

        # Re-run after the fix: the cycle is gone, so the snapshot is empty.
        await batch_upsert_graph_node_membership(async_session, repo_id, {})
        rows = (
            await async_session.execute(
                GraphNodeMembership.__table__.select().where(
                    GraphNodeMembership.repository_id == repo_id
                )
            )
        ).fetchall()
        assert rows == []
        assert (await get_scc_members(async_session, repo_id)) == {}

    async def test_surviving_nodes_are_kept_and_updated(self, async_session, repo_id) -> None:
        await batch_upsert_graph_node_membership(
            async_session,
            repo_id,
            {
                "a.go": {"node_type": "file", "scc_id": 0, "scc_size": 3},
                "b.go": {"node_type": "file", "scc_id": 0, "scc_size": 3},
                "c.go": {"node_type": "file", "scc_id": 0, "scc_size": 3},
            },
        )
        await batch_upsert_graph_node_membership(
            async_session,
            repo_id,
            {
                "a.go": {"node_type": "file", "scc_id": 0, "scc_size": 2},
                "b.go": {"node_type": "file", "scc_id": 0, "scc_size": 2},
            },
        )
        assert set((await get_scc_members(async_session, repo_id)).get(0, [])) == {"a.go", "b.go"}
