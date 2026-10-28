"""Conservative Git spelling for physical paths on case-insensitive volumes."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path


class GitPathIdentity:
    """Snapshot Git names once; never collapse ambiguous or distinct files."""

    def __init__(self, root: Path) -> None:
        from repowise.core.git_refs import tracked_paths_at

        self.root = root.resolve()
        self._head = self._groups(tracked_paths_at(str(self.root), "HEAD"))
        self._index: dict[str, set[str]] = {}
        self._entries: dict[Path, set[str]] = {}
        try:
            listing = subprocess.run(
                ["git", "-C", str(self.root), "ls-files", "--stage", "-z"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout
            for record in listing.split("\0"):
                if not record:
                    continue
                header, path = record.split("\t", 1)
                mode, _object, stage = header.split()
                group = self._index.setdefault(path.casefold(), set())
                group.add(path)
                if stage != "0" or mode not in {"100644", "100755"}:
                    group.add("")  # no regular, merged index identity
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            self._index = {}

    @staticmethod
    def _groups(paths: frozenset[str]) -> dict[str, set[str]]:
        groups: dict[str, set[str]] = {}
        for path in paths:
            groups.setdefault(path.casefold(), set()).add(path)
        return groups

    def canonical(self, path: str) -> str:
        """Return an agreed tracked alias only with positive physical proof."""
        head = self._head.get(path.casefold(), set())
        if len(head) != 1 or head != self._index.get(path.casefold()):
            return path
        target = next(iter(head))
        if target == path:
            return path
        try:
            stats = []
            for relative in (path, target):
                parts = Path(relative).parts
                if not parts or Path(relative).is_absolute() or ".." in parts:
                    return path
                source = self.root
                actual = []
                for part in parts:
                    if source not in self._entries:
                        self._entries[source] = {entry.name for entry in source.iterdir()}
                    entries = self._entries[source]
                    matches = {name for name in entries if name.casefold() == part.casefold()}
                    if part not in entries and len(matches) != 1:
                        return path
                    name = part if part in entries else next(iter(matches))
                    actual.append(name)
                    source /= name
                    if source.is_symlink():
                        return path
                if not source.resolve().is_relative_to(self.root):
                    return path
                info = source.stat()
                if not stat.S_ISREG(info.st_mode):
                    return path
                # Hard links with two exact directory entries are distinct
                # working-tree identities even when device/inode agree.
                stats.append((tuple(actual), info.st_dev, info.st_ino))
            return target if stats[0] == stats[1] else path
        except OSError:
            return path
