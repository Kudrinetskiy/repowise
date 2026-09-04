from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

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
    repo = base / "repo"
    repo.mkdir()
    (repo / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}'\n",
        encoding="utf-8",
    )
    (repo / "consumer.py").write_text(
        "from main import greet\n\n\ndef welcome() -> str:\n    return greet('World')\n",
        encoding="utf-8",
    )
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
    assert "Re-rendered" in result.output
    assert not (repo / ".vscode").exists()


def test_stale_page_is_refreshed_after_file_loses_all_symbols(tmp_path: Path) -> None:
    repo = _init_repo(
        tmp_path,
        extra_files={"test_feature.py": "def test_feature() -> None:\n    assert True\n"},
    )
    page_id = _mark_file_page_stale(repo, "test_feature.py")
    (repo / "test_feature.py").write_text("assert 1 + 1 == 2\n", encoding="utf-8")
    _git(repo, "add", "test_feature.py")
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


def test_failed_stale_renderer_keeps_page_stale_and_reports_degraded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    _mark_file_page_stale(repo)

    def fail_renderer(**kwargs):
        kwargs["degraded"].append("Template page refresh: forced stale repair failure")
        return []

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.deterministic.regenerate_deterministic_pages",
        fail_renderer,
    )
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 1
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

    monkeypatch.setattr("repowise.core.persistence.FullTextSearch.index", fail_fts)
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
    assert _stale_file_pages(repo) == 1
    assert "forced FTS persistence failure" in result.output


def test_vector_store_failure_does_not_publish_page_as_fresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _init_repo(tmp_path)
    _stabilize_fixture(repo)
    _mark_file_page_stale(repo)
    config_path = repo / ".repowise" / "config.yaml"
    config_text = config_path.read_text(encoding="utf-8")
    assert "embedder: mock" in config_text
    config_path.write_text(
        config_text.replace("embedder: mock", "embedder: ollama"),
        encoding="utf-8",
    )

    def fail_vector(*_args, **_kwargs):
        raise RuntimeError("forced vector persistence failure")

    monkeypatch.setattr("repowise.cli.providers.build_vector_store", fail_vector)
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--no-agents"],
        catch_exceptions=True,
    )

    assert result.exit_code == 0, result.output
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
