"""Git spelling must survive case-insensitive filesystem traversal."""

import subprocess
from pathlib import Path

import pytest

from repowise.core.ingestion.parse_cache import ParseCache
from repowise.core.ingestion.parser import parse_file
from repowise.core.ingestion.traverser import FileTraverser


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _tracked(root: Path) -> None:
    (root / "scripts").mkdir()
    (root / "scripts/check.py").write_text("def check():\n    return 1\n")
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "initial",
    )


def _capital_alias(root: Path) -> None:
    (root / "scripts").rename(root / "temporary-case")
    (root / "temporary-case").rename(root / "Scripts")
    if not (root / "scripts/check.py").exists():
        pytest.skip("requires a case-insensitive filesystem")


def test_traversal_uses_unique_agreed_git_spelling(tmp_path: Path) -> None:
    _tracked(tmp_path)
    _capital_alias(tmp_path)
    found = list(FileTraverser(tmp_path).traverse())
    assert [f.path for f in found] == ["scripts/check.py"]
    assert Path(found[0].abs_path).samefile(tmp_path / "Scripts/check.py")
    parsed = parse_file(found[0], Path(found[0].abs_path).read_bytes())
    assert {symbol.id for symbol in parsed.symbols} == {"scripts/check.py::check"}
    cache = ParseCache(tmp_path / ".repowise")
    cache.put(parsed, parsed.content_hash)
    cache.save()
    reused = ParseCache(tmp_path / ".repowise")
    reused.load()
    hit = reused.get(found[0], parsed.content_hash)
    assert hit is not None
    assert {symbol.id for symbol in hit.symbols} == {"scripts/check.py::check"}


def test_staged_case_rename_is_not_rewritten_to_head(tmp_path: Path) -> None:
    _tracked(tmp_path)
    _git(tmp_path, "mv", "scripts", "temporary-case")
    _git(tmp_path, "mv", "temporary-case", "Scripts")
    assert [f.path for f in FileTraverser(tmp_path).traverse()] == ["Scripts/check.py"]


def test_unmerged_index_does_not_authorize_case_normalization(tmp_path: Path) -> None:
    _tracked(tmp_path)
    blob = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD:scripts/check.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(tmp_path, "update-index", "--force-remove", "scripts/check.py")
    subprocess.run(
        ["git", "-C", str(tmp_path), "update-index", "-z", "--index-info"],
        input=f"100644 {blob} 1\tscripts/check.py\0",
        check=True,
        capture_output=True,
        text=True,
    )
    _capital_alias(tmp_path)
    assert [f.path for f in FileTraverser(tmp_path).traverse()] == ["Scripts/check.py"]


def test_ambiguous_tracked_spellings_are_not_collapsed(tmp_path: Path) -> None:
    _tracked(tmp_path)
    blob = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD:scripts/check.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(tmp_path, "update-index", "--add", "--cacheinfo", f"100644,{blob},Scripts/check.py")
    _git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "ambiguous case names",
    )
    _capital_alias(tmp_path)
    assert [f.path for f in FileTraverser(tmp_path).traverse()] == ["Scripts/check.py"]


def test_distinct_case_sensitive_sources_keep_both_identities(tmp_path: Path) -> None:
    _tracked(tmp_path)
    if (tmp_path / "Scripts").exists():
        pytest.skip("requires a case-sensitive filesystem")
    (tmp_path / "Scripts").mkdir()
    (tmp_path / "Scripts/check.py").write_text("def other():\n    return 2\n")
    assert {f.path for f in FileTraverser(tmp_path).traverse()} == {
        "scripts/check.py",
        "Scripts/check.py",
    }


def test_distinct_case_sensitive_hardlink_is_not_a_case_alias(tmp_path: Path) -> None:
    _tracked(tmp_path)
    if (tmp_path / "Scripts").exists():
        pytest.skip("requires a case-sensitive filesystem")
    (tmp_path / "Scripts").mkdir()
    (tmp_path / "Scripts/check.py").hardlink_to(tmp_path / "scripts/check.py")
    assert {f.path for f in FileTraverser(tmp_path).traverse()} == {
        "scripts/check.py",
        "Scripts/check.py",
    }


def test_escaping_directory_alias_is_not_traversed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _tracked(root)
    (root / "scripts/check.py").unlink()
    (root / "scripts").rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "check.py").write_text("def secret():\n    return 7\n")
    (root / "Scripts").symlink_to(outside, target_is_directory=True)
    assert list(FileTraverser(root).traverse()) == []
