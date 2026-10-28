"""End-to-end ``repowise update`` on a real fixture repo.

The test that would have caught #669: a real (index-only) full pipeline run
seeds wiki.db, a new commit lands, and one CliRunner ``update`` invocation
must refresh every index layer — graph nodes, health metrics, the knowledge
graph rows AND the exported knowledge-graph.json, the DB head_commit stamp,
and state.json — not just the subset the incremental path happened to touch.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from sqlalchemy import select

from repowise.cli.main import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    return result.stdout.strip()


def _git_commit_dated(repo: Path, message: str, date: str) -> None:
    """Commit already-staged changes with a fixed author/committer date, so
    decay-window tests can advance the repo's anchor deterministically."""
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(
        ["git", "commit", "-m", message], cwd=str(repo), env=env, capture_output=True, text=True
    )


async def _git_metadata(repo: Path, file_path: str) -> dict:
    """Read one file's persisted git_metadata row as a dict."""
    from repowise.core.persistence import create_engine, create_session_factory, get_session
    from repowise.core.persistence.database import resolve_db_url
    from repowise.core.persistence.models import GitMetadata

    engine = create_engine(resolve_db_url(repo))
    try:
        sf = create_session_factory(engine)
        async with get_session(sf) as session:
            row = (
                (
                    await session.execute(
                        select(GitMetadata).where(GitMetadata.file_path == file_path)
                    )
                )
                .scalars()
                .first()
            )
            return {
                "temporal_hotspot_score": row.temporal_hotspot_score,
                "commit_count_90d": row.commit_count_90d,
                "prior_defect_count": row.prior_defect_count,
            }
    finally:
        await engine.dispose()


def _make_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "a.py").write_text("def alpha():\n    return 1\n")
    (repo / "b.py").write_text("from a import alpha\n\n\ndef beta():\n    return alpha() + 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _index_full(repo: Path) -> None:
    """Real index-only init: full pipeline + persistence + KG artifact."""
    from repowise.core.pipeline.full_index import index_repo_full

    asyncio.run(index_repo_full(repo))


async def _db_snapshot(repo: Path) -> dict:
    """Read the layers the update must keep fresh from wiki.db."""
    from repowise.core.persistence import (
        create_engine,
        create_session_factory,
        get_session,
    )
    from repowise.core.persistence.database import resolve_db_url
    from repowise.core.persistence.models import (
        GraphNode,
        HealthFileMetric,
        KnowledgeGraphLayer,
        Repository,
    )

    engine = create_engine(resolve_db_url(repo))
    try:
        sf = create_session_factory(engine)
        async with get_session(sf) as session:
            repo_row = (await session.execute(select(Repository))).scalars().first()
            graph_node_ids = {
                n.node_id for n in (await session.execute(select(GraphNode))).scalars()
            }
            health_paths = {
                m.file_path for m in (await session.execute(select(HealthFileMetric))).scalars()
            }
            kg_layer_count = len(
                list((await session.execute(select(KnowledgeGraphLayer))).scalars())
            )
            return {
                "head_commit": repo_row.head_commit if repo_row else None,
                "graph_node_ids": graph_node_ids,
                "health_paths": health_paths,
                "kg_layer_count": kg_layer_count,
            }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


def test_update_refreshes_every_index_layer(tmp_path: Path) -> None:
    repo = _make_git_repo(tmp_path)
    _index_full(repo)

    base = _git(repo, "rev-parse", "HEAD")
    from repowise.cli.helpers import save_state

    save_state(repo, {"last_sync_commit": base, "docs_enabled": False})

    kg_path = repo / ".repowise" / "knowledge-graph.json"
    assert kg_path.is_file(), "init must export the KG artifact"
    assert "c.py" not in kg_path.read_text(encoding="utf-8")

    # A new file changes the graph shape, so every layer must move.
    (repo / "c.py").write_text("from b import beta\n\n\ndef gamma():\n    return beta() * 2\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add c.py")
    new_head = _git(repo, "rev-parse", "HEAD")

    result = CliRunner().invoke(cli, ["update", str(repo), "--no-workspace"])
    assert result.exit_code == 0, result.output

    # state.json advanced.
    state = json.loads((repo / ".repowise" / "state.json").read_text(encoding="utf-8"))
    assert state["last_sync_commit"] == new_head

    snap = asyncio.run(_db_snapshot(repo))
    # DB freshness stamp (the /repos + MCP _meta signal) matches HEAD.
    assert snap["head_commit"] == new_head
    # Graph rows include the new file.
    assert "c.py" in snap["graph_node_ids"]
    # Health metrics were computed for the new file.
    assert "c.py" in snap["health_paths"]
    # KG rows exist (layers persisted by the refresh, not just at init).
    assert snap["kg_layer_count"] >= 1

    # The exported artifact was rewritten for the new graph shape (#669:
    # this file used to stay frozen at init forever), and state.json carries
    # the refreshed fingerprint that gates the next rebuild.
    kg_after = json.loads(kg_path.read_text(encoding="utf-8"))
    assert any("c.py" in (n.get("filePath") or n.get("id") or "") for n in kg_after["nodes"])
    assert state.get("knowledge_graph", {}).get("fingerprint")


@pytest.mark.parametrize("route", ["single", "workspace", "selected", "workspace-docs"])
def test_unchanged_head_update_retries_failed_swept_vector_without_embedding(
    tmp_path: Path, monkeypatch, route: str
) -> None:
    """A failed SCC deletion must not disappear behind the next CLI no-op."""
    import sqlite3

    from repowise.cli.helpers import save_state
    from repowise.core.persistence.vector_store import LanceDBVectorStore
    from repowise.core.pipeline.cleanup_debt import load_cleanup_debt
    from repowise.core.providers.embedding.base import MockEmbedder

    monkeypatch.setenv("REPOWISE_EMBEDDER", "mock")
    monkeypatch.setenv("REPOWISE_SKIP_EDITOR_SETUP", "1")
    monkeypatch.setenv("REPOWISE_TELEMETRY_DISABLED", "1")
    repo = _make_git_repo(tmp_path)
    _index_full(repo)
    base = _git(repo, "rev-parse", "HEAD")
    save_state(repo, {"last_sync_commit": base, "last_docs_commit": base, "docs_enabled": False})
    db_path = repo / ".repowise/wiki.db"
    cycle_ids = {"scc_page:obsolete-cycle"}

    async def seed_prior_cycle():
        from repowise.core.persistence import create_engine, create_session_factory, get_session
        from repowise.core.persistence.crud import upsert_page
        from repowise.core.persistence.database import resolve_db_url
        from repowise.core.persistence.models import Repository
        from repowise.core.persistence.search import FullTextSearch
        from tests.unit.persistence.helpers import make_page_kwargs

        engine = create_engine(resolve_db_url(repo))
        store = LanceDBVectorStore(str(repo / ".repowise/lancedb"), MockEmbedder())
        try:
            async with get_session(create_session_factory(engine)) as session:
                stored_repo = (await session.execute(select(Repository))).scalar_one()
                await upsert_page(
                    session,
                    **make_page_kwargs(
                        stored_repo.id,
                        page_id="scc_page:obsolete-cycle",
                        page_type="scc_page",
                        target_path="obsolete-cycle",
                        title="Prior indexed cycle no longer present in the graph",
                    ),
                )
            fts = FullTextSearch(engine)
            await fts.ensure_index()
            await fts.index(
                "scc_page:obsolete-cycle",
                "Prior cycle",
                "Prior cycle evidence",
                summary="Prior cycle",
                target_path="obsolete-cycle",
            )
            await store.embed_batch([("scc_page:obsolete-cycle", "Prior cycle evidence", {})])
        finally:
            await store.close()
            await engine.dispose()

    asyncio.run(seed_prior_cycle())

    async def vector_ids():
        store = LanceDBVectorStore(str(repo / ".repowise/lancedb"), embedder=MockEmbedder())
        try:
            return set(await store.list_page_ids())
        finally:
            await store.close()

    assert cycle_ids <= asyncio.run(vector_ids())
    (repo / "b.py").write_text("def beta():\n    return 2\n")
    _git(repo, "add", "b.py")
    _git(repo, "commit", "-m", "break dependency cycle")

    original_delete = LanceDBVectorStore.delete_many

    async def unavailable_cycle_delete(self, ids):
        if cycle_ids.intersection(ids):
            raise OSError("fixture vector deletion unavailable")
        return await original_delete(self, ids)

    args = ["update", str(repo), "--no-workspace", "--no-agents", "--index-only"]
    with monkeypatch.context() as failure:
        failure.setattr(LanceDBVectorStore, "delete_many", unavailable_cycle_delete)
        first = CliRunner().invoke(cli, args)
    # Separate real CLI invocations exit between runs; CliRunner shares this
    # process, so perform the native atexit lock cleanup at that boundary.
    from repowise.cli.helpers import release_update_lock

    release_update_lock(repo)
    assert load_cleanup_debt(repo)["vectors"] == cycle_ids, first.output
    assert cycle_ids <= asyncio.run(vector_ids())
    with sqlite3.connect(db_path) as db:
        assert not list(db.execute("SELECT id FROM wiki_pages WHERE page_type='scc_page'"))
    state_before = json.loads((repo / ".repowise/state.json").read_text())
    assert state_before["last_sync_commit"] == _git(repo, "rev-parse", "HEAD")

    def forbidden_generation(*args, **kwargs):
        raise AssertionError("idle cleanup must not regenerate or embed")

    from repowise.cli.commands.update_cmd import command as update_command
    from repowise.core.workspace.update import repo as workspace_repo

    monkeypatch.setattr(update_command, "_rebuild_index", forbidden_generation)
    monkeypatch.setattr(workspace_repo, "_full_index_update", forbidden_generation)
    monkeypatch.setattr(workspace_repo, "_incremental_repo_update", forbidden_generation)
    monkeypatch.setattr(MockEmbedder, "embed", forbidden_generation)
    second_args = args
    sibling = None
    if route != "single":
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        members = [{"path": str(repo), "alias": "app", "is_primary": True}]
        if route == "selected":
            sibling = _make_git_repo(tmp_path / "neighbor")
            members.append({"path": str(sibling), "alias": "neighbor"})
        (workspace / ".repowise-workspace.yaml").write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_repo": "app",
                    "repos": members,
                }
            )
        )
        second_args = ["update", str(workspace), "--no-agents"]
        second_args += ["--repo", "app"] if route == "selected" else ["--workspace"]
        second_args += ["--docs"] if route == "workspace-docs" else ["--index-only"]
    ledger = repo / ".repowise/cleanup-debt.json"
    pending_before = ledger.read_bytes()
    preview = CliRunner().invoke(cli, [*second_args, "--dry-run"])
    assert preview.exit_code == 0, preview.output
    assert ledger.read_bytes() == pending_before
    assert cycle_ids <= asyncio.run(vector_ids())

    with monkeypatch.context() as failure:
        failure.setattr(LanceDBVectorStore, "delete_many", unavailable_cycle_delete)
        failed_retry = CliRunner().invoke(cli, second_args)
    assert failed_retry.exit_code != 0, failed_retry.output
    assert "fixture vector deletion unavailable" in failed_retry.output
    assert ledger.read_bytes() == pending_before
    assert cycle_ids <= asyncio.run(vector_ids())
    release_update_lock(repo)

    from repowise.cli.helpers import try_acquire_update_lock

    assert try_acquire_update_lock(repo, state_before["last_sync_commit"]) is None
    try:
        deferred = CliRunner().invoke(cli, second_args)
        assert deferred.exit_code == 0, deferred.output
        assert ledger.read_bytes() == pending_before
        assert cycle_ids <= asyncio.run(vector_ids())
    finally:
        release_update_lock(repo)
    second = CliRunner().invoke(cli, second_args)
    assert second.exit_code == 0, second.output
    assert not cycle_ids.intersection(asyncio.run(vector_ids())), second.output
    assert not load_cleanup_debt(repo)["vectors"]
    state_after = json.loads((repo / ".repowise/state.json").read_text())
    assert state_after["last_sync_commit"] == state_before["last_sync_commit"]
    assert state_after["last_docs_commit"] == state_before["last_docs_commit"]
    assert first.exit_code != 0, "persistent cleanup failure must not report CLI success"
    if sibling is not None:
        assert not (sibling / ".repowise").exists(), "selected cleanup must not index its sibling"


def test_only_indexing_moves_the_stored_commit(tmp_path: Path) -> None:
    """A full index and an update stamp HEAD; a decision recorded between them does not."""
    repo = _make_git_repo(tmp_path)
    _index_full(repo)
    base = _git(repo, "rev-parse", "HEAD")
    assert asyncio.run(_db_snapshot(repo))["head_commit"] == base

    from repowise.cli.helpers import save_state

    save_state(repo, {"last_sync_commit": base, "docs_enabled": False})
    (repo / "c.py").write_text("def gamma():\n    return 3\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add c.py")
    new_head = _git(repo, "rev-parse", "HEAD")

    added = CliRunner().invoke(
        cli, ["decision", "add", "--title", "T", "--decision", "D", str(repo)], input=""
    )
    assert added.exit_code == 0, added.output
    assert asyncio.run(_db_snapshot(repo))["head_commit"] == base

    result = CliRunner().invoke(cli, ["update", str(repo), "--no-workspace"])
    assert result.exit_code == 0, result.output
    assert asyncio.run(_db_snapshot(repo))["head_commit"] == new_head


def test_update_recovers_idle_file_decayed_health(tmp_path: Path, monkeypatch) -> None:
    """#728: an idle file's time-decayed history must recover on a plain git
    update. a.py churns hard, then only b.py changes six months later — a.py is
    never touched, yet its decayed hotspot score must shrink and the periodic
    full re-score must fire (stamping ``last_full_rescore_at``)."""
    # Anchor windows/decay to the repo's newest commit so the six-month gap is
    # deterministic rather than measured against wall clock.
    monkeypatch.setenv("REPOWISE_GIT_WINDOW_ANCHOR", "head")

    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    for i in range(4):
        (repo / "a.py").write_text("x = 1\n" * (i + 5))
        _git(repo, "add", ".")
        _git_commit_dated(repo, f"churn a {i}", "2024-01-01T00:00:00")
    (repo / "b.py").write_text("y = 0\n")
    _git(repo, "add", ".")
    _git_commit_dated(repo, "add b", "2024-01-02T00:00:00")

    _index_full(repo)
    base = _git(repo, "rev-parse", "HEAD")
    before = asyncio.run(_git_metadata(repo, "a.py"))
    assert before["temporal_hotspot_score"] > 0.0

    from repowise.cli.helpers import save_state

    save_state(repo, {"last_sync_commit": base, "docs_enabled": False})

    # Six months later, only b.py changes. a.py is idle.
    for i in range(3):
        (repo / "b.py").write_text(f"y = {i + 1}\n")
        _git(repo, "add", ".")
        _git_commit_dated(repo, f"b only {i}", "2024-07-01T00:00:00")

    result = CliRunner().invoke(cli, ["update", str(repo), "--no-workspace"])
    assert result.exit_code == 0, result.output

    after = asyncio.run(_git_metadata(repo, "a.py"))
    # The idle file's decayed hotspot score recovered (shrank) even though no
    # commit touched it — the ratchet #728 reported is gone.
    assert after["temporal_hotspot_score"] < before["temporal_hotspot_score"]

    # The periodic full health re-score fired (no prior stamp → due) and was
    # anchored to the repo's HEAD timestamp.
    state = json.loads((repo / ".repowise" / "state.json").read_text(encoding="utf-8"))
    assert isinstance(state.get("last_full_rescore_at"), (int, float))


def test_update_degrades_visibly_when_a_step_fails(tmp_path: Path, monkeypatch) -> None:
    """A failing best-effort persist step must surface in the degraded list
    (exit 0, warning block rendered) instead of being silently swallowed."""
    repo = _make_git_repo(tmp_path)
    _index_full(repo)

    base = _git(repo, "rev-parse", "HEAD")
    from repowise.cli.helpers import save_state

    save_state(repo, {"last_sync_commit": base, "docs_enabled": False})

    (repo / "c.py").write_text("def gamma():\n    return 3\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add c.py")

    import repowise.core.pipeline.persist as persist_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("graph nodes exploded")

    monkeypatch.setattr(persist_mod, "persist_graph_nodes", _boom)

    result = CliRunner().invoke(cli, ["update", str(repo), "--no-workspace"])

    assert result.exit_code == 0, result.output
    assert "degraded step(s)" in result.output
    assert "Graph nodes persist" in result.output


def test_a_pull_during_the_update_leaves_both_stamps_on_one_commit(
    tmp_path: Path, monkeypatch
) -> None:
    """state.json and the repository row name the head the update started from,
    even when HEAD moves while it runs (a pull or commit mid-update)."""
    repo = _make_git_repo(tmp_path)
    _index_full(repo)
    from repowise.cli.helpers import save_state

    save_state(repo, {"last_sync_commit": _git(repo, "rev-parse", "HEAD"), "docs_enabled": False})
    (repo / "c.py").write_text("def gamma():\n    return 3\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "add c.py")
    started_at = _git(repo, "rev-parse", "HEAD")

    import repowise.core.pipeline.incremental as incremental_mod

    persist = incremental_mod.persist_incremental_index

    async def _pull_then_persist(*args, **kwargs):
        (repo / "d.py").write_text("def delta():\n    return 4\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "landed mid-update")
        return await persist(*args, **kwargs)

    monkeypatch.setattr(incremental_mod, "persist_incremental_index", _pull_then_persist)

    result = CliRunner().invoke(cli, ["update", str(repo), "--no-workspace"])
    assert result.exit_code == 0, result.output
    assert _git(repo, "rev-parse", "HEAD") != started_at

    state = json.loads((repo / ".repowise" / "state.json").read_text(encoding="utf-8"))
    assert state["last_sync_commit"] == started_at
    assert asyncio.run(_db_snapshot(repo))["head_commit"] == started_at
