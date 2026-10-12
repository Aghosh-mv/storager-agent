from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ItemReport:
    path: str
    files: int = 0
    dirs: int = 0
    by_ext: dict = field(default_factory=dict)
    oldest: Optional[float] = None
    newest: Optional[float] = None
    top_files: list = field(default_factory=list)
    error: Optional[str] = None


def inspect_path(path: Path, cap: int = 5000) -> ItemReport:
    rep = ItemReport(path=str(path))
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path, onerror=lambda e: None, followlinks=False):
            rep.dirs += len(dirnames)
            for fn in filenames:
                total += 1
                if total > cap:
                    return rep
                fp = Path(dirpath) / fn
                try:
                    st = fp.stat()
                except OSError:
                    continue
                rep.files += 1
                ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else "(none)"
                rep.by_ext[ext] = rep.by_ext.get(ext, 0) + 1
                mt = st.st_mtime
                rep.oldest = mt if rep.oldest is None else min(rep.oldest, mt)
                rep.newest = mt if rep.newest is None else max(rep.newest, mt)
                rep.top_files.append((fn, st.st_size))
    except OSError as e:
        rep.error = str(e)
    rep.top_files.sort(key=lambda t: t[1], reverse=True)
    rep.top_files = rep.top_files[:5]
    return rep
