from __future__ import annotations

import time

from .inspector import ItemReport

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"

RISK_COLORS = {
    "safe": GREEN,
    "probably-safe": YELLOW,
    "risky": RED,
    "unknown": "\033[90m",
}


def age_str(days: float) -> str:
    if days < 1:
        return "today"
    if days < 30:
        return f"{int(days)} days"
    if days < 365:
        return f"{int(days // 30)} months"
    return f"{days / 365:.1f} years"


def summarize_report(rep: ItemReport) -> str:
    if not rep or rep.error:
        return ""
    parts = []
    if rep.files or rep.dirs:
        parts.append(f"{rep.files:,} files, {rep.dirs:,} folders")
        top = sorted(rep.by_ext.items(), key=lambda kv: kv[1], reverse=True)[:3]
        if top:
            parts.append("mostly " + ", ".join(f".{e} ({n:,})" for e, n in top))
    if rep.newest:
        parts.append(f"last touched {age_str((time.time() - rep.newest) / 86400)} ago")
    return " · ".join(parts)


def render_problems(problems) -> None:
    if not problems:
        return
    print(f"{BOLD}storager noticed:{RESET}")
    for p in problems:
        color = RED if p.severity == "critical" else YELLOW if p.severity == "warn" else DIM
        loc = f"  ({p.path})" if p.path else ""
        print(f"  {color}!{RESET} {p.message}{DIM}{loc}{RESET}")
    print()


def render_table(classified, reports, relations, show_all: bool = False) -> None:
    visible = list(classified) if show_all else [ce for ce in classified if ce.risk in ("safe", "probably-safe", "risky")]
    if not visible:
        print("  (nothing to show)")
        return
    print()
    width = len(str(len(visible)))
    for i, ce in enumerate(visible, 1):
        color = RISK_COLORS.get(ce.risk, "")
        marker = "D" if ce.entry.is_dir else "f"
        print(f"  {color}{BOLD}[{i:>{width}}]{RESET} {color}{ce.entry.size_str:>10}{RESET}  {ce.label}  ({ce.risk}, {marker})")
        print(f"       {ce.reason}")
        s = summarize_report(reports.get(str(ce.entry.path)))
        if s:
            print(f"       {DIM}inside:{RESET} {s}")
        for fact in ce.facts[:2]:
            print(f"       {DIM}note:{RESET} {fact}")
        for rel in ce.relations[:2]:
            print(f"       {YELLOW}also affects:{RESET} {rel}")
        print(f"       {DIM}{ce.entry.path}{RESET}")
        print()
