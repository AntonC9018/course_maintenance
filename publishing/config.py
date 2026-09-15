"""Strict version-1 publishing configuration (CFG-1, part of CFG-6).

Parses `<course-repo>/course-publishing.json` exactly as specified.
Rejects unknown fields, duplicate language codes/roots, absolute paths,
escaping paths, overlapping route mappings, unknown root lessons, and
exclusions outside language roots. Resolves configured paths safely
relative to the explicit --course-repo root. Read-only: never writes.

Error format: every ConfigError message identifies the source path
(course-publishing.json), the violated rule (CFG-1/CFG-2/CFG-6), and the
corrective operation when one exists (edit the config, fix the path).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "course-publishing.json"

ALLOWED_TOP_FIELDS = frozenset({
    "version", "default_language", "languages", "exclude",
    "route_sections", "site_title", "root_lesson", "peer_repositories",
})
ALLOWED_LANGUAGE_FIELDS = frozenset({"code", "root", "label"})
ALLOWED_ROUTE_FIELDS = frozenset({"source", "destination"})

_FIX_CONFIG = "fix: edit course-publishing.json"
_WINDOWS_ABS_RE = re.compile(r"^[a-zA-Z]:[\\/]")


class ConfigError(Exception):
    """Validation failure with rule id, source path, and fix hint."""

    def __init__(self, message: str, *, rule: str = "CFG-1",
                 path: str | Path | None = None,
                 hint: str = _FIX_CONFIG):
        self.rule = rule
        loc = str(path) if path is not None else CONFIG_FILENAME
        super().__init__(f"{loc}: [{rule}] {message}; {hint}")


def _norm_key(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def _fail(msg: str, *, rule: str = "CFG-1",
          path: Path | None = None, hint: str = _FIX_CONFIG) -> ConfigError:
    loc = str(path) if path is not None else CONFIG_FILENAME
    return ConfigError(msg, rule=rule, path=loc, hint=hint)


def _check_rel_path(value: object, *, field: str, config_path: Path,
                    allow_dotdot: bool = False) -> str:
    """Validate a repository-relative posix path. Return normalized form."""
    if not isinstance(value, str) or not value:
        raise _fail(f"{field} must be a non-empty string",
                    path=config_path)
    if "\\" in value:
        raise _fail(
            f"{field} {value!r} must use forward slashes, not backslashes",
            path=config_path)
    if value.startswith("/") or value.startswith("//") \
            or _WINDOWS_ABS_RE.match(value) or value.startswith("\\\\"):
        raise _fail(f"{field} {value!r} must not be absolute "
                    f"(paths are relative to the course repo root)",
                    path=config_path)
    if value.startswith("./"):
        raise _fail(f"{field} {value!r} is not canonical "
                    f"(remove leading ./)",
                    path=config_path)
    stripped = value.strip()
    if stripped != value:
        raise _fail(f"{field} {value!r} must not have leading/trailing whitespace",
                    path=config_path)
    # Strip trailing slashes for normalization (allows "en/" as root).
    norm = value.rstrip("/")
    if not norm:
        raise _fail(f"{field} {value!r} is empty after normalization",
                    path=config_path)
    parts = norm.split("/")
    for part in parts:
        if part == "":
            raise _fail(f"{field} {value!r} has an empty segment (//)",
                        path=config_path)
        if part == ".":
            raise _fail(f"{field} {value!r} must not contain '.' segments",
                        path=config_path)
        if part == "..":
            if not allow_dotdot:
                raise _fail(
                    f"{field} {value!r} is escaping (must not contain '..'; "
                    f"paths are relative to the course repo root)",
                    path=config_path)
    return norm


def _exact_dir_entries(parent: Path) -> list[str] | None:
    try:
        return os.listdir(parent)
    except OSError:
        return None


def check_exact_resolution(course_repo: Path, rel_posix: str, *,
                           kind: str, config_path: Path) -> bool:
    """Ensure each component of rel_posix matches disk exactly (CFG-6).

    Returns True if the full path exists exactly. Returns False if it does
    not exist at all. Raises ConfigError(CFG-6) if it does not exist
    exactly but a case-folded/NFC variant does ("does not resolve to the
    intended repository entry").
    """
    parts = rel_posix.split("/")
    cur = course_repo
    for i, part in enumerate(parts):
        entries = _exact_dir_entries(cur)
        if entries is None:
            return False
        if part in entries:
            cur = cur / part
            continue
        want = _norm_key(part)
        for e in entries:
            if _norm_key(e) == want:
                got = "/".join(parts[:i] + [e])
                raise _fail(
                    f"{kind} {rel_posix!r} does not resolve to the intended "
                    f"repository entry (found {got!r} differing only by case "
                    f"or Unicode normalization)",
                    rule="CFG-6", path=config_path,
                    hint=f"{_FIX_CONFIG} to match the on-disk name {e!r}")
        return False
    return True


@dataclass(frozen=True)
class Language:
    code: str
    root: str
    label: str


@dataclass(frozen=True)
class RouteSection:
    source: str
    destination: str


@dataclass(frozen=True)
class PublishingConfig:
    version: int
    default_language: str
    languages: tuple[Language, ...]
    exclude: tuple[str, ...]
    route_sections: tuple[RouteSection, ...]
    site_title: dict[str, str]
    root_lesson: str
    peer_repositories: tuple[str, ...]
    source_path: Path = field(compare=False)
    course_repo: Path = field(compare=False)

    def roots(self) -> dict[str, str]:
        return {l.code: l.root for l in self.languages}

    def exclude_set(self) -> set[str]:
        return set(self.exclude)


def _is_under(path: str, root: str) -> bool:
    return path != root and path.startswith(root + "/")


def load_config(course_repo: Path | str) -> PublishingConfig:
    """Read and strictly validate course-publishing.json. Read-only."""
    repo = Path(course_repo).resolve()
    cfg_path = repo / CONFIG_FILENAME
    if not cfg_path.is_file():
        raise ConfigError(
            f"{CONFIG_FILENAME} not found (expected at {cfg_path})",
            rule="CFG-1", path=cfg_path,
            hint="fix: create course-publishing.json per "
                 "docs/course-publishing-spec.md; operation: publishing check")
    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise _fail(f"invalid JSON: {e}", path=cfg_path) from e
    except OSError as e:
        raise _fail(f"cannot read config: {e}", path=cfg_path) from e

    if not isinstance(raw, dict):
        raise _fail("top-level JSON must be an object", path=cfg_path)

    unknown = set(raw) - set(ALLOWED_TOP_FIELDS)
    if unknown:
        raise _fail(
            f"unknown field(s) {sorted(unknown)}; "
            f"allowed: {sorted(ALLOWED_TOP_FIELDS)}",
            path=cfg_path)
    missing = set(ALLOWED_TOP_FIELDS) - set(raw)
    if missing:
        raise _fail(f"missing required field(s) {sorted(missing)}",
                    path=cfg_path)

    version = raw["version"]
    if type(version) is not int or version != 1:
        raise _fail(
            f"version must be exactly 1 (got {version!r})",
            path=cfg_path)

    # --- languages ---
    langs_raw = raw["languages"]
    if not isinstance(langs_raw, list) or not langs_raw:
        raise _fail("languages must be a non-empty list", path=cfg_path)
    languages: list[Language] = []
    seen_codes: dict[str, str] = {}
    seen_roots: dict[str, str] = {}
    for i, entry in enumerate(langs_raw):
        where = f"languages[{i}]"
        if not isinstance(entry, dict):
            raise _fail(f"{where} must be an object", path=cfg_path)
        unk = set(entry) - set(ALLOWED_LANGUAGE_FIELDS)
        if unk:
            raise _fail(f"{where} has unknown field(s) {sorted(unk)}; "
                        f"allowed: {sorted(ALLOWED_LANGUAGE_FIELDS)}",
                        path=cfg_path)
        for k in ("code", "root", "label"):
            if k not in entry:
                raise _fail(f"{where} is missing {k!r}", path=cfg_path)
        code, root_v, label = entry["code"], entry["root"], entry["label"]
        if not isinstance(code, str) or not code or "/" in code \
                or "\\" in code or code.strip() != code:
            raise _fail(f"{where}.code must be a non-empty language code "
                        f"(got {code!r})", path=cfg_path)
        if not isinstance(label, str) or not label:
            raise _fail(f"{where}.label must be a non-empty string",
                        path=cfg_path)
        root = _check_rel_path(root_v, field=f"{where}.root",
                               config_path=cfg_path)
        ck = _norm_key(code)
        if ck in seen_codes:
            raise _fail(
                f"duplicate language code {code!r} "
                f"(already used by {seen_codes[ck]!r})",
                path=cfg_path)
        seen_codes[ck] = code
        rk = _norm_key(root)
        if rk in seen_roots:
            raise _fail(
                f"duplicate language root {root!r} "
                f"(already used by {seen_roots[rk]!r})",
                path=cfg_path)
        seen_roots[rk] = code
        languages.append(Language(code=code, root=root, label=label))

    # Overlapping (nested) language roots are ambiguous for inventory.
    for a in languages:
        for b in languages:
            if a.code == b.code:
                continue
            if _is_under(b.root, a.root) or _is_under(a.root, b.root):
                # Report once per unordered pair.
                if a.code < b.code:
                    raise _fail(
                        f"overlapping language roots {a.root!r} ({a.code}) "
                        f"and {b.root!r} ({b.code}); roots must be disjoint",
                        path=cfg_path)

    # --- exclude ---
    excl_raw = raw["exclude"]
    if not isinstance(excl_raw, list):
        raise _fail("exclude must be a list", path=cfg_path)
    exclude: list[str] = []
    for i, e in enumerate(excl_raw):
        norm = _check_rel_path(e, field=f"exclude[{i}]",
                               config_path=cfg_path)
        exclude.append(norm)
    for e in exclude:
        if not any(_is_under(e, lang.root) for lang in languages):
            raise ConfigError(
                f"{CONFIG_FILENAME}: [CFG-2] exclude entry {e!r} is outside "
                f"configured language roots "
                f"{sorted(l.root for l in languages)}; "
                f"fix: edit course-publishing.json to place exclude entries "
                f"below a language root or remove them",
                rule="CFG-2", path=cfg_path, hint=_FIX_CONFIG)

    # --- route_sections ---
    routes_raw = raw["route_sections"]
    if not isinstance(routes_raw, list):
        raise _fail("route_sections must be a list", path=cfg_path)
    routes: list[RouteSection] = []
    for i, entry in enumerate(routes_raw):
        where = f"route_sections[{i}]"
        if not isinstance(entry, dict):
            raise _fail(f"{where} must be an object", path=cfg_path)
        unk = set(entry) - set(ALLOWED_ROUTE_FIELDS)
        if unk:
            raise _fail(f"{where} has unknown field(s) {sorted(unk)}; "
                        f"allowed: {sorted(ALLOWED_ROUTE_FIELDS)}",
                        path=cfg_path)
        if "source" not in entry or "destination" not in entry:
            raise _fail(f"{where} requires 'source' and 'destination'",
                        path=cfg_path)
        src = _check_rel_path(entry["source"], field=f"{where}.source",
                              config_path=cfg_path)
        dst = _check_rel_path(entry["destination"],
                              field=f"{where}.destination",
                              config_path=cfg_path)
        routes.append(RouteSection(source=src, destination=dst))
    for i in range(len(routes)):
        for j in range(i + 1, len(routes)):
            a, b = routes[i].source, routes[j].source
            if a == b:
                raise _fail(
                    f"overlapping route mappings: duplicate source {a!r} "
                    f"(entries {i} and {j})",
                    path=cfg_path)
            if _is_under(a, b) or _is_under(b, a):
                raise _fail(
                    f"overlapping route mappings: {a!r} (entry {i}) overlaps "
                    f"{b!r} (entry {j}); sources must be disjoint",
                    path=cfg_path)

    # --- site_title ---
    site_raw = raw["site_title"]
    if not isinstance(site_raw, dict):
        raise _fail("site_title must be an object", path=cfg_path)
    codes = {l.code for l in languages}
    for k, v in site_raw.items():
        if k not in codes:
            raise _fail(
                f"site_title has unknown language {k!r}; "
                f"known languages: {sorted(codes)}",
                path=cfg_path)
        if not isinstance(v, str) or not v:
            raise _fail(f"site_title[{k!r}] must be a non-empty string",
                        path=cfg_path)
    for c in codes:
        if c not in site_raw:
            raise _fail(f"site_title is missing language {c!r}",
                        path=cfg_path)

    # --- default_language ---
    default = raw["default_language"]
    if not isinstance(default, str) or default not in codes:
        raise _fail(
            f"default_language {default!r} must be one of "
            f"{sorted(codes)}",
            path=cfg_path)

    # --- root_lesson ---
    root_lesson_raw = raw["root_lesson"]
    root_lesson = _check_rel_path(
        root_lesson_raw, field="root_lesson", config_path=cfg_path)
    if not root_lesson.lower().endswith(".md"):
        raise _fail(f"root_lesson {root_lesson!r} must be a Markdown (.md) path",
                    path=cfg_path)
    if not any(_is_under(root_lesson, lang.root) for lang in languages):
        raise _fail(
            f"root_lesson {root_lesson!r} is outside configured language "
            f"roots {sorted(l.root for l in languages)}",
            path=cfg_path)
    if root_lesson in set(exclude):
        raise _fail(
            f"root_lesson {root_lesson!r} is excluded by the exclude list; "
            f"remove it from exclude",
            path=cfg_path)
    # Filesystem: must resolve to the intended entry (CFG-6) and exist.
    if check_exact_resolution(repo, root_lesson, kind="root_lesson",
                              config_path=cfg_path):
        if not (repo / Path(*root_lesson.split("/"))).is_file():
            raise _fail(f"unknown root_lesson {root_lesson!r}: not a file",
                        path=cfg_path)
    else:
        raise _fail(f"unknown root_lesson {root_lesson!r}: file not found",
                    path=cfg_path)

    # Language roots must exist as directories with exact case (CFG-6).
    for lang in languages:
        if check_exact_resolution(repo, lang.root, kind="language root",
                                  config_path=cfg_path):
            if not (repo / Path(*lang.root.split("/"))).is_dir():
                raise _fail(
                    f"language root {lang.root!r} ({lang.code}) is not "
                    f"a directory",
                    path=cfg_path)
        else:
            raise _fail(
                f"language root {lang.root!r} ({lang.code}) not found",
                path=cfg_path)

    # --- peer_repositories ---
    peers_raw = raw["peer_repositories"]
    if not isinstance(peers_raw, list):
        raise _fail("peer_repositories must be a list", path=cfg_path)
    peers: list[str] = []
    for i, p in enumerate(peers_raw):
        norm = _check_rel_path(p, field=f"peer_repositories[{i}]",
                               config_path=cfg_path, allow_dotdot=True)
        # Absolute already rejected inside _check_rel_path, but keep the
        # keyword in this branch for actionable diagnostics.
        if norm.startswith("/") or _WINDOWS_ABS_RE.match(str(p)):
            raise _fail(
                f"peer_repositories[{i}] {p!r} must not be absolute; "
                f"use a path relative to the course repo root",
                path=cfg_path)
        # Resolve safely without requiring containment (peers may be
        # siblings), but they must exist as directories when listed.
        fs_target = repo.joinpath(*norm.split("/"))
        try:
            resolved = fs_target.resolve()
        except OSError:
            resolved = fs_target
        if not resolved.is_dir():
            raise _fail(
                f"peer_repositories[{i}] {p!r} not found "
                f"(resolved to {resolved}); peers must be local "
                f"repository directories",
                path=cfg_path)
        peers.append(norm)

    return PublishingConfig(
        version=1,
        default_language=default,
        languages=tuple(languages),
        exclude=tuple(exclude),
        route_sections=tuple(routes),
        site_title=dict(site_raw),
        root_lesson=root_lesson,
        peer_repositories=tuple(peers),
        source_path=cfg_path,
        course_repo=repo,
    )
