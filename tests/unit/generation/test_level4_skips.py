"""Module context gates close the planned page instead of silently losing it."""

from types import SimpleNamespace

from repowise.core.generation import onboarding as _onboarding  # noqa: F401
from repowise.core.generation.page_generator.levels import build_level4_coros


def test_module_without_file_contexts_records_specific_skip_reason() -> None:
    skipped: list[tuple[str, str]] = []
    module = SimpleNamespace(key="pkg/empty", file_paths=("pkg/empty.py",), context_paths=())
    run = SimpleNamespace(
        gen=object(),
        sel_module_groups=[module],
        file_page_contexts={},
        graph_builder=SimpleNamespace(execution_flows=lambda: SimpleNamespace(flows=[])),
        parsed_files=[],
        _emit=lambda _pid: True,
        _record_skip=lambda pid, reason: skipped.append((pid, reason)),
    )
    assert build_level4_coros(run) == []
    assert skipped == [("module_page:pkg/empty", "no_file_contexts")]
