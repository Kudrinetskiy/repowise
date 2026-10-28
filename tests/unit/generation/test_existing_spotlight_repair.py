"""Existing-only admission is a scoped repair, never a resume/selection expansion."""

from types import SimpleNamespace

import pytest

from repowise.core.generation.page_generator.levels import build_level01_coros
from repowise.core.generation.page_generator.orchestrate import _GenerationRun


@pytest.mark.parametrize(
    ("deterministic", "resume", "scoped", "persisted", "expected"),
    [
        (True, False, True, True, ["first-native-match"]),
        (True, True, True, True, []),
        (False, False, True, True, []),
        (True, False, False, True, ["first-native-match"]),
        (True, False, True, False, []),
    ],
)
async def test_existing_repair_does_not_widen_resume_or_new_selection(
    deterministic, resume, scoped, persisted, expected
):
    existing_id = "symbol_spotlight:a.py::shared"
    new_id = "symbol_spotlight:a.py::new_symbol"
    absent_id = "symbol_spotlight:a.py::removed"

    class StructuralRenderer:
        async def generate_symbol_spotlight(self, symbol, *_args, **_kwargs):
            return symbol.signature

    parsed = SimpleNamespace(
        file_info=SimpleNamespace(path="a.py", is_api_contract=False),
        symbols=[
            SimpleNamespace(name="shared", signature="first-native-match"),
            SimpleNamespace(name="shared", signature="second-native-match"),
            SimpleNamespace(name="new_symbol", signature="unpersisted-candidate"),
        ],
    )
    run = SimpleNamespace(
        gen=StructuralRenderer(),
        config=SimpleNamespace(deterministic=deterministic),
        resume=resume,
        parsed_files=[parsed],
        selection=SimpleNamespace(symbol_spotlights=[]),
        sel_api_paths=set(),
        only_page_ids={existing_id, new_id, absent_id} if scoped else None,
        persisted_page_ids={existing_id, absent_id} if persisted else None,
        pagerank={},
        graph=None,
        source_map={},
        completed_ids=set(),
        preserved_page_ids=None,
    )
    run._emit = lambda page_id: _GenerationRun._emit(run, page_id)

    emitted = build_level01_coros(run)
    values = [await coroutine for _page_id, coroutine in emitted]

    assert values == expected
    assert [page_id for page_id, _coroutine in emitted] == ([existing_id] if expected else [])
