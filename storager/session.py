from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Flags:
    trace: bool = False
    parallel: str = "auto"
    deep: bool = False
    hard: bool = False
    no_prompt: bool = False
    all: bool = False
    dry_run: bool = False
    profile: str = ""


@dataclass
class Session:
    root: Path
    target_bytes: Optional[int] = None
    flags: Flags = field(default_factory=Flags)
    profile: object = None
    entries: list = field(default_factory=list)
    reports: dict = field(default_factory=dict)
    classified: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    relations: dict = field(default_factory=dict)
    freed: int = 0
