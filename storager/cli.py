"""storager CLI — thin orchestrator over the analysis pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .confirm import confirm_deletion
from .deleter import delete_entries
from .interactive import prompt_selection
from .journal import entries_for_batch, history, latest_batch, record_batch, remove_batch
from .pipeline import analyze, configure
from .present import render_problems, render_table
from .profiles import PROFILES, active_profile_name, get_profile, set_active_profile
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
    profile_name = getattr(args, "profile", "") or active_profile_name()
    flags = Flags(
        trace=getattr(args, "trace", False),
        parallel=parse_parallel(getattr(args, "parallel", "auto")),
        deep=getattr(args, "deep", False),
        hard=getattr(args, "hard", False),
        no_prompt=getattr(args, "no_prompt", False),
        all=getattr(args, "all", False),
        dry_run=getattr(args, "dry_run", False),
        profile=profile_name,
    )
    return Session(root=root, target_bytes=target, flags=flags, profile=get_profile(profile_name))


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


def _apply_deletions(session, selected, deleted_paths) -> list:
    paths = [ce.entry.path for ce in selected]
    if session.flags.dry_run:
        results = [
            type("R", (), {"path": p, "ok": True, "message": "DRY RUN — not deleted", "freed_bytes": ce.entry.size})()
            for p, ce in zip(paths, selected)
        ]
        for r in results:
            deleted_paths.add(r.path)
        return results
    results = delete_entries(paths, use_trash=not session.flags.hard)
    for r in results:
        if r.ok:
            deleted_paths.add(r.path)
    return results


def cmd_clean(args) -> int:
    session = _make_session(args)
    if not session.root.exists():
        print(f"{RED}Path does not exist: {session.root}{RESET}", file=sys.stderr)
        return 1
    _banner()
    print(f"{BOLD}Cleaning session for:{RESET} {session.root}\n")
    configure(session.flags.trace)

    if session.flags.dry_run:
        print(f"{YELLOW}DRY RUN — nothing will be deleted. This is a preview only.{RESET}\n")

    if session.profile:
        print(f"{DIM}Profile: {session.profile.name} — {session.profile.description}{RESET}\n")

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
            results = _apply_deletions(session, auto, deleted_paths)
            print_results(results)
            session.freed += sum(r.freed_bytes for r in results if r.ok)
            if not session.flags.dry_run:
                record_batch(results)
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

        results = _apply_deletions(session, selected, deleted_paths)
        print_results(results)
        session.freed += sum(r.freed_bytes for r in results if r.ok)
        if not session.flags.dry_run:
            record_batch(results)

        if mode == "always" and not session.flags.dry_run:
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
    if session.flags.dry_run:
        print(f"{YELLOW}Dry run complete — nothing was deleted.{RESET}")
    return 0


def cmd_undo(args) -> int:
    import shutil
    _banner()
    batch = latest_batch()
    if not batch:
        print("Nothing to undo — no deletions recorded yet.")
        return 0

    rows = entries_for_batch(batch)
    if not rows:
        print("Nothing to undo — no restorable items in the last batch.")
        return 0

    total = sum(r.get("size", 0) for r in rows)
    print(f"{BOLD}Last deletion batch:{RESET} {batch}")
    print(f"{BOLD}Items to restore:{RESET} {len(rows)}  ({human_size(total)})\n")
    for r in rows:
        print(f"  {human_size(r.get('size', 0)):>10}  {r.get('original')}")

    ans = input(f"\n{BOLD}Restore all of these back to their original locations? [y/N]:{RESET} ").strip().lower()
    if ans != "y":
        print("Undo cancelled.")
        return 0

    restored = 0
    failed = 0
    for r in rows:
        dest = Path(r["dest"]) if r.get("dest") else None
        original = Path(r["original"])
        if dest is None or not dest.exists():
            print(f"  {YELLOW}skip{RESET}  {original}  — no longer in Trash")
            failed += 1
            continue
        if original.exists():
            print(f"  {YELLOW}skip{RESET}  {original}  — something already exists there")
            failed += 1
            continue
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(original))
            print(f"  {GREEN}ok{RESET}  {original}")
            restored += 1
        except OSError as e:
            print(f"  {RED}fail{RESET}  {original}  — {e}")
            failed += 1

    if restored:
        remove_batch(batch)
    print(f"\n{GREEN}Restored {restored} item(s).{RESET}" + (f"  {RED}{failed} failed.{RESET}" if failed else ""))
    return 0


def cmd_history(args) -> int:
    _banner()
    rows = history()
    if not rows:
        print("No cleanups recorded yet. Run `storager clean` first.")
        return 0

    rows = list(reversed(rows))
    total = sum(r["size"] for r in rows)
    print(f"{BOLD}Cleanup history{RESET}  ({len(rows)} batch(es), {human_size(total)} freed total)\n")
    for r in rows:
        when = r.get("at") or r["batch"]
        print(f"  {when}  {r['count']:>3} item(s)  {human_size(r['size']):>10}")
    print()
    return 0


def cmd_auto(args) -> int:
    import shutil
    root = Path(args.path).expanduser().resolve()
    _banner()
    try:
        usage = shutil.disk_usage(root)
    except OSError as e:
        print(f"{RED}Could not check disk usage: {e}{RESET}", file=sys.stderr)
        return 1

    pct = usage.used / usage.total * 100
    threshold = args.threshold
    print(f"Disk: {human_size(usage.used)} used / {human_size(usage.total)}  ({pct:.1f}%)")
    print(f"Threshold: {threshold}%\n")

    if pct < threshold:
        print(f"{GREEN}Disk is fine — no action needed.{RESET}")
        print(f"{DIM}Free space: {human_size(usage.free)}{RESET}")
        return 0

    print(f"{YELLOW}Disk is {pct:.0f}% full — above your {threshold}% threshold.{RESET}")
    if args.target:
        target = parse_size(args.target)
    else:
        want_pct = max(0.0, pct - (threshold - 5))
        target = int(want_pct / 100 * usage.total)
    if target is None or target <= 0:
        target = 1024 ** 3
    print(f"{BOLD}Targeting:{RESET} {human_size(target)}\n")

    class AutoArgs:
        pass

    a = AutoArgs()
    a.path = str(root)
    a.target = None
    a.top = args.top
    a.no_prompt = True
    a.hard = False
    a.dry_run = False
    a.trace = args.trace
    a.parallel = "auto"
    a.all = False
    a.profile = ""
    a.target_bytes = target
    return cmd_clean(a)


def _disk_bar(pct: float, width: int = 40) -> str:
    filled = int(width * min(pct, 100) / 100)
    color = GREEN if pct < 70 else YELLOW if pct < 85 else RED
    return f"{color}{'█' * filled}{'░' * (width - filled)}{RESET}"


def _health_score(pct: float, problems: list) -> int:
    score = 100
    if pct > 90:
        score -= 30
    elif pct > 80:
        score -= 18
    elif pct > 70:
        score -= 8
    for p in problems:
        if p.severity == "critical":
            score -= 12
        elif p.severity == "warn":
            score -= 5
    return max(0, score)


def cmd_doctor(args) -> int:
    import shutil
    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(f"{RED}Path does not exist: {root}{RESET}", file=sys.stderr)
        return 1
    _banner()
    print(f"{BOLD}Running full disk health check on:{RESET} {root}\n")
    configure(args.trace)

    session = _make_session(args)
    analyze(session, top_n=args.top)

    try:
        usage = shutil.disk_usage(root)
        pct = usage.used / usage.total * 100
    except OSError as e:
        print(f"{RED}Could not check disk usage: {e}{RESET}", file=sys.stderr)
        return 1

    score = _health_score(pct, session.problems)
    score_color = GREEN if score >= 80 else YELLOW if score >= 50 else RED
    verdict = "Healthy" if score >= 80 else "Needs attention" if score >= 50 else "Critical"

    print(f"{BOLD}DISK{RESET}")
    print(f"  {_disk_bar(pct)}  {pct:.1f}% used")
    print(f"  {human_size(usage.used)} used / {human_size(usage.total)} total / {human_size(usage.free)} free\n")

    print(f"{BOLD}HEALTH SCORE{RESET}  {score_color}{score}/100{RESET}  — {score_color}{verdict}{RESET}\n")

    print(f"{BOLD}PROBLEMS ({len(session.problems)}){RESET}")
    if session.problems:
        for p in session.problems:
            color = RED if p.severity == "critical" else YELLOW if p.severity == "warn" else DIM
            loc = f"  ({p.path})" if p.path else ""
            print(f"  {color}!{RESET} {p.message}{DIM}{loc}{RESET}")
    else:
        print(f"  {GREEN}none — looks clean{RESET}")
    print()

    safe_total = sum(ce.entry.size for ce in session.classified if ce.risk == "safe")
    build_total = sum(ce.entry.size for ce in session.classified if ce.risk == "probably-safe")
    print(f"{BOLD}QUICK WINS{RESET}")
    print(f"  {GREEN}{human_size(safe_total)}{RESET} of safe-to-delete caches/logs/trash")
    print(f"  {YELLOW}{human_size(build_total)}{RESET} of rebuildable build output")
    print()

    print(f"{BOLD}TOP SPACE HOGS{RESET}")
    for i, ce in enumerate(session.classified[:5], 1):
        color = "\033[92m" if ce.risk == "safe" else "\033[93m" if ce.risk == "probably-safe" else "\033[91m"
        print(f"  {color}{ce.entry.size_str:>10}{RESET}  {ce.label}")
        print(f"            {DIM}{ce.entry.path}{RESET}")
    print()

    print(f"{BOLD}RECOMMENDED NEXT STEP{RESET}")
    if pct >= 85:
        print(f"  {YELLOW}→{RESET} Run {BOLD}storager clean {root}{RESET} to free space interactively.")
        print(f"  {YELLOW}→{RESET} Or {BOLD}storager clean {root} --dry-run{RESET} to preview first.")
    elif session.problems:
        print(f"  {YELLOW}→{RESET} Run {BOLD}storager clean {root}{RESET} to clear the items above.")
    else:
        print(f"  {GREEN}→{RESET} Nothing urgent. Run {BOLD}storager auto {root} --threshold 85{RESET} to stay on top of it.")
    print()
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


def cmd_low_space(args) -> int:
    root = Path(args.path).expanduser().resolve()
    _banner()
    info = check_low_space(root)
    if not info:
        print(f"{RED}Could not check disk usage for {root}{RESET}", file=sys.stderr)
        return 1
    print_low_space_help(info)
    return 0


def cmd_version(_) -> int:
    print(f"storager {__version__}")
    return 0


def cmd_profile(args) -> int:
    _banner()
    if args.name:
        if args.name not in PROFILES:
            print(f"{RED}Unknown profile '{args.name}'.{RESET}", file=sys.stderr)
            print(f"Available: {', '.join(PROFILES)}", file=sys.stderr)
            return 1
        set_active_profile(args.name)
        p = PROFILES[args.name]
        print(f"{GREEN}Profile set to '{args.name}'.{RESET}")
        print(f"{DIM}{p.description}{RESET}")
        return 0

    active = active_profile_name()
    print(f"{BOLD}Profiles{RESET}  {DIM}(active: {active or 'none'}){RESET}\n")
    for name, p in PROFILES.items():
        marker = f"{GREEN}● active{RESET}" if name == active else "  "
        print(f"  {name:10} {marker}")
        print(f"  {'':10} {DIM}{p.description}{RESET}\n")
    print(f"{DIM}Set one with: storager profile developer{RESET}")
    return 0


def cmd_export(args) -> int:
    session = _make_session(args)
    if not session.root.exists():
        print(f"{RED}Path does not exist: {session.root}{RESET}", file=sys.stderr)
        return 1
    _banner()
    print(f"{BOLD}Exporting:{RESET} {session.root}\n")
    configure(session.flags.trace)
    analyze(session, top_n=args.top)

    data = {
        "root": str(session.root),
        "profile": session.flags.profile or None,
        "target_bytes": session.target_bytes,
        "total_measured": sum(e.size for e in session.entries),
        "problems": [
            {
                "severity": p.severity,
                "path": str(p.path) if p.path else None,
                "message": p.message,
            }
            for p in session.problems
        ],
        "items": [
            {
                "path": str(ce.entry.path),
                "size_bytes": ce.entry.size,
                "size": ce.entry.size_str,
                "is_dir": ce.entry.is_dir,
                "category": ce.category,
                "risk": ce.risk,
                "label": ce.label,
                "summary": ce.summary,
                "facts": ce.facts,
                "relations": ce.relations,
            }
            for ce in session.classified
        ],
    }

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2))
    print(f"{GREEN}Wrote {out}{RESET}  ({len(session.classified)} items, "
          f"{len(session.problems)} problems).")
    return 0


def check_low_space(root: Path) -> dict:
    import shutil
    try:
        usage = shutil.disk_usage(root)
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "pct": usage.used / usage.total * 100,
        }
    except OSError:
        return {}


def print_low_space_help(info: dict) -> None:
    free = info.get("free", 0)
    pct = info.get("pct", 0)
    print(f"\n{YELLOW}Your disk is {pct:.0f}% full — only {human_size(free)} free.{RESET}")
    print(f"{BOLD}You may not have enough space to `pip install .`.{RESET}")
    print(f"\n{DIM}No problem — storager itself is tiny (~50 KB, zero dependencies).{RESET}")
    print(f"{BOLD}Ways to run it without installing:{RESET}\n")
    print(f"  {GREEN}1.{RESET} Download the zip (no git, no pip needed):")
    print(f"     curl -L https://github.com/Aghosh-mv/storager-agent/archive/refs/heads/main.zip \\")
    print(f"       -o storager.zip && unzip storager.zip")
    print(f"     cd storager-agent-main && python3 -m storager\n")
    print(f"  {GREEN}2.{RESET} Run from the repo you already cloned:")
    print(f"     cd storager-agent && python3 -m storager\n")
    print(f"  {GREEN}3.{RESET} Put it on a drive with space:")
    print(f"     pip install --target /Volumes/External/storager .")
    print(f"     PYTHONPATH=/Volumes/External/storager python3 -m storager\n")


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
    clean_p.add_argument("--dry-run", action="store_true", help="Preview what would be deleted, delete nothing")
    clean_p.add_argument("--profile", help="Override the active profile for this run")
    clean_p.add_argument("--trace", action="store_true", help="Print stage timing")
    clean_p.add_argument("--parallel", default="auto", help="auto | sequential | 1-32")
    clean_p.set_defaults(func=cmd_clean)

    rules_p = sub.add_parser("rules", help="List / add / remove persistent rules")
    rules_p.add_argument("--add-category", help="Category for a new rule")
    rules_p.add_argument("--add-glob", help="Path glob for a new rule")
    rules_p.add_argument("--add-action", choices=["delete", "ignore"], default="delete")
    rules_p.add_argument("--remove", type=int, help="Index of rule to remove")
    rules_p.set_defaults(func=cmd_rules)

    profile_p = sub.add_parser("profile", help="List or set the active user profile")
    profile_p.add_argument("name", nargs="?", help="Profile to activate (developer / designer / casual / minimal)")
    profile_p.set_defaults(func=cmd_profile)

    export_p = sub.add_parser("export", help="Write a JSON report of a scan")
    export_p.add_argument("path", nargs="?", default=".", help="Directory to export (default: cwd)")
    export_p.add_argument("--out", default="storager-report.json", help="Output file")
    export_p.add_argument("--top", type=int, default=100, help="Max items to include")
    export_p.add_argument("--trace", action="store_true", help="Print stage timing")
    export_p.add_argument("--parallel", default="auto", help="auto | sequential | 1-32")
    export_p.set_defaults(func=cmd_export)

    ver_p = sub.add_parser("version", help="Print version")
    ver_p.set_defaults(func=cmd_version)

    low_p = sub.add_parser("low-space", help="Show how to run storager when disk is almost full")
    low_p.add_argument("path", nargs="?", default=".", help="Path to check (default: cwd)")
    low_p.set_defaults(func=cmd_low_space)

    undo_p = sub.add_parser("undo", help="Restore the last batch of deleted items from Trash")
    undo_p.set_defaults(func=cmd_undo)

    hist_p = sub.add_parser("history", help="Show past cleanups and total space freed")
    hist_p.set_defaults(func=cmd_history)

    auto_p = sub.add_parser("auto", help="Check disk and clean automatically if above threshold")
    auto_p.add_argument("path", nargs="?", default=".", help="Path to check (default: cwd)")
    auto_p.add_argument("--threshold", type=float, default=85, help="Trigger when disk usage is above this %% (default: 85)")
    auto_p.add_argument("--target", help="Target free space instead of computing from threshold")
    auto_p.add_argument("--top", type=int, default=50, help="Max items to consider")
    auto_p.add_argument("--trace", action="store_true", help="Print stage timing")
    auto_p.set_defaults(func=cmd_auto)

    doctor_p = sub.add_parser("doctor", help="Full disk health report: score, problems, top hogs, next step")
    doctor_p.add_argument("path", nargs="?", default=".", help="Path to check (default: cwd)")
    doctor_p.add_argument("--top", type=int, default=50, help="Max items to consider")
    doctor_p.add_argument("--trace", action="store_true", help="Print stage timing")
    doctor_p.add_argument("--parallel", default="auto", help="auto | sequential | 1-32")
    doctor_p.set_defaults(func=cmd_doctor)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    known = {"scan", "clean", "rules", "version", "low-space", "profile", "export", "undo", "auto", "doctor", "history"}
    if not argv:
        argv = ["clean"]
    elif argv[0] not in known and not argv[0].startswith("-"):
        argv = ["clean"] + argv
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
