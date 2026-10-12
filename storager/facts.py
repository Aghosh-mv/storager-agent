from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable

FACTS_DIR = Path.home() / ".config" / "storager" / "facts"


def _fact_node_modules(path: Path) -> list:
    parent = path.parent
    if (parent / "package.json").exists():
        return [f"needed by project '{parent.name}' at {parent}"]
    return ["JS dependencies — reinstall with 'npm install' in the parent project"]


def _fact_venv(path: Path) -> list:
    parent = path.parent
    if any((parent / f).exists() for f in ("pyproject.toml", "setup.py", "requirements.txt")):
        return [f"Python virtual environment for project '{parent.name}' at {parent}"]
    return ["Python virtual environment — recreate with 'python -m venv'"]


def _fact_git(path: Path) -> list:
    return [f"git data for project '{path.parent.name}' at {path.parent} — deleting loses local branches, history, and stashes"]


def _fact_docker(path: Path) -> list:
    return ["Docker data — deleting it removes containers/images/volumes and can break running apps"]


def _fact_trash(path: Path) -> list:
    return ["already in Trash — safe to empty"]


INTERNAL_FACTS: list = [
    ("node_modules", _fact_node_modules),
    ("venv", _fact_venv),
    (".venv", _fact_venv),
    (".git", _fact_git),
    ("overlay2", _fact_docker),
    ("volumes", _fact_docker),
    (".trash", _fact_trash),
    ("trash", _fact_trash),
]


def collect_facts(path: Path) -> list:
    out: list = []
    for name, fn in INTERNAL_FACTS:
        if path.name == name:
            try:
                out.extend(fn(path))
            except Exception:
                continue
    return out


def load_external_facts() -> list:
    fns = []
    if not FACTS_DIR.is_dir():
        return fns
    for file in sorted(FACTS_DIR.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(file.stem, file)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[file.stem] = mod
            spec.loader.exec_module(mod)
            fns.extend(mod.FACTS)
        except Exception:
            continue
    return fns


EXTERNAL_FACTS = load_external_facts()
