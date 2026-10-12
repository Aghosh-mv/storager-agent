from __future__ import annotations

from pathlib import Path

from .facts import collect_facts
from .session import Session


def build_relations(session: Session) -> dict:
    rel: dict = {}
    for ce in session.classified:
        path = ce.entry.path
        notes = collect_facts(path)
        parent = path.parent
        if path.name == "node_modules" and (parent / "package.json").exists():
            notes.append(f"project '{parent.name}' is at {parent}")
        if path.suffix.lower() in (".dmg", ".pkg", ".exe", ".msi", ".iso") or path.name.lower() in ("downloads", "download"):
            notes.append("came from the internet — usually re-downloadable")
        if notes:
            rel[str(path)] = notes
    return rel
