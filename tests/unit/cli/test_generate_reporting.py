"""User-facing generate summaries distinguish complete and partial runs."""

from __future__ import annotations

from types import SimpleNamespace

from repowise.cli.commands.generate_cmd.command import _format_completion_summary


def _outcome(*, completed: int, failed: int, skipped: int, remaining: int = 0):
    return SimpleNamespace(
        completed_page_ids=tuple(f"module_page:ok-{i}" for i in range(completed)),
        failed_page_ids=tuple(f"module_page:failed-{i}" for i in range(failed)),
        skipped_page_ids=tuple(f"module_page:skipped-{i}" for i in range(skipped)),
        marked_stale=0,
        remaining_template_pages=remaining,
    )


def test_complete_summary_can_say_every_page_is_written() -> None:
    summary = _format_completion_summary(_outcome(completed=3, failed=0, skipped=0), elapsed=1.2)

    assert "Generated 3 of 3 pages" in summary
    assert "every page is now written" in summary


def test_partial_summary_reports_failed_and_skipped_without_success_claim() -> None:
    summary = _format_completion_summary(_outcome(completed=2, failed=1, skipped=1), elapsed=1.2)

    assert "Generated 2 of 4 pages" in summary
    assert "1 failed" in summary
    assert "1 skipped" in summary
    assert "every page is now written" not in summary
