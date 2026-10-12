"""storager CLI — entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .classifier import ClassifiedEntry, classify, suggest_default_risk_filter
from .deleter import delete_entries
from .interactive import prompt_selection, render_table
from .rules import add_rule, load_rules, match_rule, remove_rule
from .scanner import human_size, scan_immediate_children, scan_path_deep


BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"


def _banner() -> None:
    print(f"{BOLD}storager{RESET} {DIM}v{__version__}{RESET}")
    print(f"{DIM}Pure-algorithm disk analyser — no AI, no network.{RESET}\n")


_SIZE_UNITS = {
    "k": 1024, "kb": 1024, "kib": 1024,
    "m": 1024**2, "mb": 1024**2, "mib": 1024**2,
    "g": 1024**3, "gb": 1024**3, "gib": 1024**3,
    "t": 1024**4, "tb": 1024**4, "tib": 1024**4,
}


def parse_size(raw: str) -> int | None:
    """Parse '5G', '500M', '2.5gb', '1024' → bytes. Returns None on failure."""
    s = raw.strip().lower().replace(" ", "")
    if not s:
        return None
    # split number and unit
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


def prompt_target_bytes() -> int | None:
    """Ask the user how much space they want to free. None = no target."""
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


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"{RED}Path does not exist: {root}{RESET}", file=sys.stderr)
        return 1

    _banner()
    print(f"{BOLD}Scanning:{RESET} {root}\n")
    print(f"{DIM}Measuring sizes… this may take a moment on large trees.{RESET}\n")

    children = scan_immediate_children(root, top_n=args.top)
    if not children:
        print("No items found (or permission denied).")
        return 0

    classified: list[ClassifiedEntry] = [classify(c) for c in children]

    # apply saved rules
    rules = load_rules()
    for ce in classified:
        rule = match_rule(str(ce.entry.path), ce.category, rules)
        if rule and rule.action == "ignore":
            ce.label = f"[ignored by rule] {ce.label}"

    total = sum(c.size for c in children)
    print(f"{BOLD}Top items by size{RESET}  (total measured: {human_size(total)})")
    render_table(classified, show_all=args.all)

    print(f"{DIM}Tip: run `storager clean {root}` to interactively delete.{RESET}")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"{RED}Path does not exist: {root}{RESET}", file=sys.stderr)
        return 1

    _banner()
    print(f"{BOLD}Cleaning session for:{RESET} {root}\n")

    # 1. Ask the target first (or use --target / --no-prompt)
    target_bytes: int | None = None
    if getattr(args, "target", None):
        target_bytes = parse_size(args.target)
    if target_bytes is None and not getattr(args, "no_prompt", False):
        target_bytes = prompt_target_bytes()

    children = scan_immediate_children(root, top_n=args.top)
    if not children:
        print("No items found.")
        return 0

    classified: list[ClassifiedEntry] = [classify(c) for c in children]

    # auto-apply saved "always delete" rules
    rules = load_rules()
    auto_selected: list[ClassifiedEntry] = []
    for ce in classified:
        rule = match_rule(str(ce.entry.path), ce.category, rules)
        if rule and rule.action == "delete":
            auto_selected.append(ce)

    freed_running = 0
    if auto_selected:
        auto_total = sum(e.entry.size for e in auto_selected)
        print(f"{YELLOW}Applying {len(auto_selected)} saved 'always delete' rule(s){RESET} "
              f"({human_size(auto_total)}).\n")
        render_table(auto_selected, show_all=True)
        confirm = input(f"{BOLD}Delete these now? [y/N]:{RESET} ").strip().lower()
        if confirm == "y":
            results = delete_entries([e.entry.path for e in auto_selected], use_trash=not args.hard)
            _print_results(results)
            freed_running += sum(r.freed_bytes for r in results if r.ok)
        print()

    # interactive pass on the rest — loop until target met or user quits
    remaining = [ce for ce in classified if ce not in auto_selected]

    while True:
        if target_bytes is not None:
            pct = min(100.0, freed_running / target_bytes * 100)
            print(f"{BOLD}Progress:{RESET} {human_size(freed_running)} / {human_size(target_bytes)}  ({pct:.0f}%)")
            if freed_running >= target_bytes:
                print(f"{GREEN}Target reached.{RESET} You can stop here or keep going.")
            print()

        selected, mode = prompt_selection(remaining)
        if not selected:
            break

        results = delete_entries([e.entry.path for e in selected], use_trash=not args.hard)
        _print_results(results)
        freed_running += sum(r.freed_bytes for r in results if r.ok)

        if mode == "always":
            print(f"\n{BOLD}Saving 'always delete' rules…{RESET}")
            for ce in selected:
                glob = str(ce.entry.path)
                add_rule(ce.category, glob, "delete")
                print(f"  + rule: category={ce.category}  glob={glob}")
            print(f"{DIM}Rules stored in ~/.config/storager/rules.json{RESET}")

        # remove selected from remaining so we don't offer them again
        selected_paths = {id(ce) for ce in selected}
        remaining = [ce for ce in remaining if id(ce) not in selected_paths]

        if target_bytes is not None and freed_running >= target_bytes:
            more = input(f"\n{BOLD}Target met. Delete more? [y/N]:{RESET} ").strip().lower()
            if more != "y":
                break
        if not remaining:
            break

    print(f"\n{GREEN}Freed approximately {human_size(freed_running)} this session.{RESET}")
    if target_bytes is not None:
        pct = min(100.0, freed_running / target_bytes * 100)
        print(f"{DIM}Target was {human_size(target_bytes)} — {pct:.0f}% achieved.{RESET}")
    return 0


def _print_results(results) -> None:
    for r in results:
        tag = f"{GREEN}ok{RESET}" if r.ok else f"{RED}fail{RESET}"
        print(f"  [{tag}] {r.path}  — {r.message}")


def cmd_rules(args: argparse.Namespace) -> int:
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


def cmd_version(_: argparse.Namespace) -> int:
    print(f"storager {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="storager",
        description="Pure-algorithm disk space analyser. Finds what is eating your disk, "
                    "names it in plain language, and lets you pick what to delete.",
    )
    p.add_argument("--version", action="version", version=f"storager {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Scan a directory and list biggest items")
    scan_p.add_argument("path", nargs="?", default=".", help="Directory to scan (default: cwd)")
    scan_p.add_argument("--top", type=int, default=30, help="Max items to show")
    scan_p.add_argument("--all", action="store_true", help="Show risky items too")
    scan_p.set_defaults(func=cmd_scan)

    clean_p = sub.add_parser("clean", help="Interactively select and delete items")
    clean_p.add_argument("path", nargs="?", default=".", help="Directory to clean (default: cwd)")
    clean_p.add_argument("--top", type=int, default=50, help="Max items to consider")
    clean_p.add_argument("--hard", action="store_true", help="Permanently delete (skip Trash)")
    clean_p.add_argument("--target", help="Target free space, e.g. 5G / 500M / 2T (skip the prompt)")
    clean_p.add_argument("--no-prompt", action="store_true", help="Skip the target question entirely")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]

    known = {"scan", "clean", "rules", "version"}
    # bare `storager` or `storager <path>` → default to clean
    if not argv:
        argv = ["clean"]
    elif argv[0] not in known and not argv[0].startswith("-"):
        argv = ["clean"] + argv

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
