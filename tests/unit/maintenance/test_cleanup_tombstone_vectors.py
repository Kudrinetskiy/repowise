"""Real-store safety boundary for the explicitly approved delete-only helper."""

from __future__ import annotations

import copy
import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from repowise.core.persistence.vector_store import LanceDBVectorStore
from repowise.core.providers.embedding.base import MockEmbedder

HELPER = (
    Path(__file__).resolve().parents[3]
    / "skills/maintain-repowise/scripts/cleanup_tombstone_vectors.py"
)


def helper():
    spec = importlib.util.spec_from_file_location("cleanup_tombstone_vectors", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
async def fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "live.py").write_text("print('live')\n")
    git(repo, "add", "live.py")
    git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=x@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    store_dir = repo / ".repowise"
    store_dir.mkdir()
    (store_dir / "state.json").write_text('{"last_docs_commit":"preserve"}\n')
    (store_dir / "config.yaml").write_text("embedder: ollama\n")
    db = store_dir / "wiki.db"
    with sqlite3.connect(db) as sql:
        sql.executescript("""
            CREATE TABLE repositories (id TEXT, local_path TEXT);
            CREATE TABLE wiki_pages (id TEXT PRIMARY KEY, repository_id TEXT,
                page_type TEXT, target_path TEXT, provider_name TEXT,
                freshness_status TEXT, content TEXT, digest TEXT, model_name TEXT,
                updated_at TEXT, input_tokens INTEGER, output_tokens INTEGER);
            CREATE TABLE decision_records (id TEXT, repository_id TEXT);
        """)
        sql.execute("INSERT INTO repositories VALUES ('repo', ?)", (str(repo),))
        for page_id, page_type, target, provider, status in [
            ("file_page:live.py", "file_page", "live.py", "template", "fresh"),
            ("module_page:project", "module_page", ".", "authored", "fresh"),
            ("file_page:gone'old.py", "file_page", "gone'old.py", "template", "tombstone"),
        ]:
            sql.execute(
                "INSERT INTO wiki_pages VALUES (?, 'repo', ?, ?, ?, ?, ?, ?, ?, ?, 7, 9)",
                (
                    page_id,
                    page_type,
                    target,
                    provider,
                    status,
                    "preserve prose",
                    "preserve digest",
                    "model",
                    "2020-01-01",
                ),
            )
        sql.execute("INSERT INTO decision_records VALUES ('keep', 'repo')")
    store = LanceDBVectorStore(str(store_dir / "lancedb"), MockEmbedder())
    ids = {"file_page:live.py", "module_page:project", "file_page:gone'old.py", "decision:keep"}
    # Three-wide vectors prove delete/list never reset a real store to mock's width (8).
    await store.upsert_vectors([(page_id, [1.0, 0.0, 0.0], {}) for page_id in sorted(ids)])
    await store.close()

    async def no_embed(*args, **kwargs):
        raise AssertionError("cleanup must never embed")

    monkeypatch.setattr(MockEmbedder, "embed", no_embed)
    return repo, db, ids


async def vector_rows(repo):
    import lancedb

    db = await lancedb.connect_async(str(repo / ".repowise/lancedb"))
    table = await db.open_table("wiki_pages")
    return {row["page_id"]: row for row in await table.query().to_list()}


@pytest.mark.parametrize("cohort_size", [1, 519])
async def test_exact_delete_preserves_models_decisions_state_source_and_vector_width(
    fixture, cohort_size
):
    repo, db, ids = fixture
    module = helper()
    approved = {"file_page:gone'old.py"}
    if cohort_size > 1:
        with sqlite3.connect(db) as sql:
            sql.executemany(
                "INSERT INTO wiki_pages SELECT ?, repository_id, page_type, ?, provider_name, "
                "freshness_status, content, digest, model_name, updated_at, input_tokens, "
                "output_tokens FROM wiki_pages WHERE id=?",
                (
                    (f"file_page:gone-{index}.py", f"gone-{index}.py", "file_page:gone'old.py")
                    for index in range(cohort_size - 1)
                ),
            )
        approved |= {f"file_page:gone-{index}.py" for index in range(cohort_size - 1)}
        store = LanceDBVectorStore(str(repo / ".repowise/lancedb"), MockEmbedder())
        await store.upsert_vectors([(page_id, [1.0, 0.0, 0.0], {}) for page_id in sorted(approved)])
        await store.close()
        ids |= approved
    before_vectors = await vector_rows(repo)
    before = {
        p: p.read_bytes()
        for p in [
            db,
            repo / "live.py",
            repo / ".git/index",
            repo / ".git/HEAD",
            repo / ".repowise/state.json",
            repo / ".repowise/config.yaml",
        ]
    }
    receipt = await module.preview(repo)
    assert receipt["candidate_ids"] == sorted(approved)
    result = await module.apply_receipt(repo, receipt)
    assert result["deleted_ids"] == sorted(approved)
    after = await vector_rows(repo)
    assert set(after) == ids - approved
    assert after == {key: value for key, value in before_vectors.items() if key in after}
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize(
    "problem",
    ["missing_sql", "model", "not_file", "live", "symlink", "head", "index", "outside", "empty"],
)
async def test_mixed_or_unverified_candidates_block_entire_preview(fixture, problem):
    repo, db, ids = fixture
    with sqlite3.connect(db) as sql:
        if problem == "missing_sql":
            sql.execute("DELETE FROM wiki_pages WHERE freshness_status='tombstone'")
        elif problem == "model":
            sql.execute(
                "UPDATE wiki_pages SET provider_name='authored' WHERE freshness_status='tombstone'"
            )
        elif problem == "not_file":
            sql.execute(
                "UPDATE wiki_pages SET page_type='module_page' WHERE freshness_status='tombstone'"
            )
        elif problem in {"outside", "empty", "head", "index"}:
            path = {
                "outside": "../outside.py",
                "empty": "",
                "head": "live.py",
                "index": "staged.py",
            }[problem]
            sql.execute(
                "UPDATE wiki_pages SET target_path=? WHERE freshness_status='tombstone'", (path,)
            )
    if problem == "live":
        (repo / "gone'old.py").write_text("new untracked file")
    elif problem == "symlink":
        (repo / "gone'old.py").symlink_to("missing-target")
    elif problem == "head":
        (repo / "live.py").unlink()
        git(repo, "rm", "--cached", "live.py")
    elif problem == "index":
        (repo / "staged.py").write_text("staged")
        git(repo, "add", "staged.py")
        (repo / "staged.py").unlink()
    with pytest.raises(ValueError):
        await helper().preview(repo)
    assert set(await vector_rows(repo)) == ids


@pytest.mark.parametrize(
    "change",
    [
        "tamper",
        "type_tamper",
        "state",
        "config",
        "head",
        "vectors",
        "candidate",
        "untracked",
        "wrong_repo",
    ],
)
async def test_apply_refuses_changed_receipt_or_state_before_any_delete(fixture, change, tmp_path):
    repo, db, ids = fixture
    module = helper()
    if change == "untracked":
        (repo / "untracked.py").write_text("original untracked body")
    receipt = await module.preview(repo)
    if change == "tamper":
        receipt = copy.deepcopy(receipt)
        receipt["candidate_ids"].append("module_page:project")
    elif change == "type_tamper":
        receipt["schema"] = True
    elif change == "state":
        (repo / ".repowise/state.json").write_text('{"changed":true}')
    elif change == "config":
        (repo / ".repowise/config.yaml").write_text("embedder: changed\n")
    elif change == "untracked":
        (repo / "untracked.py").write_text("different untracked body")
    elif change == "head":
        git(
            repo,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=x@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "new HEAD",
        )
    elif change == "candidate":
        with sqlite3.connect(db) as sql:
            sql.execute(
                "UPDATE wiki_pages SET content='changed' WHERE freshness_status='tombstone'"
            )
    elif change == "vectors":
        store = LanceDBVectorStore(str(repo / ".repowise/lancedb"), MockEmbedder())
        await store.upsert_vectors([("unexpected", [0.0, 1.0, 0.0], {})])
        await store.close()
        ids.add("unexpected")
    if change == "wrong_repo":
        repo = tmp_path / "wrong"
        repo.mkdir()
        git(repo, "init", "-q")
    with pytest.raises(ValueError):
        await module.apply_receipt(repo, receipt)
    original_repo = db.parent.parent
    assert set(await vector_rows(original_repo)) == ids


async def test_unknown_orphan_blocks_deleting_otherwise_valid_tombstone(fixture):
    repo, _, ids = fixture
    store = LanceDBVectorStore(str(repo / ".repowise/lancedb"), MockEmbedder())
    await store.upsert_vectors([("unknown-without-sql", [0.0, 1.0, 0.0], {})])
    await store.close()
    with pytest.raises(ValueError, match="lacks matching SQL"):
        await helper().preview(repo)
    assert set(await vector_rows(repo)) == ids | {"unknown-without-sql"}


@pytest.mark.parametrize("missing", ["wiki.db", "lancedb", "lancedb/wiki_pages.lance"])
async def test_absent_store_is_refused_without_creating_replacement(fixture, missing):
    repo, _, _ = fixture
    target = repo / ".repowise" / missing
    retained = target.with_name(target.name + ".retained")
    target.rename(retained)
    with pytest.raises(ValueError, match="Required existing"):
        await helper().preview(repo)
    assert not target.exists()
    assert retained.exists()


def test_snapshot_streams_large_prose_instead_of_retaining_wiki_bodies(fixture):
    import tracemalloc

    repo, db, _ = fixture
    body = "x" * (128 * 1024)
    with sqlite3.connect(db) as sql:
        sql.executemany(
            "INSERT INTO wiki_pages VALUES (?, 'repo', 'module_page', '.', 'authored', "
            "'fresh', ?, ?, 'model', '2020-01-01', 7, 9)",
            ((f"module_page:bulk-{index:03}", body, body) for index in range(96)),
        )
    module = helper()
    tracemalloc.start()
    try:
        _, pages, _ = module._snapshot(repo)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # 24 MiB of prose/digest must not accumulate in Python receipt planning.
    assert peak < 8 * 1024 * 1024
    assert len(pages) == 99
    assert all("content" not in row and "digest" not in row for row in pages.values())


def test_preview_cli_prints_one_json_receipt_only(fixture, monkeypatch, capsys):
    import sys

    repo, _, _ = fixture
    module = helper()
    monkeypatch.setattr(sys, "argv", [str(HELPER), str(repo), "--preview"])
    module.main()
    output = capsys.readouterr().out
    assert len(output.splitlines()) == 1
    assert json.loads(output)["candidate_ids"] == ["file_page:gone'old.py"]
