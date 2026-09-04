"""Explicit accounting for module pages skipped before coroutine creation."""

from __future__ import annotations

from types import SimpleNamespace

from repowise.core.generation.page_generator.levels import build_level4_coros


def test_module_without_file_contexts_records_specific_skip_reason() -> None:
    skipped: list[tuple[str, str]] = []
    module = SimpleNamespace(
        key="pkg/empty",
        file_paths=("pkg/empty.py",),
        context_paths=("pkg/empty.py",),
    )
    run = SimpleNamespace(
        gen=object(),
        sel_module_groups=[module],
        file_page_contexts={},
        _emit=lambda _page_id: True,
        _record_skip=lambda page_id, reason: skipped.append((page_id, reason)),
    )

    assert build_level4_coros(run) == []
    assert skipped == [("module_page:pkg/empty", "no_file_contexts")]
