"""Generation closes every planned page with an explicit outcome."""

from __future__ import annotations

from types import SimpleNamespace

from repowise.core.generation.job_system import JobSystem
from repowise.core.generation.models import GenerationConfig
from repowise.core.generation.page_generator.orchestrate import _GenerationRun


def test_unemitted_planned_pages_are_reconciled_as_skipped(tmp_path) -> None:
    jobs = JobSystem(tmp_path / "jobs")
    job_id = jobs.create_job(".", GenerationConfig(), "mock", "mock-model")
    jobs.start_job(job_id, 3)
    jobs.complete_page(job_id, "module_page:written")
    jobs.fail_page(job_id, "module_page:failed", "provider failed")
    run = SimpleNamespace(
        job_system=jobs,
        job_id=job_id,
        planned_page_ids={
            "module_page:written",
            "module_page:failed",
            "module_page:not-emitted",
        },
    )

    _GenerationRun._reconcile_job_outcomes(run)

    cp = jobs.get_checkpoint(job_id)
    assert cp.skipped_page_ids == ["module_page:not-emitted"]
    assert cp.skip_reasons == {"module_page:not-emitted": "not_emitted_by_current_selection"}
    assert cp.total_pages == cp.completed_pages + cp.failed_pages + cp.skipped_pages
