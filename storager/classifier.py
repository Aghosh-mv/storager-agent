"""Classifier — names disk entries in plain human language using pure heuristics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .scanner import DiskEntry


@dataclass
class ClassifiedEntry:
    entry: DiskEntry
    label: str          # plain-language name
    category: str       # e.g. "cache", "download", "project", "log"
    risk: str           # "safe", "probably-safe", "risky", "unknown"
    reason: str         # one-line explanation


# Ordered rules: first match wins.
# Each rule: (category, risk, label_template, predicate)
# predicate(entry: DiskEntry) -> bool

def _name(p: Path) -> str:
    return p.name.lower()


_RULES = [
    # ---- caches ----
    ("cache", "safe", "App cache — safe to clear", lambda e: _name(e.path) in {
        "caches", ".cache", "cache", "cacheddata", "cached_data",
        "library/caches", "appdata/local/cache",
    }),
    ("cache", "safe", "Browser cache", lambda e: any(
        x in _name(e.path) for x in ("chromium", "chrome", "firefox", "safari", "brave", "edge")
    ) and "cache" in _name(e.path)),
    ("cache", "safe", "Package-manager cache (npm, pip, cargo…)", lambda e: _name(e.path) in {
        ".npm", ".yarn", ".cargo/registry", ".cargo/git", ".pub-cache", ".gradle/caches",
        ".m2", ".nuget", ".bundler", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".tox", "pip/cache",
    }),

    # ---- logs ----
    ("log", "safe", "Log files — usually safe to delete", lambda e: (
        _name(e.path).endswith((".log", ".log.1", ".log.gz"))
        or _name(e.path) in {"logs", "log", "var/log"}
    )),
    ("log", "safe", "Crash reports / diagnostic dumps", lambda e: any(
        x in _name(e.path) for x in ("crash", "diagnostic", "symptom", "report", "telemetry")
    )),

    # ---- trash / recycle ----
    ("trash", "safe", "Trash / Recycle Bin — already deleted by you", lambda e: _name(e.path) in {
        ".trash", ".trash-1000", "$recycle.bin", "recycle.bin", ".local/share/trash",
    }),

    # ---- downloads ----
    ("download", "probably-safe", "Downloaded files (installers, zips, images…)", lambda e: (
        _name(e.path) in {"downloads", "download"} or e.path.suffix.lower() in {
            ".dmg", ".pkg", ".exe", ".msi", ".zip", ".tar", ".tar.gz", ".tgz", ".7z", ".rar",
            ".iso", ".img",
        }
    )),

    # ---- build artifacts ----
    ("build", "probably-safe", "Build output / compiled artifacts (rebuildable)", lambda e: (
        _name(e.path) in {
            "build", "dist", "out", "target", "bin/obj", "__pycache__", ".next", ".nuxt",
            ".output", ".turbo", ".parcel-cache", ".webpack", ".rollup.cache",
            "cmake-build-debug", "cmake-build-release",
        }
        or _name(e.path).endswith(".egg-info")
    )),
    ("build", "probably-safe", "node_modules — reinstall with npm install", lambda e: (
        _name(e.path) == "node_modules"
    )),

    # ---- old app / project dirs ----
    ("project", "risky", "Old project folder (has code — review before deleting)", lambda e: (
        any(_name(e.path).endswith(ext) for ext in (".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp"))
    )),

    # ---- media ----
    ("media", "risky", "Photo / video / music file", lambda e: e.path.suffix.lower() in {
        ".jpg", ".jpeg", ".png", ".heic", ".raw", ".cr2", ".nef",
        ".mp4", ".mov", ".avi", ".mkv", ".m4v",
        ".mp3", ".wav", ".flac", ".m4a", ".aac",
    }),

    # ---- virtual machines / containers ----
    ("vm", "risky", "Virtual machine / container disk image", lambda e: (
        e.path.suffix.lower() in {".vdi", ".vmdk", ".vhd", ".vhdx", ".qcow2", ".img"}
        or "docker" in _name(e.path) and "disk" in _name(e.path)
        or "vm" in _name(e.path) and "bundle" in _name(e.path)
    )),

    # ---- databases ----
    ("db", "risky", "Database file", lambda e: e.path.suffix.lower() in {
        ".db", ".sqlite", ".sqlite3", ".mdb",
    }),

    # ---- generic large file ----
    ("unknown", "unknown", "Large file (no clear category)", lambda e: not e.is_dir),
    ("unknown", "unknown", "Large folder (no clear category)", lambda e: e.is_dir),
]


def classify(entry: DiskEntry) -> ClassifiedEntry:
    for category, risk, label, pred in _RULES:
        try:
            if pred(entry):
                return ClassifiedEntry(entry=entry, label=label, category=category, risk=risk, reason=_reason(category, entry))
        except Exception:
            continue
    return ClassifiedEntry(
        entry=entry, label="Unclassified item", category="unknown",
        risk="unknown", reason="Could not categorise this item.",
    )


def _reason(category: str, entry: DiskEntry) -> str:
    size = entry.entry.size_str if hasattr(entry, "entry") else "unknown size"
    reasons = {
        "cache": "Caches are regenerated automatically by apps.",
        "log": "Logs are records of past events; apps rewrite them.",
        "trash": "Items here were already marked for deletion.",
        "download": "Files you downloaded; you may not need them anymore.",
        "build": "Compiled output; can be rebuilt from source.",
        "project": "Contains source code — you may want to keep it.",
        "media": "Photos, videos or music — personal files.",
        "vm": "Virtual machine image; deleting it removes the whole VM.",
        "db": "Database file; deleting it destroys the data inside.",
        "unknown": "storager could not identify what this is.",
    }
    return reasons.get(category, "No description available.")


def suggest_default_risk_filter(entries: list[ClassifiedEntry]) -> list[ClassifiedEntry]:
    """Return only entries that are safe or probably-safe (for a quick clean)."""
    return [e for e in entries if e.risk in ("safe", "probably-safe")]
