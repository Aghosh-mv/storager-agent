"""Safe deletion — moves to system trash by default, hard-delete only on request."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class DeleteResult:
    path: Path
    ok: bool
    message: str
    freed_bytes: int = 0


def _move_to_trash_macos(path: Path) -> bool:
    """Use macOS `trash` command if available, else osascript."""
    # Try Homebrew `trash` binary
    if shutil.which("trash"):
        try:
            subprocess.run(["trash", str(path)], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            pass
    # Fallback: osascript Finder delete
    script = f'tell application "Finder" to delete POSIX file "{path}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _move_to_trash_linux(path: Path) -> bool:
    trash_dir = Path.home() / ".local" / "share" / "Trash" / "files"
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / path.name
    # avoid collision
    i = 1
    while dest.exists():
        dest = trash_dir / f"{path.name}.{i}"
        i += 1
    try:
        shutil.move(str(path), str(dest))
        # write trashinfo
        info_dir = Path.home() / ".local" / "share" / "Trash" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        info = info_dir / (dest.name + ".trashinfo")
        info.write_text(f"[Trash Info]\nPath={path}\nDeletionDate=2026-01-01T00:00:00\n")
        return True
    except OSError:
        return False


def move_to_trash(path: Path) -> bool:
    if sys.platform == "darwin":
        return _move_to_trash_macos(path)
    elif sys.platform.startswith("linux"):
        return _move_to_trash_linux(path)
    else:
        # Windows: use recycle bin via PowerShell
        ps = f'(New-Object -ComObject Shell.Application).Namespace(0xA).MoveHere("{path}")'
        try:
            subprocess.run(["powershell", "-Command", ps], check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


def hard_delete(path: Path) -> bool:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=False)
        else:
            path.unlink()
        return True
    except OSError:
        return False


def delete_entries(paths: List[Path], *, use_trash: bool = True) -> List[DeleteResult]:
    results: List[DeleteResult] = []
    for p in paths:
        if not p.exists():
            results.append(DeleteResult(path=p, ok=False, message="Already gone"))
            continue
        size = _dir_or_file_size(p)
        if use_trash:
            ok = move_to_trash(p)
            msg = "Moved to Trash" if ok else "Failed to move to Trash"
        else:
            ok = hard_delete(p)
            msg = "Permanently deleted" if ok else "Failed to delete"
        results.append(DeleteResult(path=p, ok=ok, message=msg, freed_bytes=size if ok else 0))
    return results


def _dir_or_file_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            fp = Path(root) / f
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total
