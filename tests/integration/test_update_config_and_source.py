from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from repowise.cli.main import cli

REPOWISE = str(Path(sys.executable).with_name("repowise"))


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


def _init_repo(base: Path) -> Path:
    repo = base / "repo"
    repo.mkdir()
    (repo / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}'\n",
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
    return repo


def _change_source_and_config(repo: Path) -> None:
    (repo / "main.py").write_text(
        "def farewell(name: str) -> str:\n    return f'Goodbye, {name}'\n",
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
        "change source",
    )
    (repo / ".repowise" / "health-rules.json").write_text(
        '{"disabled_biomarkers": ["ungoverned_hotspot"]}\n',
        encoding="utf-8",
    )


def _state(repo: Path) -> dict:
    return json.loads((repo / ".repowise" / "state.json").read_text(encoding="utf-8"))


def _file_page(repo: Path) -> str:
    with sqlite3.connect(repo / ".repowise" / "wiki.db") as database:
        row = database.execute(
            "SELECT content FROM wiki_pages "
            "WHERE page_type = 'file_page' AND target_path = 'main.py'"
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_config_and_source_change_continues_into_page_update(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert "greet" in _file_page(repo)
    _change_source_and_config(repo)

    updated = _run(
        [REPOWISE, "update", str(repo), "--index-only", "--no-agents"],
        repo,
    )

    output = updated.stdout + updated.stderr
    assert updated.returncode == 0, output
    assert "Config-triggered health re-score complete" in output
    assert "Re-rendered" in output
    assert "farewell" in _file_page(repo)


def test_config_and_source_dry_run_shows_both_stages_without_state_change(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    before = _state(repo)
    _change_source_and_config(repo)

    result = _run(
        [
            REPOWISE,
            "update",
            str(repo),
            "--index-only",
            "--no-agents",
            "--dry-run",
        ],
        repo,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "health would be re-scored" in output
    assert "Pages to regenerate" in output
    assert "Dry run — no pages regenerated" in output
    assert _state(repo) == before


def test_config_only_rescore_advances_only_fingerprint(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    before = _state(repo)
    (repo / ".repowise" / "health-rules.json").write_text(
        '{"disabled_biomarkers": ["ungoverned_hotspot"]}\n',
        encoding="utf-8",
    )

    result = _run(
        [REPOWISE, "update", str(repo), "--index-only", "--no-agents"],
        repo,
    )

    output = result.stdout + result.stderr
    after = _state(repo)
    assert result.returncode == 0, output
    assert "Config-triggered health re-score complete" in output
    assert "Pages to regenerate" not in output
    assert after["last_sync_commit"] == before["last_sync_commit"]
    assert after.get("last_docs_commit") == before.get("last_docs_commit")
    assert after["config_fingerprint"] != before["config_fingerprint"]


def test_failure_after_rescore_does_not_advance_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = _init_repo(tmp_path)
    before = _state(repo)
    _change_source_and_config(repo)

    def fail_rebuild(*_args, **_kwargs):
        raise RuntimeError("forced post-rescore failure")

    monkeypatch.setattr(
        "repowise.cli.commands.update_cmd.command._rebuild_graph_and_git",
        fail_rebuild,
    )
    result = CliRunner().invoke(
        cli,
        ["update", str(repo), "--index-only", "--no-agents"],
        catch_exceptions=True,
    )

    after = _state(repo)
    assert result.exit_code != 0
    assert after["last_sync_commit"] == before["last_sync_commit"]
    assert after["config_fingerprint"] == before["config_fingerprint"]
