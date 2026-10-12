from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DiskEntry:
    path: Path
    size: int
    is_dir: bool
    child_count: int = 0
    error: Optional[str] = None

    @property
    def size_str(self) -> str:
        return human_size(self.size)


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def dir_size(path: Path, max_depth: int = 64, _depth: int = 0) -> tuple:
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


def scan_immediate_children(root: Path, top_n: Optional[int] = None, parallel: bool = False) -> list:
    dirs: list[Path] = []
    results: list[DiskEntry] = []

    try:
        with os.scandir(root) as it:
            for entry in it:
                p = Path(entry.path)
                try:
                    st = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(st.st_mode):
                        dirs.append(p)
                    else:
                        results.append(DiskEntry(path=p, size=st.st_size, is_dir=False, child_count=1))
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except (PermissionError, FileNotFoundError, OSError):
        return []

    def measure(p: Path) -> tuple:
        total, count, err = dir_size(p)
        return p, total, count, err

    if parallel and len(dirs) >= 8:
        workers = min(len(dirs), 8)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            measured = list(ex.map(measure, dirs))
    else:
        measured = [measure(p) for p in dirs]

    for p, total, count, err in measured:
        results.append(DiskEntry(path=p, size=total, is_dir=True, child_count=count, error=err))

    results.sort(key=lambda e: e.size, reverse=True)
    if top_n is not None:
        results = results[:top_n]
    return results
