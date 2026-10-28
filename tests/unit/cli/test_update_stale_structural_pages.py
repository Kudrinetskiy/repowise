from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from repowise.cli.helpers import config_fingerprint
from repowise.cli.main import cli
from repowise.core.ingestion import AffectedPages

REPOWISE = str(Path(sys.executable).with_name("repowise"))
STALE_SENTINEL = "STALE STRUCTURAL PAGE SENTINEL"


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["REPOWISE_TELEMETRY_DISABLED"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _git(repo: Path, *args: str) -> None:
    result = _run(["git", *args], repo)
    assert result.returncode == 0, result.stdout + result.stderr


def _init_repo(base: Path, *, extra_files: dict[str, str] | None = None) -> Path:
    repo = base / "repo"
    repo.mkdir()
    (repo / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}'\n",
        encoding="utf-8",
    )
    for relative_path, content in (extra_files or {}).items():
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "-qm",
        "initial",
    )
    initialized = _run(
        [
            REPOWISE,
            "init",
            str(repo),
            "--no-prose",
            "--no-seed",
            "--embedder",
            "mock",
            "--no-editor-setup",
            "--no-claude-md",
            "--no-agents",
            "--no-codex",
            "--no-distill-hook",
            "--yes",
        ],
        repo,
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    return repo


def _mark_file_page_stale(repo: Path, target_path: str = "main.py") -> str:
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        row = database.execute(
            "SELECT id FROM wiki_pages WHERE page_type = 'file_page' AND target_path = ?",
            (target_path,),
        ).fetchone()
        assert row is not None, f"missing file page for {target_path}"
        page_id = str(row[0])
        database.execute(
            "UPDATE wiki_pages SET content = ?, freshness_status = 'stale' WHERE id = ?",
            (STALE_SENTINEL, page_id),
        )
        database.execute(
            "UPDATE page_fts SET content = ? WHERE page_id = ?",
            (STALE_SENTINEL, page_id),
        )
    return page_id


def _stale_file_pages(repo: Path) -> int:
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        row = database.execute(
            "SELECT COUNT(*) FROM wiki_pages "
            "WHERE page_type = 'file_page' AND freshness_status = 'stale'"
        ).fetchone()
    assert row is not None
    return int(row[0])


def _page_and_fts_content(repo: Path, page_id: str) -> tuple[str, str]:
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        page = database.execute(
            "SELECT content FROM wiki_pages WHERE id = ?", (page_id,)
        ).fetchone()
        fts = database.execute(
            "SELECT content FROM page_fts WHERE page_id = ?", (page_id,)
        ).fetchone()
    assert page is not None and fts is not None
    return str(page[0]), str(fts[0])


def _set_llm_docs_mode(repo: Path) -> None:
    state_path = repo / ".repowise" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "docs_mode": "llm",
            "provider": "codex_cli",
            "model": "codex_cli/gpt-5.6-luna",
        }
    )
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _stabilize_fixture(repo: Path) -> None:
    """Remove unrelated editor artifacts and baseline the current config."""
    shutil.rmtree(repo / ".vscode", ignore_errors=True)
    state_path = repo / ".repowise" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["config_fingerprint"] = config_fingerprint(repo)
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _init_two_file_repo(base: Path) -> Path:
    repo = _init_repo(
        base,
        extra_files={
            "consumer.py": (
                "from main import greet\n\n\ndef welcome() -> str:\n    return greet('World')\n"
            )
        },
    )
    _stabilize_fixture(repo)
    return repo


def test_stale_only_update_repairs_sql_and_fts_without_model_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    _set_llm_docs_mode(repo)
    page_id = _mark_file_page_stale(repo)

    def fail_provider(*_args, **_kwargs):
        raise AssertionError("model provider must not be resolved")

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.command.resolve_provider_or_prompt",
        fail_provider,
    )
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 0
    page_content, fts_content = _page_and_fts_content(repo, page_id)
    assert STALE_SENTINEL not in page_content
    assert STALE_SENTINEL not in fts_content
    assert not (repo / ".vscode").exists()


@pytest.mark.parametrize(
    ("docs_mode", "mode_flags", "preserve_docs_pointer", "change_generation_config"),
    [
        pytest.param("llm", ["--index-only"], True, False, id="llm-index-only"),
        pytest.param("llm", ["--no-docs"], True, False, id="llm-no-docs"),
        pytest.param("deterministic", ["--index-only"], True, True, id="deterministic-config"),
        pytest.param("deterministic", ["--no-docs"], True, False, id="deterministic-no-docs"),
        pytest.param("deterministic", [], False, False, id="normal-deterministic"),
    ],
)
def test_structural_refresh_respects_explicit_docs_pointer_opt_out(
    tmp_path: Path,
    monkeypatch,
    docs_mode: str,
    mode_flags: list[str],
    preserve_docs_pointer: bool,
    change_generation_config: bool,
) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    if docs_mode == "llm":
        _set_llm_docs_mode(repo)
    page_id = _mark_file_page_stale(repo)
    state_path = repo / ".repowise" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    old_docs_commit = state["last_sync_commit"]
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "--allow-empty",
        "-qm",
        "new head",
    )
    head = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    assert head != old_docs_commit
    state.update(
        last_sync_commit=head,
        last_docs_commit=old_docs_commit,
        renderer_fingerprint="previous-release-renderer",
    )
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        database.row_factory = sqlite3.Row
        prose = dict(
            database.execute("SELECT * FROM wiki_pages WHERE id = ?", (page_id,)).fetchone()
        )
        prose.update(
            id="module_page:preserved-prose",
            page_type="module_page",
            target_path="",
            content="Existing conceptual prose must survive an index refresh.",
            summary="Existing conceptual summary",
            digest="Existing conceptual digest",
            provider_name="mock",
            model_name="original-prose-model",
            input_tokens=123,
            output_tokens=45,
            cached_tokens=6,
            metadata_json="{}",
            freshness_status="fresh",
        )
        columns = ", ".join(prose)
        placeholders = ", ".join("?" for _ in prose)
        database.execute(
            f"INSERT INTO wiki_pages ({columns}) VALUES ({placeholders})", list(prose.values())
        )
    if change_generation_config:
        import yaml

        config_path = repo / ".repowise" / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["enable_onboarding"] = False
        config_path.write_text(yaml.safe_dump(config))

    def fail_provider(*_args, **_kwargs):
        raise AssertionError("structural-only refresh must not resolve a model provider")

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.command.resolve_provider_or_prompt", fail_provider
    )
    from contextlib import nullcontext

    monkeypatch.setattr(
        "repowise.core.analysis.communities._suppress_graspologic_output", nullcontext
    )
    monkeypatch.setenv("REPOWISE_SKIP_EDITOR_SETUP", "1")
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-workspace", "--no-agents", *mode_flags],
        catch_exceptions=True,
    )
    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 0
    page_content, fts_content = _page_and_fts_content(repo, page_id)
    assert STALE_SENTINEL not in page_content
    assert STALE_SENTINEL not in fts_content
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        database.row_factory = sqlite3.Row
        preserved = dict(
            database.execute("SELECT * FROM wiki_pages WHERE id = ?", (prose["id"],)).fetchone()
        )
        # Hierarchy numbering may reconcile independently of prose generation.
        for field in (
            "content",
            "summary",
            "digest",
            "metadata_json",
            "provider_name",
            "model_name",
            "created_at",
            "updated_at",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
        ):
            assert preserved[field] == prose[field]
    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated["last_sync_commit"] == head
    assert updated["renderer_fingerprint"] != "previous-release-renderer"
    assert updated["last_docs_commit"] == (old_docs_commit if preserve_docs_pointer else head)


def test_stale_page_is_refreshed_after_file_loses_all_symbols(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    page_id = _mark_file_page_stale(repo)
    (repo / "main.py").write_text("assert 1 + 1 == 2\n", encoding="utf-8")
    _git(repo, "add", "main.py")
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "-qm",
        "remove the last symbol",
    )

    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--index-only", "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 0
    page_content, fts_content = _page_and_fts_content(repo, page_id)
    assert STALE_SENTINEL not in page_content
    assert STALE_SENTINEL not in fts_content


def test_stale_file_page_refresh_bypasses_near_clone_dedupe(tmp_path: Path) -> None:
    repo = _init_repo(
        tmp_path,
        extra_files={
            "main.py": (
                "from alpha import feature_alpha\n"
                "from beta import feature_beta\n"
                "from gamma import feature_gamma\n\n"
                "def run() -> tuple[str, str, str]:\n"
                "    return feature_alpha(), feature_beta(), feature_gamma()\n"
            ),
            "alpha.py": "def feature_alpha() -> str:\n    return 'alpha'\n",
            "beta.py": "def feature_beta() -> str:\n    return 'beta'\n",
            "gamma.py": "def feature_gamma() -> str:\n    return 'gamma'\n",
        },
    )
    _stabilize_fixture(repo)
    page_id = _mark_file_page_stale(repo, "gamma.py")

    clone_content = "def feature() -> str:\n    return 'clone'\n"
    for name in ("alpha.py", "beta.py", "gamma.py"):
        (repo / name).write_text(clone_content, encoding="utf-8")
    (repo / "main.py").write_text(
        "from alpha import feature as alpha_feature\n"
        "from beta import feature as beta_feature\n"
        "from gamma import feature as gamma_feature\n\n"
        "def run() -> tuple[str, str, str]:\n"
        "    return alpha_feature(), beta_feature(), gamma_feature()\n",
        encoding="utf-8",
    )
    _git(repo, "add", "main.py", "alpha.py", "beta.py", "gamma.py")
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "-qm",
        "make test files near clones",
    )

    result = _run(
        [REPOWISE, "update", str(repo), "--index-only", "--no-agents"],
        repo,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert _stale_file_pages(repo) == 0
    page_content, fts_content = _page_and_fts_content(repo, page_id)
    assert STALE_SENTINEL not in page_content
    assert STALE_SENTINEL not in fts_content


def test_new_decay_only_file_page_is_refreshed_in_same_index_update(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _init_two_file_repo(tmp_path)
    (repo / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'Welcome, {name}'\n",
        encoding="utf-8",
    )
    _git(repo, "add", "main.py")
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "-qm",
        "change dependency",
    )
    monkeypatch.setattr(
        "repowise.core.ingestion.ChangeDetector.get_affected_pages",
        lambda *_args, **_kwargs: AffectedPages(
            regenerate=["main.py"],
            rename_patch=[],
            decay_only=["consumer.py"],
        ),
    )

    result = CliRunner().invoke(
        cli,
        [
            "update",
            str(repo),
            "--index-only",
            "--cascade-budget",
            "1",
            "--no-agents",
        ],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 0


def test_full_docs_update_refreshes_decay_only_page_structurally(tmp_path: Path) -> None:
    repo = _init_two_file_repo(tmp_path)
    _set_llm_docs_mode(repo)
    (repo / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'Welcome, {name}'\n",
        encoding="utf-8",
    )
    _git(repo, "add", "main.py")
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "-qm",
        "change dependency",
    )
    result = _run(
        [
            REPOWISE,
            "update",
            str(repo),
            "--provider",
            "mock",
            "--cascade-budget",
            "1",
            "--no-agents",
        ],
        repo,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert _stale_file_pages(repo) == 0


@pytest.mark.parametrize("page_type", ["file_page", "scc_page"])
def test_failed_stale_renderer_keeps_page_stale_and_reports_degraded(
    tmp_path: Path,
    monkeypatch,
    page_type: str,
) -> None:
    extra_files = (
        {
            "main.py": "from helper import help_me\ndef greet():\n    return help_me()\n",
            "helper.py": "from main import greet\ndef help_me():\n    return greet()\n",
        }
        if page_type == "scc_page"
        else None
    )
    repo = _init_repo(tmp_path, extra_files=extra_files)
    _stabilize_fixture(repo)
    if page_type == "file_page":
        page_id = _mark_file_page_stale(repo)
    else:
        _set_llm_docs_mode(repo)
        with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
            row = database.execute(
                "SELECT id FROM wiki_pages WHERE page_type = 'scc_page'"
            ).fetchone()
            assert row is not None, "fixture must produce a real cycle page"
            page_id = row[0]
            database.execute(
                "UPDATE wiki_pages SET freshness_status = 'stale' WHERE id = ?", (page_id,)
            )
    state_path = repo / ".repowise" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    old_docs_commit = state["last_sync_commit"]
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "--allow-empty",
        "-qm",
        "new head",
    )
    state["last_sync_commit"] = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    state["last_docs_commit"] = old_docs_commit
    state_path.write_text(json.dumps(state), encoding="utf-8")

    # Concurrent Leiden calls redirect process-global streams in upstream.
    # Keep the real graph algorithms, but isolate their console side effect
    # from Click's capture: this case owns failed-render state, not console IO.
    from contextlib import nullcontext

    monkeypatch.setattr(
        "repowise.core.analysis.communities._suppress_graspologic_output", nullcontext
    )

    def fail_renderer(**kwargs):
        kwargs["degraded"].append("Template page refresh: forced stale repair failure")
        return []

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.deterministic."
        + (
            "regenerate_deterministic_pages"
            if page_type == "file_page"
            else "regenerate_deterministic_page_ids"
        ),
        fail_renderer,
    )
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        assert database.execute(
            "SELECT freshness_status FROM wiki_pages WHERE id = ?", (page_id,)
        ).fetchone() == ("stale",)
    assert json.loads(state_path.read_text(encoding="utf-8"))["last_docs_commit"] == old_docs_commit
    assert "forced stale repair failure" in result.output


def test_failed_stale_persistence_keeps_page_stale_and_reports_degraded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    _mark_file_page_stale(repo)

    def fail_persistence(**_kwargs):
        raise RuntimeError("forced stale persistence failure")

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.deterministic.persist_deterministic_pages",
        fail_persistence,
    )
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 1
    assert "forced stale persistence failure" in result.output


def test_fts_failure_after_sql_upsert_rolls_page_back_to_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    _mark_file_page_stale(repo)

    def fail_fts(*_args, **_kwargs):
        raise RuntimeError("forced FTS persistence failure")

    monkeypatch.setattr("repowise.core.persistence.FullTextSearch.index_pages", fail_fts)
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 1
    assert "forced FTS persistence failure" in result.output


@pytest.mark.parametrize("failure_stage", ["creation", "embedding"])
def test_vector_store_failure_does_not_publish_page_as_fresh(
    tmp_path: Path,
    monkeypatch,
    failure_stage: str,
) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    _mark_file_page_stale(repo)
    # Select the configured-store branch without changing the config: a real
    # embedder edit now triggers the upstream automatic re-embedding upgrade.
    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.deterministic.deterministic_embedder_name",
        lambda _cfg: "test-real",
    )
    monkeypatch.setattr("repowise.cli.providers.build_embedder", lambda *_args: object())

    def fail_vector(*_args, **_kwargs):
        if failure_stage == "creation":
            raise RuntimeError("forced vector persistence failure")
        return FailingVectorStore()

    class FailingVectorStore:
        async def get_page_summaries_by_paths(self, _paths):
            return {}

        async def embed_batch(self, _items):
            raise RuntimeError("forced vector persistence failure")

    monkeypatch.setattr("repowise.cli.providers.build_vector_store", fail_vector)
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    # Actual write failures retain upstream's fatal semantic-index signal;
    # store creation failure is a degraded structural repair that can retry.
    assert (result.exit_code == 0) == (failure_stage == "creation"), result.output
    assert _stale_file_pages(repo) == 1
    assert "forced vector persistence failure" in result.output


def test_added_markdown_doc_becomes_searchable_file_page(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    marker = "S2FIELDPRESENTATIONCANONICAL"
    doc_path = "docs/_task/event-change-history/01-global-plan.md"
    doc = repo / doc_path
    doc.parent.mkdir(parents=True)
    long_prefix = "## Historical checkpoint\n\nArchived evidence line.\n\n" * 1_500
    doc.write_text(
        f"# Event Change History\n\n{long_prefix}\n{marker}\n",
        encoding="utf-8",
    )
    _git(repo, "add", doc_path)
    _git(
        repo,
        "-c",
        "user.name=RepoWise Test",
        "-c",
        "user.email=repowise-test@example.invalid",
        "commit",
        "-qm",
        "add canonical docs",
    )

    updated = _run(
        [REPOWISE, "update", str(repo), "--index-only", "--no-agents"],
        repo,
    )

    output = updated.stdout + updated.stderr
    assert updated.returncode == 0, output
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        row = database.execute(
            "SELECT content FROM wiki_pages WHERE page_type = 'file_page' AND target_path = ?",
            (doc_path,),
        ).fetchone()
        fts_count = database.execute(
            "SELECT COUNT(*) FROM page_fts WHERE page_fts MATCH ?",
            (marker,),
        ).fetchone()

    assert row is not None, output
    assert marker in str(row[0])
    assert fts_count is not None and int(fts_count[0]) >= 1


@pytest.mark.parametrize("page_type", ["file_page", "symbol_spotlight"])
@pytest.mark.parametrize("new_commit", [True, False], ids=["scheduled", "idle"])
def test_per_page_renderer_debt_is_repaired_then_idle_without_global_change(
    tmp_path: Path, monkeypatch, page_type: str, new_commit: bool
) -> None:
    from repowise.cli.commands.update_cmd.command import (
        _current_renderer_fingerprint,
        clear_update_queued,
        release_update_lock,
    )

    monkeypatch.setenv("REPOWISE_SKIP_EDITOR_SETUP", "1")
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    _set_llm_docs_mode(repo)
    state_path = repo / ".repowise/state.json"
    state = json.loads(state_path.read_text())
    global_key = _current_renderer_fingerprint(repo)
    state["renderer_fingerprint"] = global_key
    state_path.write_text(json.dumps(state))
    # Init runs in a subprocess; align this process with the per-test HOME key.
    from repowise.core.cache_seal import reset_key_cache_for_tests

    reset_key_cache_for_tests()
    old_key = "obsolete-per-page-renderer-key"
    with sqlite3.connect(repo / ".repowise/wiki.db") as db:
        db.row_factory = sqlite3.Row
        target = dict(
            db.execute(
                "SELECT * FROM wiki_pages WHERE page_type=? LIMIT 1", (page_type,)
            ).fetchone()
        )
        metadata = json.loads(target["metadata_json"])
        metadata["render_key"] = old_key
        db.execute(
            "UPDATE wiki_pages SET metadata_json=? WHERE id=?", (json.dumps(metadata), target["id"])
        )
        # One scenario also protects the idle scanner's exclusion and missing-source paths.
        extra_rows = {}
        for label, provider, freshness in [
            ("authored", "original-model", "fresh"),
            ("retired", "template", "tombstone"),
            ("missing", "template", "fresh"),
        ]:
            if label == "missing" and new_commit:
                continue
            row = {
                **target,
                "id": f"file_page:{label}.py",
                "page_type": "file_page",
                "target_path": f"{label}.py",
                "provider_name": provider,
                "freshness_status": freshness,
                "metadata_json": json.dumps(metadata),
            }
            if label == "authored":
                row.update(
                    content="Preserve model prose",
                    digest="Preserve model digest",
                    model_name="original-model",
                    input_tokens=17,
                    output_tokens=9,
                )
            db.execute(
                f"INSERT INTO wiki_pages ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                list(row.values()),
            )
            extra_rows[label] = row
    if new_commit:
        (repo / "other.py").write_text("def unrelated():\n    return 7\n")
        _git(repo, "add", "other.py")
        _git(
            repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "unrelated change wakes update",
        )

    def no_model(*_a, **_k):
        raise AssertionError("structural key repair must not resolve a model")

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.command.resolve_provider_or_prompt", no_model
    )
    args = ["update", str(repo), "--index-only", "--no-workspace", "--no-agents"]
    first = CliRunner().invoke(cli, args)
    assert first.exit_code == 0, first.output
    with sqlite3.connect(repo / ".repowise/wiki.db") as db:
        db.row_factory = sqlite3.Row
        repaired = dict(
            db.execute("SELECT * FROM wiki_pages WHERE id=?", (target["id"],)).fetchone()
        )
        assert json.loads(repaired["metadata_json"])["render_key"] != old_key, first.output
        assert repaired["freshness_status"] == "fresh"
        for label in extra_rows:
            row = dict(
                db.execute(
                    "SELECT * FROM wiki_pages WHERE id=?", (extra_rows[label]["id"],)
                ).fetchone()
            )
            if label == "authored":
                for field in [
                    "content",
                    "digest",
                    "model_name",
                    "provider_name",
                    "created_at",
                    "updated_at",
                    "input_tokens",
                    "output_tokens",
                ]:
                    assert row[field] == extra_rows[label][field]
                assert row["freshness_status"] == "fresh"
            else:
                assert row["freshness_status"] == "tombstone"
    release_update_lock(repo)
    clear_update_queued(repo)
    retry = CliRunner().invoke(cli, args)
    assert retry.exit_code == 0, retry.output
    assert "Already up to date" in retry.output
    updated = json.loads(state_path.read_text())
    assert updated.get("last_docs_commit") == state.get("last_docs_commit")
    assert updated["renderer_fingerprint"] == global_key
    # The idle check compares persisted ingestion subjects, not source-only WIP.
    before_wip = (repaired["updated_at"], json.loads(repaired["metadata_json"])["render_key"])
    (repo / "main.py").write_text("def unsaved_product_change():\n    return 99\n")
    wip = CliRunner().invoke(cli, args)
    assert wip.exit_code == 0, wip.output
    assert "Already up to date" in wip.output
    with sqlite3.connect(repo / ".repowise/wiki.db") as db:
        current = db.execute(
            "SELECT updated_at, metadata_json FROM wiki_pages WHERE id=?", (target["id"],)
        ).fetchone()
    assert (current[0], json.loads(current[1])["render_key"]) == before_wip
    (repo / "main.py").unlink()
    deletion_wip = CliRunner().invoke(cli, args)
    assert deletion_wip.exit_code == 0, deletion_wip.output
    assert "Already up to date" in deletion_wip.output
    with sqlite3.connect(repo / ".repowise/wiki.db") as db:
        assert db.execute(
            "SELECT freshness_status FROM wiki_pages WHERE id=?", (target["id"],)
        ).fetchone() == ("fresh",)


@pytest.mark.parametrize(
    "cache_state", ["corrupt", "oversize", "escape", "deleted-stale", "special"]
)
def test_idle_renderer_scan_reports_unverified_cache_without_reading_source(
    tmp_path: Path, monkeypatch, capsys, cache_state: str
) -> None:
    from repowise.cli.commands.update_cmd.command import _idle_stale_renderer_paths
    from repowise.core.cache_seal import reset_key_cache_for_tests

    repo = _init_repo(tmp_path)
    reset_key_cache_for_tests()
    cache = repo / ".repowise/parse_cache.pkl"
    if cache_state == "corrupt":
        cache.write_bytes(b"not an authenticated cache")
    elif cache_state == "oversize":
        with cache.open("r+b") as handle:
            handle.truncate(256 * 1024 * 1024 + 1)
    elif cache_state == "special":
        cache.unlink()
        os.mkfifo(cache)
    elif cache_state == "escape":
        # A source symlink must not be followed even with a valid signed subject.
        original = repo / "main.py"
        original.unlink()
        outside = tmp_path / "outside.py"
        outside.write_text("def never_read():\n    return 0\n")
        original.symlink_to(outside)
    else:
        with sqlite3.connect(repo / ".repowise/wiki.db") as db:
            db.execute(
                "UPDATE wiki_pages SET metadata_json=? WHERE page_type='file_page'",
                (json.dumps({"render_key": "obsolete"}),),
            )
        (repo / "main.py").unlink()
    if cache_state in {"oversize", "special"}:

        def forbidden_load(*_a, **_k):
            pytest.fail("oversize or special idle cache must not be opened or unpickled")

        monkeypatch.setattr("repowise.core.cache_seal.load_sealed_pickle", forbidden_load)

    def forbidden_source_read(self, *args, **kwargs):
        if self.suffix == ".py" and self.is_relative_to(tmp_path):
            pytest.fail("idle renderer check must not read live source bytes")
        return original_open(self, *args, **kwargs)

    original_open = Path.open
    monkeypatch.setattr(Path, "open", forbidden_source_read)

    assert _idle_stale_renderer_paths(repo) == []
    output = capsys.readouterr().out
    if cache_state == "oversize":
        assert "256 MiB idle-check limit" in output
    elif cache_state == "special":
        assert "not a confined regular cache" in output
    elif cache_state == "corrupt":
        assert "Could not check idle structural render keys" in output
    else:
        assert "no safe indexed subject" in output


def test_scoped_repair_refreshes_existing_spotlight_outside_subset_rank_only(
    tmp_path: Path, monkeypatch
) -> None:
    from repowise.cli.commands.update_cmd.command import clear_update_queued, release_update_lock
    from repowise.core.cache_seal import reset_key_cache_for_tests

    def functions(first: int, stop: int) -> str:
        return "\n".join(
            f"def symbol_{i:03d}(value):\n    return value + {i}\n" for i in range(first, stop)
        )

    monkeypatch.setenv("REPOWISE_SKIP_EDITOR_SETUP", "1")
    repo = _init_repo(
        tmp_path,
        extra_files={
            "main.py": functions(0, 20),
            "zother.py": functions(20, 200),
        },
    )
    _stabilize_fixture(repo)
    _set_llm_docs_mode(repo)
    reset_key_cache_for_tests()
    state_path = repo / ".repowise/state.json"
    state = json.loads(state_path.read_text())
    target_id = "symbol_spotlight:main.py::symbol_019"
    model_id = "symbol_spotlight:main.py::symbol_016"
    tombstone_id = "symbol_spotlight:main.py::symbol_017"
    removed_id = "symbol_spotlight:main.py::removed_symbol"
    jobs_dir = repo / ".repowise/jobs"
    checkpoints_before = {p.name: p.read_bytes() for p in jobs_dir.glob("*.json")}
    with sqlite3.connect(repo / ".repowise/wiki.db") as db:
        db.row_factory = sqlite3.Row
        target = dict(db.execute("SELECT * FROM wiki_pages WHERE id=?", (target_id,)).fetchone())
        db.execute(
            "UPDATE wiki_pages SET content=?,metadata_json=? WHERE id=?",
            ("Obsolete retained spotlight body", json.dumps({"render_key": "old-key"}), target_id),
        )
        db.execute(
            "UPDATE wiki_pages SET provider_name='original-model', model_name='kept-model', "
            "content='Preserved model spotlight',digest='Preserved digest' WHERE id=?",
            (model_id,),
        )
        model = dict(db.execute("SELECT * FROM wiki_pages WHERE id=?", (model_id,)).fetchone())
        db.execute("UPDATE wiki_pages SET freshness_status='tombstone' WHERE id=?", (tombstone_id,))
        removed = {**target, "id": removed_id, "target_path": "main.py::removed_symbol"}
        db.execute(
            f"INSERT INTO wiki_pages ({', '.join(removed)}) VALUES ({', '.join('?' for _ in removed)})",
            list(removed.values()),
        )
    # The new symbol is a valid current candidate, but was never persisted and
    # is below this one-file render's 10% slice. It must not be force-created.
    (repo / "main.py").write_text(functions(0, 21))
    _git(repo, "add", "main.py")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "change the affected subset",
    )

    def no_model(*_a, **_k):
        raise AssertionError("structural repair must not resolve a model")

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.command.resolve_provider_or_prompt", no_model
    )
    args = ["update", str(repo), "--index-only", "--no-workspace", "--no-agents"]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    # This internal structural renderer has no JobSystem; unlike public
    # generation it must not emit an unaccounted file checkpoint.
    assert {p.name: p.read_bytes() for p in jobs_dir.glob("*.json")} == checkpoints_before
    with sqlite3.connect(repo / ".repowise/wiki.db") as db:
        db.row_factory = sqlite3.Row
        repaired = dict(db.execute("SELECT * FROM wiki_pages WHERE id=?", (target_id,)).fetchone())
        assert json.loads(repaired["metadata_json"])["render_key"] != "old-key"
        assert repaired["content"] != "Obsolete retained spotlight body"
        assert repaired["freshness_status"] == "fresh"
        assert (
            db.execute(
                "SELECT id FROM wiki_pages WHERE id=?", ("symbol_spotlight:main.py::symbol_020",)
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "SELECT freshness_status FROM wiki_pages WHERE id=?", (tombstone_id,)
            ).fetchone()[0]
            == "tombstone"
        )
        assert db.execute("SELECT id FROM wiki_pages WHERE id=?", (removed_id,)).fetchone() is None
        preserved = dict(db.execute("SELECT * FROM wiki_pages WHERE id=?", (model_id,)).fetchone())
        for field in [
            "content",
            "digest",
            "model_name",
            "provider_name",
            "created_at",
            "updated_at",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
        ]:
            assert preserved[field] == model[field]
    release_update_lock(repo)
    clear_update_queued(repo)
    retry = CliRunner().invoke(cli, args)
    assert retry.exit_code == 0, retry.output
    assert "Already up to date" in retry.output
    assert json.loads(state_path.read_text()).get("last_docs_commit") == state.get(
        "last_docs_commit"
    )
