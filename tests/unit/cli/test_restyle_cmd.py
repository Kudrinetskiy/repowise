"""Tests for `repowise restyle` and `repowise wiki-styles` (CLI surface).

These cover the validation/guard rails that run *before* any generation — the
expensive regeneration path itself is exercised by the generation suite. The key
guarantees: unknown styles are rejected, restyle refuses repos with no pages, and
the listing surfaces the built-in catalogue + current style.
"""

from __future__ import annotations

import gc
import json
import subprocess
import warnings
from pathlib import Path

from click.testing import CliRunner

from repowise.cli.commands import restyle_cmd
from repowise.cli.main import cli
from repowise.core.generation import GenerationConfig
from repowise.core.providers.llm.mock import MockProvider


def _write_state(repo: Path, state: dict) -> None:
    d = repo / ".repowise"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _write_config(repo: Path, cfg: dict) -> None:
    import yaml

    d = repo / ".repowise"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")


def _init_tiny_index(repo: Path) -> None:
    (repo / "main.py").write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=RepoWise Test",
            "-c",
            "user.email=repowise-test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repo,
        check=True,
    )
    result = CliRunner().invoke(
        cli,
        [
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
    )
    assert result.exit_code == 0, result.output


def _generation_config(repo: Path) -> GenerationConfig:
    cfg = restyle_cmd.load_config(repo)
    return GenerationConfig.from_repo_config(
        cfg,
        max_concurrency=1,
        language=cfg.get("language", "en"),
        reasoning="low",
        enable_onboarding=bool(cfg.get("enable_onboarding", True)),
        wiki_style="caveman",
    )


class RecordingProgress:
    def __init__(self) -> None:
        self.started: list[tuple[str, int | None]] = []
        self.completed: list[str] = []

    def on_phase_start(self, phase: str, total: int | None) -> None:
        self.started.append((phase, total))

    def on_item_done(self, phase: str) -> None:
        self.completed.append(phase)

    def on_phase_done(self, phase: str) -> None:
        return None

    def on_message(self, level: str, message: str) -> None:
        return None

    def set_cost(self, total_cost: float) -> None:
        return None


def test_run_restyle_reports_progress_and_returns_persisted_totals(tmp_path: Path) -> None:
    _init_tiny_index(tmp_path)
    progress = RecordingProgress()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        generated, total_pages, total_tokens = restyle_cmd.run_async(
            restyle_cmd._run_restyle(
                tmp_path,
                MockProvider(),
                _generation_config(tmp_path),
                exclude_patterns=[],
                progress=progress,
            )
        )
        gc.collect()

    assert not any("never awaited" in str(item.message) for item in caught)
    assert generated
    assert total_pages >= len(generated)
    assert total_tokens > 0
    assert any(phase == "generation" for phase, _total in progress.started)
    assert "generation" in progress.completed


def test_restyle_command_persists_provider_state_and_resume_notice(tmp_path: Path) -> None:
    _init_tiny_index(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "restyle",
            "caveman",
            str(tmp_path),
            "--provider",
            "mock",
            "--concurrency",
            "1",
            "--reasoning",
            "low",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "each generated page is saved as it completes" in result.output
    state = json.loads((tmp_path / ".repowise" / "state.json").read_text(encoding="utf-8"))
    assert state["provider"] == "mock"
    assert state["model"] == "mock-model-1"
    assert state["reasoning"] == "low"
    assert state["total_pages"] > 0
    assert state["total_tokens"] > 0
    assert state["docs_mode"] == "llm"
    config = restyle_cmd.load_config(tmp_path)
    assert config["wiki_style"] == "caveman"
    assert config["provider"] == "mock"
    assert config["model"] == "mock-model-1"
    assert config["reasoning"] == "low"


def test_wiki_styles_lists_builtins(tmp_path):
    result = CliRunner().invoke(cli, ["wiki-styles", str(tmp_path)])
    assert result.exit_code == 0
    for name in ("comprehensive", "caveman", "reference", "tutorial"):
        assert name in result.output


def test_wiki_styles_marks_current(tmp_path):
    _write_config(tmp_path, {"wiki_style": "caveman"})
    result = CliRunner().invoke(cli, ["wiki-styles", str(tmp_path)])
    assert result.exit_code == 0
    # caveman line should be flagged current
    caveman_line = next(line for line in result.output.splitlines() if "caveman" in line)
    assert "current" in caveman_line


def test_restyle_no_style_shows_current_and_options():
    """With no STYLE arg, restyle prints the current style + catalogue (no regen)."""
    runner = CliRunner()
    with runner.isolated_filesystem() as fs:
        _write_config(Path(fs), {"wiki_style": "reference"})
        result = runner.invoke(cli, ["restyle"])
    assert result.exit_code == 0
    assert "Current wiki style" in result.output
    assert "reference" in result.output
    assert "caveman" in result.output  # catalogue shown


def test_restyle_verbose_configures_cli_logging(monkeypatch, tmp_path):
    calls: list[bool] = []
    monkeypatch.setattr(
        restyle_cmd,
        "configure_cli_logging",
        lambda *, verbose=False: calls.append(verbose),
    )

    result = CliRunner().invoke(
        cli,
        ["restyle", "caveman", str(tmp_path), "--yes", "--verbose"],
    )

    assert result.exit_code == 1
    assert "No index found" in result.output
    assert calls == [True]


def test_restyle_unknown_style_errors(tmp_path):
    result = CliRunner().invoke(cli, ["restyle", "bogus", str(tmp_path)])
    # A mistyped STYLE is a usage error (Click convention: exit code 2), not a
    # generic failure — see the telemetry usage_error classification.
    assert result.exit_code == 2
    assert "Unknown style" in result.output
    assert "comprehensive" in result.output  # lists valid choices


def test_restyle_requires_index(tmp_path):
    result = CliRunner().invoke(cli, ["restyle", "caveman", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "No index found" in result.output


def test_restyle_refuses_repo_with_no_pages(tmp_path):
    _write_state(tmp_path, {"docs_enabled": False, "last_sync_commit": "abc"})
    result = CliRunner().invoke(cli, ["restyle", "caveman", str(tmp_path), "--yes"])
    assert result.exit_code == 1
    assert "no wiki pages to restyle" in result.output


def test_restyle_warns_but_does_not_refuse_on_stub_wiki(tmp_path):
    # Restyling a wiki with no written prose writes the subsystem pages in the
    # chosen style, so the guard must let it through after saying what it costs.
    _write_state(tmp_path, {"docs_mode": "deterministic", "last_sync_commit": "abc"})
    result = CliRunner().invoke(cli, ["restyle", "caveman", str(tmp_path), "--yes"])
    assert "no written prose yet" in result.output
    assert "no wiki pages to restyle" not in result.output


def test_restyle_known_styles_accepted_past_validation(tmp_path):
    """All four built-ins clear name validation (they fail later on no-index)."""
    for style in ("comprehensive", "caveman", "reference", "tutorial"):
        result = CliRunner().invoke(cli, ["restyle", style, str(tmp_path), "--yes"])
        # Past the unknown-style guard → fails on the missing index instead.
        assert "Unknown style" not in result.output
        assert "No index found" in result.output
