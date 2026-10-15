from __future__ import annotations

from .present import render_table
from .scanner import human_size

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def parse_selection(raw: str, max_index: int) -> list:
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


def prompt_selection(classified) -> tuple:
    if not classified:
        print("Nothing to delete here.")
        return [], "once"

    print(f"\n{BOLD}Show which items?{RESET}")
    print("  [1] Only safe (recommended)")
    print("  [2] Safe + probably-safe")
    print("  [3] Everything including risky")
    scope = input("  Choice [1]: ").strip() or "1"
    if scope == "2":
        visible = [ce for ce in classified if ce.risk in ("safe", "probably-safe")]
    elif scope == "3":
        visible = list(classified)
    else:
        visible = [ce for ce in classified if ce.risk == "safe"]

    if not visible:
        print("Nothing matches that filter.")
        return [], "once"

    render_table(visible, {}, {}, show_all=True)

    print(f"{BOLD}Select items to delete.{RESET}")
    print("  Examples: 1,3,5   |   1-4   |   all   |   none")
    raw = input("  > ").strip().lower()

    if raw in ("none", "n", ""):
        return [], "once"
    indices = list(range(1, len(visible) + 1)) if raw in ("all", "a") else parse_selection(raw, len(visible))
    selected = [visible[i - 1] for i in indices]
    if not selected:
        print("Nothing selected.")
        return [], "once"

    total = sum(ce.entry.size for ce in selected)
    print(f"\n  Selected {len(selected)} item(s), {human_size(total)}.")

    print(f"\n{BOLD}Delete how?{RESET}")
    print("  [1] Only this time")
    print("  [2] Always (save a rule so storager auto-deletes these next time)")
    mode_choice = input("  Choice [1]: ").strip() or "1"
    mode = "always" if mode_choice == "2" else "once"

    return selected, mode
