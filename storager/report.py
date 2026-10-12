from __future__ import annotations

from .scanner import human_size

GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def print_results(results) -> None:
    for r in results:
        tag = f"{GREEN}ok{RESET}" if r.ok else f"{RED}fail{RESET}"
        print(f"  [{tag}] {r.path}  — {r.message}")


def print_summary(session) -> None:
    freed = session.freed
    print(f"\n{GREEN}Freed approximately {human_size(freed)} this session.{RESET}")
    if session.target_bytes is not None:
        pct = min(100.0, freed / session.target_bytes * 100)
        print(f"{DIM}Target was {human_size(session.target_bytes)} — {pct:.0f}% achieved.{RESET}")
    if session.problems:
        print(f"{DIM}Re-run `storager scan {session.root}` to check progress.{RESET}")
