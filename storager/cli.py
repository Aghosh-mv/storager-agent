"""storager CLI — thin orchestrator over the analysis pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .confirm import confirm_deletion
from .deleter import delete_entries
from .interactive import prompt_selection
from .pipeline import analyze, configure
from .present import render_problems, render_table
from .report import print_results, print_summary
from .rules import add_rule, load_rules, match_rule, remove_rule
from .scanner import human_size
from .session import Flags, Session

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"

_SIZE_UNITS = {
    "k": 1024, "kb": 1024, "kib": 1024,
    "m": 1024**2, "mb": 1024**2, "mib": 1024**2,
    "g": 1024**3, "gb": 1024**3, "gib": 1024**3,
    "t": 1024**4, "tb": 1024**4, "tib": 1024**4,
}


def parse_size(raw: str):
    s = raw.strip().lower().replace(" ", "")
    if not s:
        return None
    i = 0
    while i < len(s) and (s[i].isdigit() or s[i] == "."):
        i += 1
    num_str, unit = s[:i], s[i:]
    if not num_str:
        return None
    try:
        num = float(num_str)
    except ValueError:
        return None
    if unit == "" or unit == "b":
        return int(num)
    mult = _SIZE_UNITS.get(unit)
    if mult is None:
        return None
    return int(num * mult)


def parse_parallel(raw: str) -> str:
    if raw in ("auto", "sequential"):
        return raw
    try:
        n = int(raw)
        return str(max(1, min(n, 32)))
    except (TypeError, ValueError):
        return "auto"


def prompt_target_bytes():
    print(f"{BOLD}How much disk space do you want to free?{RESET}")
    print(f"  {DIM}Examples: 5G   500M   2T   1024   (or press Enter for no target){RESET}")
    raw = input("  > ").strip()
    if not raw:
        return None
    target = parse_size(raw)
    if target is None or target <= 0:
        print(f"  {YELLOW}Could not parse that — continuing without a target.{RESET}")
        return None
    print(f"  {GREEN}Target: {human_size(target)}{RESET}\n")
    return target


def _banner() -> None:
    print(f"{BOLD}storager{RESET} {DIM}v{__version__}{RESET}")
    print(f"{DIM}Pure-algorithm disk analyser — no AI, no network.{RESET}\n")


def _make_session(args) -> Session:
    root = Path(args.path).expanduser().resolve()
    target = parse_size(args.target) if getattr(args, "target", None) else None
    flags = Flags(
        trace=getattr(args, "trace", False),
        parallel=parse_parallel(getattr(args, "parallel", "auto")),
        deep=getattr(args, "deep", False),
        hard=getattr(args, "hard", False),
        no_prompt=getattr(args, "no_prompt", False),
        all=getattr(args, "all", False),
    )
    return Session(root=root, target_bytes=target, flags=flags)


def cmd_scan(args) -> int:
    session = _make_session(args)
    if not session.root.exists():
        print(f"{RED}Path does not exist: {session.root}{RESET}", file=sys.stderr)
        return 1
    _banner()
    print(f"{BOLD}Scanning:{RESET} {session.root}\n")
    configure(session.flags.trace)
    analyze(session, top_n=args.top)
    render_problems(session.problems)
    total = sum(e.size for e in session.entries)
    print(f"{BOLD}Biggest items{RESET} (total measured: {human_size(total)})")
    render_table(session.classified, session.reports, session.relations, show_all=session.flags.all)
    print(f"{DIM}Tip: run `storager clean {session.root}` to delete.{RESET}")
    return 0


def cmd_clean(args) -> int:
    session = _make_session(args)
    if not session.root.exists():
        print(f"{RED}Path does not exist: {session.root}{RESET}", file=sys.stderr)
        return 1
    _banner()
    print(f"{BOLD}Cleaning session for:{RESET} {session.root}\n")
    configure(session.flags.trace)

    if session.target_bytes is None and not session.flags.no_prompt:
        session.target_bytes = prompt_target_bytes()

    analyze(session, top_n=args.top)
    render_problems(session.problems)

    rules = load_rules()
    auto = [
        ce for ce in session.classified
        if (r := match_rule(str(ce.entry.path), ce.category, rules)) and r.action == "delete"
    ]
    deleted_paths: set = set()
    if auto:
        print(f"{YELLOW}Saved 'always delete' rules matched {len(auto)} item(s):{RESET}")
        render_table(auto, session.reports, session.relations, show_all=True)
        if confirm_deletion(auto, hard=session.flags.hard):
            results = delete_entries([ce.entry.path for ce in auto], use_trash=not session.flags.hard)
            print_results(results)
            session.freed += sum(r.freed_bytes for r in results if r.ok)
            for r in results:
                deleted_paths.add(r.path)
        print()

    remaining = [ce for ce in session.classified if ce.entry.path not in deleted_paths]

    while True:
        if session.target_bytes is not None:
            pct = min(100.0, session.freed / session.target_bytes * 100)
            print(f"{BOLD}Progress:{RESET} {human_size(session.freed)} / {human_size(session.target_bytes)} ({pct:.0f}%)")
            if session.freed >= session.target_bytes:
                print(f"{GREEN}Target reached.{RESET} You can stop or keep going.")
            print()

        selected, mode = prompt_selection(remaining)
        if not selected:
            break

        if not confirm_deletion(selected, hard=session.flags.hard):
            print(f"{YELLOW}Cancelled — nothing deleted. Pick different items or type 'none'.{RESET}\n")
            continue

        results = delete_entries([ce.entry.path for ce in selected], use_trash=not session.flags.hard)
        print_results(results)
        session.freed += sum(r.freed_bytes for r in results if r.ok)
        for r in results:
            deleted_paths.add(r.path)

        if mode == "always":
            print(f"\n{BOLD}Saving 'always delete' rules…{RESET}")
            for ce in selected:
                add_rule(ce.category, str(ce.entry.path), "delete")
                print(f"  + rule: category={ce.category}  glob={ce.entry.path}")
            print(f"{DIM}Rules stored in ~/.config/storager/rules.json{RESET}")

        remaining = [ce for ce in remaining if ce.entry.path not in deleted_paths]

        if session.target_bytes is not None and session.freed >= session.target_bytes:
            more = input(f"\n{BOLD}Target met. Delete more? [y/N]:{RESET} ").strip().lower()
            if more != "y":
                break
        if not remaining:
            break

    print_summary(session)
    return 0


def cmd_rules(args) -> int:
    rules = load_rules()
    if args.add_category and args.add_glob:
        add_rule(args.add_category, args.add_glob, args.add_action or "delete")
        print("Rule added.")
        return 0
    if args.remove is not None:
        if remove_rule(args.remove):
            print("Rule removed.")
        else:
            print("Invalid index.", file=sys.stderr)
            return 1
        return 0

    if not rules:
        print("No saved rules.")
        return 0
    print(f"{BOLD}Saved rules ({len(rules)}):{RESET}")
    for i, r in enumerate(rules):
        print(f"  [{i}] {r.action:8}  category={r.category:12}  glob={r.path_glob}")
    return 0


def cmd_version(_) -> int:
    print(f"storager {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="storager",
        description="Pure-algorithm disk space analyser. Scans, inspects, classifies, "
                    "diagnoses, explains in plain language, and always asks before deleting.",
    )
    p.add_argument("--version", action="version", version=f"storager {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Scan a directory and list biggest items")
    scan_p.add_argument("path", nargs="?", default=".", help="Directory to scan (default: cwd)")
    scan_p.add_argument("--top", type=int, default=30, help="Max items to show")
    scan_p.add_argument("--all", action="store_true", help="Show risky items too")
    scan_p.add_argument("--trace", action="store_true", help="Print stage timing")
    scan_p.add_argument("--parallel", default="auto", help="auto | sequential | 1-32")
    scan_p.set_defaults(func=cmd_scan)

    clean_p = sub.add_parser("clean", help="Interactively select and delete items")
    clean_p.add_argument("path", nargs="?", default=".", help="Directory to clean (default: cwd)")
    clean_p.add_argument("--top", type=int, default=50, help="Max items to consider")
    clean_p.add_argument("--target", help="Target free space, e.g. 5G / 500M / 2T (skip the prompt)")
    clean_p.add_argument("--no-prompt", action="store_true", help="Skip the target question entirely")
    clean_p.add_argument("--hard", action="store_true", help="Permanently delete (skip Trash)")
    clean_p.add_argument("--trace", action="store_true", help="Print stage timing")
    clean_p.add_argument("--parallel", default="auto", help="auto | sequential | 1-32")
    clean_p.set_defaults(func=cmd_clean)

    rules_p = sub.add_parser("rules", help="List / add / remove persistent rules")
    rules_p.add_argument("--add-category", help="Category for a new rule")
    rules_p.add_argument("--add-glob", help="Path glob for a new rule")
    rules_p.add_argument("--add-action", choices=["delete", "ignore"], default="delete")
    rules_p.add_argument("--remove", type=int, help="Index of rule to remove")
    rules_p.set_defaults(func=cmd_rules)

    ver_p = sub.add_parser("version", help="Print version")
    ver_p.set_defaults(func=cmd_version)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    known = {"scan", "clean", "rules", "version"}
    if not argv:
        argv = ["clean"]
    elif argv[0] not in known and not argv[0].startswith("-"):
        argv = ["clean"] + argv
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
