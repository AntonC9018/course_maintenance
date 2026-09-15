"""Shared temp-dir harness for course-maintenance tests (stdlib only).

Every test builds its own course-repo copy inside a TemporaryDirectory and
passes absolute paths to the CLI. Nothing here ever writes to committed
fixtures or to a live course checkout.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def make_lab(root: Path, dirname: str, files: dict) -> Path:
    """Create <root>/<dirname>/ with {filename: content} and return the dir."""
    d = root / dirname
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        write(d / name, content)
    return d


def tree_names(d: Path) -> list:
    return sorted(p.name for p in d.iterdir() if p.is_file())


def run_maintain(*args: str) -> "subprocess.CompletedProcess[str]":
    cmd = [sys.executable, str(REPO_ROOT / "maintain.py"), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def run_publish(*args: str) -> "subprocess.CompletedProcess[str]":
    cmd = [sys.executable, str(REPO_ROOT / "publish.py"), *args]
    return subprocess.run(cmd, capture_output=True, text=True)
