from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

CONFIG_DIR = Path.home() / ".config" / "storager"
JOURNAL_FILE = CONFIG_DIR / "journal.json"


@dataclass
class JournalEntry:
    original: str
    dest: Optional[str]
    size: int
    at: str
    batch: str


def _load() -> list:
    if not JOURNAL_FILE.exists():
        return []
    try:
        return json.loads(JOURNAL_FILE.read_text())
    except (json.JSONDecodeError, TypeError):
        return []


def _save(rows: list) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL_FILE.write_text(json.dumps(rows, indent=2))


def record_batch(results: list, batch: Optional[str] = None) -> None:
    batch = batch or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    rows = _load()
    for r in results:
        if r.ok and r.dest is not None:
            rows.append(asdict(JournalEntry(
                original=str(r.path),
                dest=str(r.dest),
                size=r.freed_bytes,
                at=datetime.now().isoformat(),
                batch=batch,
            )))
    _save(rows)


def latest_batch() -> Optional[str]:
    rows = _load()
    if not rows:
        return None
    return rows[-1].get("batch")


def entries_for_batch(batch: str) -> list:
    return [r for r in _load() if r.get("batch") == batch]


def remove_batch(batch: str) -> None:
    rows = [r for r in _load() if r.get("batch") != batch]
    _save(rows)
