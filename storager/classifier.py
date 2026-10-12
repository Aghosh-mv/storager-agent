from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .scanner import DiskEntry, human_size


@dataclass
class ClassifiedEntry:
    entry: DiskEntry
    label: str
    category: str
    risk: str
    reason: str
    summary: str = ""
    facts: list = field(default_factory=list)
    relations: list = field(default_factory=list)


_RULES = [
    ("cache", "safe", "App cache — safe to clear", lambda e: e.path.name.lower() in {
        "caches", ".cache", "cache", "cacheddata", "cached_data",
        "library/caches", "appdata/local/cache",
    }),
    ("cache", "safe", "Browser cache", lambda e: any(
        x in e.path.name.lower() for x in ("chromium", "chrome", "firefox", "safari", "brave", "edge")
    ) and "cache" in e.path.name.lower()),
    ("cache", "safe", "Package-manager cache (npm, pip, cargo…)", lambda e: e.path.name.lower() in {
        ".npm", ".yarn", ".cargo/registry", ".cargo/git", ".pub-cache", ".gradle/caches",
        ".m2", ".nuget", ".bundler", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".tox", "pip/cache",
    }),
    ("log", "safe", "Log files — usually safe to delete", lambda e: (
        e.path.name.lower().endswith((".log", ".log.1", ".log.gz"))
        or e.path.name.lower() in {"logs", "log", "var/log"}
    )),
    ("log", "safe", "Crash reports / diagnostic dumps", lambda e: any(
        x in e.path.name.lower() for x in ("crash", "diagnostic", "symptom", "report", "telemetry")
    )),
    ("trash", "safe", "Trash / Recycle Bin — already deleted by you", lambda e: e.path.name.lower() in {
        ".trash", ".trash-1000", "$recycle.bin", "recycle.bin", ".local/share/trash",
    }),
    ("download", "probably-safe", "Downloaded files (installers, zips, images…)", lambda e: (
        e.path.name.lower() in {"downloads", "download"} or e.path.suffix.lower() in {
            ".dmg", ".pkg", ".exe", ".msi", ".zip", ".tar", ".tar.gz", ".tgz", ".7z", ".rar",
            ".iso", ".img",
        }
    )),
    ("build", "probably-safe", "Build output / compiled artifacts (rebuildable)", lambda e: (
        e.path.name.lower() in {
            "build", "dist", "out", "target", "bin/obj", "__pycache__", ".next", ".nuxt",
            ".output", ".turbo", ".parcel-cache", ".webpack", ".rollup.cache",
            "cmake-build-debug", "cmake-build-release",
        }
        or e.path.name.lower().endswith(".egg-info")
    )),
    ("build", "probably-safe", "node_modules — reinstall with npm install", lambda e: (
        e.path.name.lower() == "node_modules"
    )),
    ("project", "risky", "Old project folder (has code — review before deleting)", lambda e: (
        any(e.path.name.lower().endswith(ext) for ext in (".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp"))
    )),
    ("media", "risky", "Photo / video / music file", lambda e: e.path.suffix.lower() in {
        ".jpg", ".jpeg", ".png", ".heic", ".raw", ".cr2", ".nef",
        ".mp4", ".mov", ".avi", ".mkv", ".m4v",
        ".mp3", ".wav", ".flac", ".m4a", ".aac",
    }),
    ("vm", "risky", "Virtual machine / container disk image", lambda e: (
        e.path.suffix.lower() in {".vdi", ".vmdk", ".vhd", ".vhdx", ".qcow2", ".img"}
        or "docker" in e.path.name.lower() and "disk" in e.path.name.lower()
        or "vm" in e.path.name.lower() and "bundle" in e.path.name.lower()
    )),
    ("db", "risky", "Database file", lambda e: e.path.suffix.lower() in {
        ".db", ".sqlite", ".sqlite3", ".mdb",
    }),
    ("unknown", "unknown", "Large file (no clear category)", lambda e: not e.is_dir),
    ("unknown", "unknown", "Large folder (no clear category)", lambda e: e.is_dir),
]


def classify(entry: DiskEntry) -> ClassifiedEntry:
    for category, risk, label, pred in _RULES:
        try:
            if pred(entry):
                return ClassifiedEntry(
                    entry=entry, label=label, category=category, risk=risk,
                    reason=_reason(category, entry),
                )
        except Exception:
            continue
    return ClassifiedEntry(
        entry=entry, label="Unclassified item", category="unknown",
        risk="unknown", reason="storager could not identify what this is.",
    )


def _reason(category: str, entry: DiskEntry) -> str:
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
