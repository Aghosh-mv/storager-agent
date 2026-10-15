from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROFILE_FILE = Path.home() / ".config" / "storager" / "profile"


@dataclass
class Profile:
    name: str
    description: str
    extra_rules: list = field(default_factory=list)
    default_scope: str = "safe"


def _is_rust_target(e) -> bool:
    return e.path.name.lower() == "target" and (e.path.parent / "Cargo.toml").exists()


def _is_xcode_derived(e) -> bool:
    return e.path.name.lower() == "deriveddata"


def _names(*names: str) -> set:
    return set(n.lower() for n in names)


_PROFILES = {
    "developer": Profile(
        name="developer",
        description="Knows dev artifacts: node_modules, venvs, Rust target, Docker, Xcode DerivedData, Pods, terraform",
        default_scope="probably-safe",
        extra_rules=[
            ("build", "probably-safe", "Python virtualenv — recreate with python -m venv", lambda e: e.path.name.lower() in _names("venv", ".venv", "env", ".env")),
            ("build", "probably-safe", "Rust build output — rebuild with cargo build", _is_rust_target),
            ("build", "probably-safe", "Xcode build data — regenerates on next build", _is_xcode_derived),
            ("build", "probably-safe", "CocoaPods dependencies — reinstall with pod install", lambda e: e.path.name.lower() in _names("pods")),
            ("build", "probably-safe", "Terraform plugins/state — re-init with terraform init", lambda e: e.path.name.lower() in _names(".terraform")),
            ("build", "probably-safe", "Next.js build output — rebuilds on next deploy", lambda e: e.path.name.lower() in _names(".next")),
            ("build", "probably-safe", "Vite / Parcel cache — regenerates", lambda e: e.path.name.lower() in _names(".vite", ".parcel-cache", ".turbo")),
            ("cache", "safe", "Docker data — removing frees space but deletes images/containers", lambda e: e.path.name.lower() in _names(".docker", "docker")),
            ("cache", "safe", "Homebrew cache — re-downloaded on next install", lambda e: e.path.name.lower() in _names("homebrew")),
            ("cache", "safe", "npm cache — re-downloaded", lambda e: e.path.name.lower() in _names(".npm", "_cacache")),
            ("cache", "safe", "Gradle / Maven cache — re-downloaded", lambda e: e.path.name.lower() in _names(".gradle", ".m2")),
        ],
    ),
    "designer": Profile(
        name="designer",
        description="Knows Adobe, Figma, Sketch, fonts, and render caches",
        default_scope="probably-safe",
        extra_rules=[
            ("cache", "safe", "Adobe cache — regenerates on next app launch", lambda e: "adobe" in e.path.name.lower() or "library/caches" in str(e.path).lower()),
            ("cache", "safe", "Figma cache — regenerates", lambda e: "figma" in e.path.name.lower()),
            ("cache", "safe", "Sketch cache — regenerates", lambda e: "sketch" in e.path.name.lower()),
            ("cache", "safe", "Font cache — regenerates", lambda e: "font" in e.path.name.lower() and "cache" in e.path.name.lower()),
            ("build", "probably-safe", "Render / export temp files — regenerates", lambda e: "render" in e.path.name.lower() or "export" in e.path.name.lower()),
            ("cache", "safe", "Application support cache — regenerates", lambda e: "application support" in str(e.path).lower() and "cache" in e.path.name.lower()),
        ],
    ),
    "casual": Profile(
        name="casual",
        description="Conservative — caches, downloads, trash, logs only",
        default_scope="safe",
        extra_rules=[],
    ),
    "minimal": Profile(
        name="minimal",
        description="Only the safest items: caches and trash",
        default_scope="safe",
        extra_rules=[],
    ),
}


def get_profile(name: str):
    return _PROFILES.get(name)


PROFILES = _PROFILES


def active_profile_name() -> str:
    if PROFILE_FILE.exists():
        return PROFILE_FILE.read_text().strip()
    return ""


def set_active_profile(name: str) -> None:
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(name)
