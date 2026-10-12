from __future__ import annotations

from .scanner import human_size

BOLD = "\033[1m"
RESET = "\033[0m"
YELLOW = "\033[93m"


def confirm_deletion(selected, hard: bool = False) -> bool:
    total = sum(ce.entry.size for ce in selected)
    mode = "permanently delete" if hard else "move to Trash"
    print(f"\nAbout to {mode} {len(selected)} item(s), {human_size(total)}:")
    for ce in selected:
        print(f"  - {ce.entry.size_str:>10}  {ce.entry.path}")
    print("\nstorager always asks before deleting. There is no flag to skip this.")
    ans = input("Type 'yes' to confirm: ").strip().lower()
    return ans == "yes"
