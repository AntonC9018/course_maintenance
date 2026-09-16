"""Shared CI orchestration (issue #14, CI-1..CI-12 shared side).

Stable entry point: ``python3 <course_maintenance>/publish.py ci
--course-repo <repo> [--out <dir>]``. Runs in fixed order:

1. existing course-maintenance checks (``maintain.py --check`` semantics,
   read-only);
2. publishing checks (``publishing check``, read-only);
3. compatibility suite (``tests.test_compatibility``, isolated temp dirs);
4. complete static site build (``site build`` to a disposable directory
   outside the course repo).

All paths resolve from this file's location so the command works from a
checked-out submodule at a pinned revision (CI-2/CI-6); no reusable
workflow is fetched independently of the submodule revision.

Read-only wrt course sources: maintain runs with ``check_only=True``,
publishing check never writes, the compat suite uses TemporaryDirectory
fixtures, and the site build writes only below ``--out`` (or an auto temp
dir) outside the repo. Exit codes: 0 success, 1 validation/build dirty,
2 usage error (bad ``--out`` location; bad ``--course-repo`` is handled
by the publish.py dispatcher).

Dependency pins + safe caches (CI-8): renderer/npm versions live in
``renderer/package.json`` + ``package-lock.json`` (see
``publishing.site.PINNED_VERSIONS``), Chromium in
``publishing.site.PINNED_BROWSERS``, Python/Node below. Cache keys
incorporate the lockfile hash and toolchain versions so caches never
substitute outputs from a different lockfile or browser version.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

from .site import PINNED_BROWSERS, PINNED_VERSIONS

PINNED_PYTHON = "3.12"
PINNED_NODE = "22"

_FIX_CI = "operation: ci"


def maintenance_root() -> Path:
    """Course-maintenance checkout root (works from a submodule)."""
    return Path(__file__).resolve().parent.parent


def lockfile_path() -> Path:
    """Committed npm lockfile used for installs + cache keys."""
    return maintenance_root() / "renderer" / "package-lock.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def npm_cache_key(lockfile: Path | None = None) -> str:
    """Safe npm cache key incorporating the lockfile hash (CI-8).

    Different lockfile bytes give different keys, so a cache entry can
    never substitute dependencies from a different pinned revision.
    """
    lf = Path(lockfile) if lockfile is not None else lockfile_path()
    try:
        digest = hashlib.sha256(lf.read_bytes()).hexdigest()[:16]
    except OSError:
        digest = "no-lock"
    return f"npm-{sys.platform}-node-{PINNED_NODE}-lock-{digest}"


def browser_cache_key(playwright: str | None = None,
                      chromium: str | None = None) -> str:
    """Safe Playwright/Chromium cache key incorporating versions (CI-8)."""
    pw = playwright or PINNED_VERSIONS["playwright"]
    cr = chromium or PINNED_BROWSERS["chromium"]
    return f"playwright-{pw}-chromium-{cr}"


def run_maintain_check(repo: Path) -> int:
    """Run existing maintenance checks in read-only ``--check`` mode.

    Scoped to course sources: when the repo has ``en/``/``ru/`` language
    roots, only those plus root-level ``*.md`` are checked. The
    ``course_maintenance`` submodule (own CI), ``node_modules``,
    renderer outputs, and other tooling are never treated as lessons.
    """
    from maintenance.pipeline import run as run_pipeline

    repo = Path(repo).resolve()
    print("--- ci: maintain check ---")
    targets: list[Path] = []
    for lang in ("en", "ru"):
        lang_dir = repo / lang
        if lang_dir.is_dir():
            targets.append(lang_dir)
    # Root-level docs (README, AGENTS) still checked; submodule excluded.
    targets.extend(sorted(repo.glob("*.md")))
    if not targets:
        targets = [repo]
    try:
        code = run_pipeline(targets, root=repo, check_only=True, quiet=False)
    except Exception as exc:  # defensive: actionable, still nonzero
        print(f"error: ci stage 'maintain check' failed for {repo}: {exc}; "
              f"{_FIX_CI}", file=sys.stderr)
        return 1
    if code != 0:
        print(f"error: ci stage 'maintain check' found issues in {repo}; "
              f"operation: maintain.py --check", file=sys.stderr)
    else:
        print("ci: maintain check: OK")
    return code


def run_publishing_check_stage(repo: Path) -> int:
    """Run read-only publishing validation (config/metadata/links)."""
    from .check import run_publishing_check

    repo = Path(repo).resolve()
    print("--- ci: publishing check ---")
    try:
        code = run_publishing_check(repo, None)
    except Exception as exc:  # defensive: actionable, still nonzero
        print(f"error: ci stage 'publishing check' failed for {repo}: {exc}; "
              f"{_FIX_CI}", file=sys.stderr)
        return 1
    if code != 0:
        print(f"error: ci stage 'publishing check' failed for {repo}; "
              f"operation: publishing check", file=sys.stderr)
    else:
        print("ci: publishing check: OK")
    return code


def run_compat_suite() -> int:
    """Run the shared compatibility suite in isolation (temp dirs)."""
    root = maintenance_root()
    print("--- ci: compatibility suite ---")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_compatibility"],
            cwd=str(root), capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"error: ci stage 'compatibility suite' failed to run: {exc}; "
              f"{_FIX_CI}", file=sys.stderr)
        return 1
    except Exception as exc:  # defensive (e.g. timeout type differences)
        print(f"error: ci stage 'compatibility suite' failed to run: {exc}; "
              f"{_FIX_CI}", file=sys.stderr)
        return 1
    if proc.stdout:
        print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        print("error: ci stage 'compatibility suite' failed; "
              f"{_FIX_CI}", file=sys.stderr)
    else:
        print("ci: compatibility suite: OK")
    return proc.returncode


def run_site_build_stage(repo: Path, out=None) -> int:
    """Run the complete static site build outside the course repo."""
    from .projection import validate_out_location
    from .site import run_site_build

    repo = Path(repo).resolve()
    print("--- ci: site build ---")
    if out is not None:
        cand = Path(out)
        out_path = cand if cand.is_absolute() else (Path.cwd() / cand)
        try:
            out_resolved = out_path.resolve()
        except OSError as exc:
            print(f"error: cannot resolve output directory {out}: {exc}; "
                  f"{_FIX_CI}", file=sys.stderr)
            return 2
        problem = validate_out_location(repo, out_resolved)
        if problem is not None:
            print(f"error: {problem}; {_FIX_CI}", file=sys.stderr)
            return 2
        args = argparse.Namespace(out=str(out_resolved), check=False)
    else:
        args = argparse.Namespace(out=None, check=False)
    try:
        code = run_site_build(repo, args)
    except Exception as exc:  # defensive: actionable, still nonzero
        print(f"error: ci stage 'site build' failed for {repo}: {exc}; "
              f"{_FIX_CI}", file=sys.stderr)
        return 1
    if code == 2:
        return 2
    if code != 0:
        print(f"error: ci stage 'site build' failed for {repo}; "
              f"operation: site build", file=sys.stderr)
        return 1
    print("ci: site build: OK")
    return 0


def run_ci(course_repo: Path, args) -> int:
    """Handler(course_repo, args) -> int for publish.py registry (CI-1)."""
    from .projection import validate_out_location

    repo = Path(course_repo).resolve()
    raw_out = getattr(args, "out", None)
    # Fail fast on usage errors before expensive stages (exit 2).
    if raw_out is not None:
        cand = Path(raw_out)
        out_path = cand if cand.is_absolute() else (Path.cwd() / cand)
        try:
            out_resolved = out_path.resolve()
        except OSError as exc:
            print(f"error: cannot resolve output directory {raw_out}: {exc}; "
                  f"{_FIX_CI}", file=sys.stderr)
            return 2
        problem = validate_out_location(repo, out_resolved)
        if problem is not None:
            print(f"error: {problem}; {_FIX_CI}", file=sys.stderr)
            return 2

    print(f"ci: validating {repo} "
          f"(maintain check + publishing check + compat suite + site build)")
    code = run_maintain_check(repo)
    if code != 0:
        print(f"error: ci stage 'maintain check' failed for {repo}; "
              f"{_FIX_CI}", file=sys.stderr)
        return code
    code = run_publishing_check_stage(repo)
    if code != 0:
        print(f"error: ci stage 'publishing check' failed for {repo}; "
              f"{_FIX_CI}", file=sys.stderr)
        return code
    code = run_compat_suite()
    if code != 0:
        print(f"error: ci stage 'compatibility suite' failed; "
              f"{_FIX_CI}", file=sys.stderr)
        return code
    code = run_site_build_stage(repo, raw_out)
    if code != 0:
        print(f"error: ci stage 'site build' failed for {repo}; "
              f"{_FIX_CI}", file=sys.stderr)
        return code
    print(f"ci: OK ({repo}; read-only wrt sources; "
          f"site build outside repo)")
    return 0
