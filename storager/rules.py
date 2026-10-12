"""Persistent rules — 'always delete' vs 'this time only'."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

CONFIG_DIR = Path.home() / ".config" / "storager"
RULES_FILE = CONFIG_DIR / "rules.json"


@dataclass
class Rule:
    category: str       # classifier category, e.g. "cache", "log"
    path_glob: str      # glob pattern matched against the entry path
    action: str         # "delete" or "ignore"
    created_at: str = ""


def load_rules() -> List[Rule]:
    if not RULES_FILE.exists():
        return []
    try:
        data = json.loads(RULES_FILE.read_text())
        return [Rule(**r) for r in data]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


def save_rules(rules: List[Rule]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(json.dumps([asdict(r) for r in rules], indent=2))


def add_rule(category: str, path_glob: str, action: str) -> Rule:
    import datetime
    rule = Rule(
        category=category,
        path_glob=path_glob,
        action=action,
        created_at=datetime.datetime.now().isoformat(),
    )
    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    return rule


def match_rule(path_str: str, category: str, rules: Optional[List[Rule]] = None) -> Optional[Rule]:
    from fnmatch import fnmatch
    if rules is None:
        rules = load_rules()
    for rule in rules:
        if fnmatch(path_str, rule.path_glob):
            return rule
        # also match if the category matches and glob is broad
        if rule.path_glob in ("*", "**") and rule.category == category:
            return rule
    return None


def remove_rule(index: int) -> bool:
    rules = load_rules()
    if 0 <= index < len(rules):
        rules.pop(index)
        save_rules(rules)
        return True
    return False
