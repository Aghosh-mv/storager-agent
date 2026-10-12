"""Core disk scanner — walks the filesystem and measures sizes."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple


@dataclass
class DiskEntry:
    path: Path
    size: int  # bytes
    is_dir: bool
    child_count: int = 0
    error: Optional[str] = None

    @property
    def size_str(self) -> str:
        return human_size(self.size)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def dir_size(path: Path, *, max_depth: int = 64, _depth: int = 0) -> Tuple[int, int, Optional[str]]:
    """Return (total_bytes, file_count, error)."""
    if _depth > max_depth:
        return 0, 0, "max depth"

    total = 0
    count = 0
    err: Optional[str] = None

    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    st = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(st.st_mode):
                        sub_total, sub_count, sub_err = dir_size(
                            Path(entry.path), max_depth=max_depth, _depth=_depth + 1
                        )
                        total += sub_total
                        count += sub_count
                        if sub_err and err is None:
                            err = sub_err
                    else:
                        total += st.st_size
                        count += 1
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except PermissionError:
        return 0, 0, "permission denied"
    except FileNotFoundError:
        return 0, 0, "not found"
    except OSError as e:
        return 0, 0, str(e)

    return total, count, err


def scan_immediate_children(root: Path, *, top_n: Optional[int] = None) -> List[DiskEntry]:
    """List immediate children of root with sizes. Directories are measured recursively."""
    results: List[DiskEntry] = []

    try:
        with os.scandir(root) as it:
            for entry in it:
                p = Path(entry.path)
                try:
                    st = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(st.st_mode):
                        total, count, err = dir_size(p)
                        results.append(
                            DiskEntry(path=p, size=total, is_dir=True, child_count=count, error=err)
                        )
                    else:
                        results.append(
                            DiskEntry(path=p, size=st.st_size, is_dir=False, child_count=1)
                        )
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except PermissionError:
        return []
    except FileNotFoundError:
        return []

    results.sort(key=lambda e: e.size, reverse=True)
    if top_n is not None:
        results = results[:top_n]
    return results


def scan_path_deep(path: Path, *, max_depth: int = 3, min_size: int = 1024 * 1024) -> List[DiskEntry]:
    """
    Recursively find the biggest leaves under `path`.
    Returns entries (files and dirs) that are >= min_size, sorted desc.
    """
    found: List[DiskEntry] = []

    def _walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            with os.scandir(current) as it:
                for entry in it:
                    p = Path(entry.path)
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if stat.S_ISDIR(st.st_mode):
                            total, count, err = dir_size(p)
                            if total >= min_size:
                                found.append(
                                    DiskEntry(path=p, size=total, is_dir=True, child_count=count, error=err)
                                )
                            _walk(p, depth + 1)
                        else:
                            if st.st_size >= min_size:
                                found.append(
                                    DiskEntry(path=p, size=st.st_size, is_dir=False, child_count=1)
                                )
                    except (PermissionError, FileNotFoundError, OSError):
                        continue
        except (PermissionError, FileNotFoundError, OSError):
            return

    _walk(path, 0)
    found.sort(key=lambda e: e.size, reverse=True)
    return found
