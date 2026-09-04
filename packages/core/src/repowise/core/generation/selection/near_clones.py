"""Near-clone filtering shared by every page-selection caller."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from repowise.core.ingestion.models import ParsedFile


def select_clone_representatives(
    code_files: list[ParsedFile],
    pagerank: dict[str, float],
    *,
    min_cluster_size: int = 3,
) -> set[str]:
    """Return paths dropped in favour of one stable near-clone representative."""
    clusters: dict[tuple[str, tuple[tuple[str, str], ...]], list[ParsedFile]] = defaultdict(list)
    for parsed in code_files:
        if parsed.file_info.is_entry_point or not parsed.symbols:
            continue
        parent = str(Path(parsed.file_info.path).parent.as_posix())
        shape = tuple(sorted((str(symbol.kind), symbol.name) for symbol in parsed.symbols))
        clusters[(parent, shape)].append(parsed)

    dropped: set[str] = set()
    for members in clusters.values():
        if len(members) < min_cluster_size:
            continue
        members.sort(
            key=lambda parsed: (
                -pagerank.get(parsed.file_info.path, 0.0),
                parsed.file_info.path,
            )
        )
        dropped.update(parsed.file_info.path for parsed in members[1:])
    return dropped
