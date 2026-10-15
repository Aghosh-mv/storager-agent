from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class DeleteResult:
    path: Path
    ok: bool
    message: str
    freed_bytes: int = 0
    dest: Optional[Path] = None


def _move_to_trash_macos(path: Path) -> tuple:
    trash_dir = Path.home() / ".Trash"
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / path.name
    i = 1
    while dest.exists():
        dest = trash_dir / f"{path.name}.{i}"
        i += 1
    try:
        shutil.move(str(path), str(dest))
        return True, dest
    except OSError:
        return False, None


def _move_to_trash_linux(path: Path) -> tuple:
    trash_dir = Path.home() / ".local" / "share" / "Trash" / "files"
    trash_dir.mkdir(parents=True, exist_ok=True)
    dest = trash_dir / path.name
    i = 1
    while dest.exists():
        dest = trash_dir / f"{path.name}.{i}"
        i += 1
    try:
        shutil.move(str(path), str(dest))
        info_dir = Path.home() / ".local" / "share" / "Trash" / "info"
        info_dir.mkdir(parents=True, exist_ok=True)
        info = info_dir / (dest.name + ".trashinfo")
        info.write_text(f"[Trash Info]\nPath={path}\nDeletionDate=2026-01-01T00:00:00\n")
        return True, dest
    except OSError:
        return False, None


def move_to_trash(path: Path) -> tuple:
    if sys.platform == "darwin":
        return _move_to_trash_macos(path)
    elif sys.platform.startswith("linux"):
        return _move_to_trash_linux(path)
    else:
        ps = f'(New-Object -ComObject Shell.Application).Namespace(0xA).MoveHere("{path}")'
        try:
            subprocess.run(["powershell", "-Command", ps], check=True, capture_output=True)
            return True, None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False, None


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
            ok, dest = move_to_trash(p)
            msg = "Moved to Trash" if ok else "Failed to move to Trash"
        else:
            ok = hard_delete(p)
            msg = "Permanently deleted" if ok else "Failed to delete"
            dest = None
        results.append(DeleteResult(path=p, ok=ok, message=msg, freed_bytes=size if ok else 0, dest=dest))
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
