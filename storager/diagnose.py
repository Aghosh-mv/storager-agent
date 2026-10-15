from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .session import Session
from .scanner import human_size


@dataclass
class Problem:
    severity: str
    path: Optional[Path]
    message: str


def diagnose(session: Session) -> list:
    probs: list = []

    try:
        usage = shutil.disk_usage(session.root)
        pct = usage.used / usage.total * 100
        if pct >= 90:
            probs.append(Problem("critical", None, f"disk is {pct:.0f}% full — urgent cleanup needed"))
        elif pct >= 75:
            probs.append(Problem("warn", None, f"disk is {pct:.0f}% full — worth cleaning soon"))
    except OSError:
        pass

    now = time.time()
    for ce in session.classified:
        rep = session.reports.get(str(ce.entry.path))
        if rep and rep.error:
            probs.append(Problem("info", ce.entry.path, f"could not fully read this folder ({rep.error})"))
        if ce.category == "cache" and rep and rep.newest:
            age_days = (now - rep.newest) / 86400
            if age_days > 180:
                probs.append(Problem("info", ce.entry.path, f"cache untouched for {age_days // 30:.0f} months — very safe to clear"))
        if ce.entry.is_dir and rep and rep.files == 0 and rep.dirs == 0:
            probs.append(Problem("info", ce.entry.path, "empty folder — safe to remove"))
        if ce.entry.size > 5 * 1024**3 and not ce.entry.is_dir:
            probs.append(Problem("warn", ce.entry.path, f"single file {ce.entry.size_str} — big items are usually the fastest win"))

    seen: dict = {}
    for ce in session.classified:
        if not ce.entry.is_dir and ce.entry.size >= 50 * 1024**2:
            seen.setdefault(ce.entry.size, []).append(str(ce.entry.path))
    for size, paths in seen.items():
        if len(paths) > 1:
            probs.append(Problem("warn", None, f"{len(paths)} files of exactly {human_size(size)} — possible duplicates"))

    for size, group in _find_true_duplicates(session):
        probs.append(Problem("warn", None, f"{len(group)} identical files ({human_size(size)}) — real duplicates wasting space"))

    return probs


def _hash_file(path: Path, chunk: int = 1024 * 1024):
    import hashlib
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


def _find_true_duplicates(session: Session, min_size: int = 1024 * 1024, cap: int = 60):
    groups: dict = {}
    for ce in session.classified:
        if not ce.entry.is_dir and ce.entry.size >= min_size:
            groups.setdefault(ce.entry.size, []).append(ce.entry.path)

    out = []
    for size, paths in groups.items():
        if len(paths) < 2 or len(paths) > cap:
            continue
        by_hash: dict = {}
        for p in paths:
            h = _hash_file(p)
            if h:
                by_hash.setdefault(h, []).append(p)
        for h, ps in by_hash.items():
            if len(ps) > 1:
                out.append((size, ps))
    return out
