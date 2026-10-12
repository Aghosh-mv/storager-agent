"""Interactive selection — lets the user pick what to delete, and choose always vs this-time."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from .classifier import ClassifiedEntry
from .scanner import human_size


RISK_COLORS = {
    "safe": "\033[92m",          # green
    "probably-safe": "\033[93m", # yellow
    "risky": "\033[91m",         # red
    "unknown": "\033[90m",       # grey
}
RESET = "\033[0m"
BOLD = "\033[1m"


def render_table(entries: List[ClassifiedEntry], *, show_all: bool = False) -> None:
    visible = entries if show_all else [e for e in entries if e.risk in ("safe", "probably-safe", "risky")]
    if not visible:
        print("  (nothing to show)")
        return
    print()
    idx_width = len(str(len(visible)))
    for i, ce in enumerate(visible, 1):
        color = RISK_COLORS.get(ce.risk, "")
        size = ce.entry.size_str
        marker = "d" if ce.entry.is_dir else "f"
        print(
            f"  {color}{BOLD}[{i:>{idx_width}}]{RESET} "
            f"{color}{size:>10}{RESET}  "
            f"{ce.label}  "
            f"({ce.category}, {ce.risk}, {marker})"
        )
        print(f"       {ce.reason}")
        print(f"       {ce.entry.path}")
        print()


def parse_selection(raw: str, max_index: int) -> List[int]:
    """Parse '1,3-5,8' into [1,3,4,5,8]."""
    chosen = set()
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            try:
                lo, hi = int(a), int(b)
                for n in range(lo, hi + 1):
                    if 1 <= n <= max_index:
                        chosen.add(n)
            except ValueError:
                continue
        else:
            try:
                n = int(part)
                if 1 <= n <= max_index:
                    chosen.add(n)
            except ValueError:
                continue
    return sorted(chosen)


def prompt_selection(entries: List[ClassifiedEntry]) -> Tuple[List[ClassifiedEntry], str]:
    """
    Returns (selected_entries, mode) where mode is 'always' or 'once'.
    """
    visible = [e for e in entries if e.risk in ("safe", "probably-safe", "risky")]
    if not visible:
        print("Nothing selected.")
        return [], "once"

    print(f"\n{BOLD}How many to show?{RESET}")
    print("  [1] Only safe items (recommended)")
    print("  [2] Safe + probably-safe")
    print("  [3] Everything including risky")
    scope = input("  Choice [1]: ").strip() or "1"

    if scope == "2":
        visible = [e for e in visible if e.risk in ("safe", "probably-safe")]
    elif scope == "3":
        pass  # keep all
    else:
        visible = [e for e in visible if e.risk == "safe"]

    if not visible:
        print("Nothing matches that filter.")
        return [], "once"

    render_table(visible, show_all=True)

    print(f"{BOLD}Select items to delete.{RESET}")
    print("  Examples: 1,3,5   |   1-4   |   all   |   none")
    raw = input("  > ").strip().lower()

    if raw in ("none", "n", ""):
        return [], "once"
    if raw in ("all", "a"):
        indices = list(range(1, len(visible) + 1))
    else:
        indices = parse_selection(raw, len(visible))

    selected = [visible[i - 1] for i in indices]
    if not selected:
        print("Nothing selected.")
        return [], "once"

    total = sum(e.entry.size for e in selected)
    print(f"\n  Selected {len(selected)} item(s), total {human_size(total)}.")

    print(f"\n{BOLD}Delete how?{RESET}")
    print("  [1] Only this time")
    print("  [2] Always (save a rule so storager auto-deletes these next time)")
    mode_choice = input("  Choice [1]: ").strip() or "1"
    mode = "always" if mode_choice == "2" else "once"

    return selected, mode
