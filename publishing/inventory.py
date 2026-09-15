"""Deterministic lesson inventory (CFG-2, CFG-4, part of CFG-6).

Selects Markdown only from configured language roots, then applies exact
repository-relative exclusions. Empty, outline, and `stub.md` documents
remain valid lessons (no content filtering). Only `*.md` (case-insensitive)
under roots are selected.

CFG-6: rejects case-folded (+ NFC-normalized) duplicate source paths and
configuration paths that do not resolve to the intended repository entry
(case/Unicode mismatches). The inventory is sorted by repository-relative
posix path for byte-identical downstream projections.

Reusable internal model for metadata (#8) and projection (#10-11) stages:
import Lesson / LessonInventory and build_inventory(); do not re-walk.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .config import PublishingConfig, check_exact_resolution
from .config import ConfigError


class InventoryError(Exception):
    def __init__(self, message: str, *, rule: str = "CFG-6",
                 path: str | Path | None = None,
                 hint: str = "fix: rename files so names differ beyond case/"
                             "Unicode folding, or correct course-publishing.json; "
                             "operation: publishing check"):
        self.rule = rule
        loc = str(path) if path is not None else "lesson inventory"
        super().__init__(f"{loc}: [{rule}] {message}; {hint}")


def _fold_key(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


@dataclass(frozen=True)
class Lesson:
    source_path: Path
    repo_rel: str
    language: str


@dataclass(frozen=True)
class LessonInventory:
    course_repo: Path = field(compare=False)
    config: PublishingConfig = field(compare=False)
    lessons: tuple[Lesson, ...]

    def by_rel(self) -> dict[str, Lesson]:
        return {l.repo_rel: l for l in self.lessons}

    def count_by_language(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for l in self.lessons:
            out[l.language] = out.get(l.language, 0) + 1
        return out

    def total(self) -> int:
        return len(self.lessons)


def _language_for(rel: str, config: PublishingConfig) -> str | None:
    best: str | None = None
    best_len = -1
    for lang in config.languages:
        if rel == lang.root or rel.startswith(lang.root + "/"):
            if len(lang.root) > best_len:
                best, best_len = lang.code, len(lang.root)
    return best


def build_inventory(course_repo: Path | str,
                    config: PublishingConfig) -> LessonInventory:
    """Collect selected lessons. Read-only (walks + reads dirs only)."""
    repo = Path(course_repo).resolve()
    cfg_path = config.source_path

    # Roots must still resolve exactly (CFG-6) at selection time.
    for lang in config.languages:
        try:
            exists = check_exact_resolution(
                repo, lang.root, kind="language root", config_path=cfg_path)
        except ConfigError as e:
            raise InventoryError(str(e), rule="CFG-6",
                                 path=cfg_path) from e
        root_abs = repo.joinpath(*lang.root.split("/"))
        if not exists or not root_abs.is_dir():
            raise InventoryError(
                f"language root {lang.root!r} ({lang.code}) not found",
                rule="CFG-1", path=cfg_path,
                hint="fix: edit course-publishing.json to point at an "
                     "existing directory; operation: publishing check")

    # Exclusion case-mismatch check (CFG-6): an exclusion that does not
    # exist exactly but matches an on-disk path after folding is ambiguous.
    # Truly unknown exclusions (no folded match) are allowed (future files).
    for excl in config.exclude:
        try:
            exists = check_exact_resolution(
                repo, excl, kind="exclusion", config_path=cfg_path)
        except ConfigError as e:
            raise InventoryError(str(e), rule="CFG-6",
                                 path=cfg_path) from e
        if not exists:
            # Look for a folded match anywhere under the owning root(s) to
            # give a sharper diagnostic; absence is fine (allowed).
            folded = _fold_key(excl)
            for lang in config.languages:
                if not (excl == lang.root or excl.startswith(lang.root + "/")):
                    continue
                root_abs = repo.joinpath(*lang.root.split("/"))
                for dirpath, _d, fns in os.walk(root_abs):
                    if ".git" in Path(dirpath).parts:
                        continue
                    for fn in fns:
                        cand = (Path(dirpath) / fn)
                        try:
                            rel = cand.relative_to(repo).as_posix()
                        except ValueError:
                            continue
                        if _fold_key(rel) == folded and rel != excl:
                            raise InventoryError(
                                f"exclude entry {excl!r} does not resolve to the "
                                f"intended repository entry (found {rel!r} "
                                f"differing only by case or Unicode "
                                f"normalization)",
                                rule="CFG-6", path=cfg_path)

    exclude_set = set(config.exclude)
    found: list[Lesson] = []
    for lang in config.languages:
        root_abs = repo.joinpath(*lang.root.split("/"))
        for dirpath, dirnames, filenames in os.walk(root_abs):
            if ".git" in Path(dirpath).parts:
                continue
            dirnames[:] = sorted(d for d in dirnames if d != ".git")
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if p.suffix.lower() != ".md":
                    continue
                if not p.is_file():
                    continue
                try:
                    rel = p.resolve().relative_to(repo).as_posix()
                except ValueError:
                    try:
                        rel = p.relative_to(repo).as_posix()
                    except ValueError:
                        continue
                if rel in exclude_set:
                    continue
                # Guard against symlinks/roots overlap placing a file under
                # a different language than walked: assign by longest prefix.
                assigned = _language_for(rel, config)
                if assigned is None:
                    continue
                found.append(Lesson(source_path=p.resolve(),
                                    repo_rel=rel, language=assigned))

    # CFG-6: folded duplicate source paths are ambiguous.
    seen: dict[str, str] = {}
    for lesson in found:
        key = _fold_key(lesson.repo_rel)
        if key in seen and seen[key] != lesson.repo_rel:
            raise InventoryError(
                f"case-folded duplicate source paths {seen[key]!r} and "
                f"{lesson.repo_rel!r} (identical after Unicode NFC "
                f"normalization and case folding)",
                rule="CFG-6", path=lesson.source_path)
        seen.setdefault(key, lesson.repo_rel)

    found.sort(key=lambda l: l.repo_rel)

    # Root lesson must be selected (not excluded, exists, .md, under root).
    if config.root_lesson not in {l.repo_rel for l in found}:
        # Distinguish excluded vs missing for actionable diagnostics.
        if config.root_lesson in exclude_set:
            raise InventoryError(
                f"unknown root_lesson {config.root_lesson!r}: listed in "
                f"exclude",
                rule="CFG-1", path=cfg_path,
                hint="fix: edit course-publishing.json to remove the "
                     "root_lesson from exclude; operation: publishing check")
        raise InventoryError(
            f"unknown root_lesson {config.root_lesson!r}: not in selected "
            f"inventory",
            rule="CFG-1", path=cfg_path,
            hint="fix: edit course-publishing.json to point root_lesson at "
                 "a selected lesson; operation: publishing check")

    return LessonInventory(course_repo=repo, config=config,
                           lessons=tuple(found))
