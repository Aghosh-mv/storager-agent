from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from .classifier import ClassifiedEntry, classify
from .diagnose import diagnose
from .facts import collect_facts
from .graph import build_relations
from .inspector import inspect_path
from .present import summarize_report
from .scanner import scan_immediate_children
from .session import Session

_TRACE = False

DIM = "\033[2m"
RESET = "\033[0m"


def configure(trace: bool = False) -> None:
    global _TRACE
    _TRACE = trace


def _trace(stage: str, elapsed: float, count: int) -> None:
    if _TRACE:
        print(f"  {DIM}▸ {stage} ({elapsed:.2f}s, {count} items){RESET}")


def scan_stage(session: Session, top_n: int) -> None:
    t0 = time.time()
    entries = scan_immediate_children(
        session.root, top_n=top_n, parallel=session.flags.parallel != "sequential"
    )
    session.entries = entries
    _trace("scanned", time.time() - t0, len(entries))


def inspect_stage(session: Session) -> None:
    dirs = [e for e in session.entries if e.is_dir]
    reports = {}
    t0 = time.time()
    if session.flags.parallel != "sequential" and len(dirs) >= 8:
        workers = min(len(dirs), 8)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            reps = list(ex.map(inspect_path, [d.path for d in dirs]))
        for rep in reps:
            reports[rep.path] = rep
    else:
        for d in dirs:
            rep = inspect_path(d.path)
            reports[rep.path] = rep
    _trace("inspected", time.time() - t0, len(dirs))
    session.reports = reports


def classify_stage(session: Session) -> None:
    t0 = time.time()
    out: list = []
    for e in session.entries:
        ce = classify(e)
        ce.summary = summarize_report(session.reports.get(str(e.path)))
        ce.facts = collect_facts(e.path)
        out.append(ce)
    session.classified = out
    _trace("classified", time.time() - t0, len(out))


def diagnose_stage(session: Session) -> None:
    t0 = time.time()
    session.problems = diagnose(session)
    _trace("diagnosed", time.time() - t0, len(session.problems))


def relate_stage(session: Session) -> None:
    t0 = time.time()
    rel = build_relations(session)
    for ce in session.classified:
        ce.relations = rel.get(str(ce.entry.path), [])
    session.relations = rel
    _trace("related", time.time() - t0, len(rel))


def analyze(session: Session, top_n: int = 30) -> None:
    scan_stage(session, top_n)
    inspect_stage(session)
    classify_stage(session)
    diagnose_stage(session)
    relate_stage(session)
