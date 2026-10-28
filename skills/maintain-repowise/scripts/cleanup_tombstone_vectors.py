"""Preview/apply one approved template-file-tombstone vector deletion cohort.

Quiesce all writers before preview and keep them stopped through apply. A receipt
is an exact-state approval artifact, not a lock or permission to prune other
orphans. This script never creates a store, embeds, reindexes, or writes SQL.
Cohorts are capped at 5000; native delete_many chunks them at 500. A mid-delete
failure can be partial: preserve evidence and diagnose, never retry automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path, PurePosixPath

from repowise.core.persistence.vector_store import LanceDBVectorStore
from repowise.core.providers.embedding.base import MockEmbedder


def _feed_json(digest, value: object) -> None:
    for chunk in json.JSONEncoder(sort_keys=True, default=str).iterencode(value):
        digest.update(chunk.encode())
    digest.update(b"\n")


def _hash(value: object) -> str:
    digest = hashlib.sha256()
    _feed_json(digest, value)
    return digest.hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        timeout=30,
        check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )
    if result.returncode:
        raise ValueError(f"Git check failed: {' '.join(args)}")
    return result.stdout


def _root(repo_root: Path) -> Path:
    root = Path(repo_root).resolve(strict=True)
    if Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve() != root:
        raise ValueError("repo_root must be the exact Git root")
    for relative in (
        ".repowise",
        ".repowise/wiki.db",
        ".repowise/state.json",
        ".repowise/config.yaml",
        ".repowise/lancedb",
        ".repowise/lancedb/wiki_pages.lance",
    ):
        path = root / relative
        if not path.exists() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Required existing non-symlink store path unavailable: {relative}")
    return root


def _source_hash(root: Path) -> str:
    """Bind file bytes, not just status names; do not recurse into submodules."""
    digest = hashlib.sha256()
    inventory = _git(
        root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        ".",
        ":(exclude).repowise",
    )
    for name in sorted(set(os.fsdecode(inventory).split("\0")) - {""}):
        path = root / name
        if path.is_symlink():
            entry = {"path": name, "symlink": os.readlink(path)}
        elif path.is_file():
            entry = {"path": name, "file_sha256": _file_hash(path)}
        elif path.is_dir():
            entry = {"path": name, "directory_not_recursed": True}
        elif not os.path.lexists(path):
            entry = {"path": name, "absent": True}
        else:
            raise ValueError(f"Unsupported source file kind: {name}")
        _feed_json(digest, entry)
    digest.update(
        _git(
            root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--",
            ".",
            ":(exclude).repowise",
        )
    )
    return digest.hexdigest()


def _snapshot(root: Path) -> tuple[dict, dict[str, dict], set[str]]:
    uri = (root / ".repowise/wiki.db").as_uri() + "?mode=ro"
    sql_digest = hashlib.sha256()
    rows: dict[str, dict] = {}
    decisions: set[str] = set()
    repo_ids = []
    try:
        with sqlite3.connect(uri, uri=True, timeout=10) as sql:
            sql.row_factory = sqlite3.Row
            sql.execute("PRAGMA query_only=ON")
            sql.execute("BEGIN")
            for name in ("repositories", "wiki_pages", "decision_records"):
                _feed_json(sql_digest, {"table": name})
                # Only one row's prose/digest is in memory; retain metadata and hashes.
                for raw_row in sql.execute(f"SELECT * FROM {name} ORDER BY id"):
                    row = dict(raw_row)
                    _feed_json(sql_digest, row)
                    if name == "repositories":
                        if Path(row["local_path"]).resolve() == root:
                            repo_ids.append(row["id"])
                    elif row["repository_id"] == repo_ids[0]:
                        if name == "decision_records":
                            decisions.add("decision:" + row["id"])
                        else:
                            rows[row["id"]] = {
                                key: row[key]
                                for key in (
                                    "id",
                                    "target_path",
                                    "page_type",
                                    "provider_name",
                                    "freshness_status",
                                )
                            } | {"row_sha256": _hash(row)}
                if name == "repositories" and len(repo_ids) != 1:
                    raise ValueError("SQLite must identify exactly one matching repository")
    except sqlite3.Error as exc:
        raise ValueError(f"Cannot read required SQLite schema: {exc}") from exc
    state = root / ".repowise/state.json"
    if not state.is_file() or state.is_symlink():
        raise ValueError("Required existing non-symlink state.json unavailable")
    snapshot = {
        "repo_root": str(root),
        "head": _git(root, "rev-parse", "--verify", "HEAD").decode().strip(),
        "git_index_sha256": hashlib.sha256(_git(root, "ls-files", "--stage", "-z")).hexdigest(),
        "git_worktree_sha256": _source_hash(root),
        "source_scope": "tracked + untracked nonignored files; excludes .repowise; submodules not recursed",
        "sql_rows_sha256": sql_digest.hexdigest(),
        "state_sha256": _file_hash(state),
        "config_sha256": _file_hash(root / ".repowise/config.yaml"),
    }
    return snapshot, rows, decisions


def _candidate(root: Path, row: dict, head_paths: set[str], index_paths: set[str]) -> dict:
    if (row["page_type"], row["provider_name"], row["freshness_status"]) != (
        "file_page",
        "template",
        "tombstone",
    ):
        raise ValueError(f"Orphan is not a template file-page tombstone: {row['id']}")
    target = row["target_path"]
    if not isinstance(target, str) or not target or "\x00" in target:
        raise ValueError(f"Empty/invalid target_path: {row['id']}")
    relative = PurePosixPath(target)
    if relative.is_absolute() or ".." in relative.parts or str(relative) in ("", "."):
        raise ValueError(f"Non-repository target_path: {row['id']}")
    path = root / target
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"Target escapes repository: {row['id']}")
    if os.path.lexists(path) or str(relative) in head_paths or str(relative) in index_paths:
        raise ValueError(f"Target exists in filesystem, HEAD or Git index: {row['id']}")
    return {
        key: row[key]
        for key in ("id", "target_path", "page_type", "provider_name", "freshness_status")
    } | {"row_sha256": row["row_sha256"]}


async def preview(repo_root: Path) -> dict:
    root = _root(repo_root)
    store = LanceDBVectorStore(str(root / ".repowise/lancedb"), MockEmbedder())
    try:
        vectors = await store.list_page_ids()
    finally:
        await store.close()
    if not vectors or len(vectors) > 1_000_000:
        raise ValueError("Empty/unreadable or oversized vector ID set; refusing cleanup")
    snapshot, pages, decisions = _snapshot(root)
    live = {key for key, row in pages.items() if row["freshness_status"] != "tombstone"}
    orphans = vectors - live - decisions
    if len(orphans) > 5000:
        raise ValueError("Cohort exceeds bounded cleanup scope (5000)")
    head_paths = set(
        os.fsdecode(_git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD")).split("\0")
    )
    index_paths = set(os.fsdecode(_git(root, "ls-files", "-z")).split("\0"))
    candidates = []
    for page_id in sorted(orphans):
        if page_id not in pages:
            raise ValueError(
                f"Orphan lacks matching SQL page; generic pruning forbidden: {page_id}"
            )
        candidates.append(_candidate(root, pages[page_id], head_paths, index_paths))
    receipt = {
        "schema": 1,
        **snapshot,
        "vector_ids": sorted(vectors),
        "candidate_ids": sorted(orphans),
        "candidates": candidates,
    }
    receipt["receipt_sha256"] = _hash(receipt)
    return receipt


async def apply_receipt(repo_root: Path, receipt: dict) -> dict:
    try:
        current = await preview(repo_root)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Cannot revalidate receipt: {exc}") from exc
    # Canonical JSON distinguishes booleans from integers (Python dict equality does not).
    if not isinstance(receipt, dict) or _hash(receipt) != _hash(current):
        raise ValueError(
            "Receipt or repository/HEAD/index/SQL/state/vector set changed; nothing deleted"
        )
    approved = current["candidate_ids"]
    if not approved:
        raise ValueError("Receipt contains no approved tombstone vectors")
    root = Path(current["repo_root"])
    store = LanceDBVectorStore(str(root / ".repowise/lancedb"), MockEmbedder())
    try:
        # A second ID check narrows the gap; writers must still remain quiescent.
        if await store.list_page_ids() != set(current["vector_ids"]):
            raise ValueError("Vector IDs changed before deletion; nothing deleted")
        await store.delete_many(approved)
        remaining = await store.list_page_ids()
        if remaining != set(current["vector_ids"]) - set(approved):
            raise RuntimeError(
                "Deletion postcheck failed; preserve stores and diagnose; do not retry"
            )
        after, _, _ = _snapshot(root)
        if any(after[key] != current[key] for key in after):
            raise RuntimeError(
                "Source/SQL/state changed during cleanup; stop and diagnose; do not retry"
            )
    finally:
        await store.close()
    return {
        "receipt_sha256": current["receipt_sha256"],
        "deleted_ids": approved,
        "remaining_vector_ids": sorted(remaining),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", metavar="RECEIPT_FILE", type=Path)
    args = parser.parse_args()
    import structlog

    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
    try:
        if args.preview:
            result = asyncio.run(preview(args.repo_root))
        else:
            if args.apply.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Receipt exceeds 16 MiB")
            receipt = json.loads(args.apply.read_text())
            result = asyncio.run(apply_receipt(args.repo_root, receipt))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Cleanup refused/failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
