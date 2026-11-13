"""Validated, optional course policy in course-publishing.json.

Toolchain pins and algorithms stay shared; course paths, presentation,
deployment expectations, and smoke probes are data owned by each course.
"""

from dataclasses import dataclass, field
from pathlib import Path
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CiOptions:
    maintenance_paths: tuple[str, ...] | None = None
    run_compatibility_tests: bool = True
    required_pr_label: str | None = None


@dataclass(frozen=True)
class MaintenanceOptions:
    heading_numbering: str = "section"


@dataclass(frozen=True)
class DeploymentOptions:
    branch: str = "master"
    pages_url: str | None = None
    required_status_checks: tuple[str, ...] = ("validate",)
    require_pull_requests: bool = False
    enforce_admins: bool = False


@dataclass(frozen=True)
class SmokeCheck:
    label: str
    paths: tuple[str, ...]
    contains: str | None = None


@dataclass(frozen=True)
class SmokeOptions:
    checks: tuple[SmokeCheck, ...] = ()
    retries: int = 30
    retry_delay_seconds: int = 10
    timeout_seconds: int = 30


@dataclass(frozen=True)
class NavigationOptions:
    group_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    subject_order: tuple[str, ...] = ()
    lab_prefixes: tuple[str, ...] = ()
    last_lessons: tuple[str, ...] = ()
    index_labels: dict[str, str] = field(default_factory=dict)
    source_labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PlaygroundOptions:
    source: str = "visualizations/player"
    route: str = "playground"
    sidebar_group: str = "cpp"
    label: str = "Execution Playground"
    translations: dict[str, str] = field(default_factory=dict)


def _object(raw, name, allowed):
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object")
    unknown = set(raw) - set(allowed)
    if unknown:
        raise ValueError(f"{name} has unknown fields {sorted(unknown)}")
    return raw


def _strings(raw, name):
    if not isinstance(raw, list) or any(
            not isinstance(x, str) or not x.strip() for x in raw):
        raise ValueError(f"{name} must be a list of nonempty strings")
    if len(set(raw)) != len(raw):
        raise ValueError(f"{name} must not contain duplicates")
    return tuple(raw)


def _bool(raw, name):
    if type(raw) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return raw


def _relative(raw, name):
    if (not isinstance(raw, str) or not raw or raw.strip() != raw
            or raw.startswith(("/", "./")) or "\\" in raw
            or ":" in raw or any(p in ("", ".", "..") for p in raw.split("/"))):
        raise ValueError(f"{name} must be a canonical repository-relative path")
    return raw


def _labels(raw, name, languages):
    if not isinstance(raw, dict) or any(
            k not in languages or not isinstance(v, str) or not v.strip()
            for k, v in raw.items()):
        raise ValueError(f"{name} must map configured languages to nonempty labels")
    return dict(raw)


def parse_options(raw, repo: Path, languages):
    """Validate all optional policy blocks; paths resolve against this course."""
    ci_raw = _object(raw.get("ci", {}), "ci", {
        "maintenance_paths", "run_compatibility_tests", "required_pr_label"})
    paths = None
    if "maintenance_paths" in ci_raw:
        paths = _strings(ci_raw["maintenance_paths"], "ci.maintenance_paths")
        if not paths:
            raise ValueError("ci.maintenance_paths must not be empty")
        shared_root = Path(__file__).resolve().parent.parent
        for path in paths:
            _relative(path, "ci.maintenance_paths")
            target = (repo / path).resolve()
            if not target.is_relative_to(repo) or target.is_relative_to(shared_root):
                raise ValueError(f"ci.maintenance_paths selects outside course sources: {path}")
            # Also reject another checkout of this shared tool in fixtures.
            if "course_maintenance" in Path(path).parts or ".git" in Path(path).parts:
                raise ValueError(f"ci.maintenance_paths selects tooling: {path}")
            if not target.exists() or (target.is_file() and target.suffix.lower() != ".md"):
                raise ValueError(f"ci.maintenance_paths must select existing documents: {path}")
    label = ci_raw.get("required_pr_label")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError("ci.required_pr_label must be a nonempty string or null")
    ci = CiOptions(paths, _bool(ci_raw.get("run_compatibility_tests", True),
                               "ci.run_compatibility_tests"), label)

    dep = _object(raw.get("deployment", {}), "deployment", {
        "branch", "pages_url", "required_status_checks", "require_pull_requests", "enforce_admins"})
    branch = dep.get("branch", "master")
    if (not isinstance(branch, str) or not branch or branch.startswith("-")
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", branch)
            or any(p in ("", ".", "..") for p in branch.split("/"))):
        raise ValueError("deployment.branch must be a Git branch name")
    pages = dep.get("pages_url")
    if pages is not None:
        if not isinstance(pages, str):
            raise ValueError("deployment.pages_url must be an HTTP(S) URL")
        parts = urlsplit(pages)
        if (parts.scheme not in ("http", "https") or not parts.netloc
                or parts.username or parts.password or parts.query or parts.fragment):
            raise ValueError("deployment.pages_url must be an HTTP(S) URL without credentials/query/fragment")
        pages = pages.rstrip("/")
    deployment = DeploymentOptions(
        branch, pages,
        _strings(dep.get("required_status_checks", ["validate"]), "deployment.required_status_checks"),
        _bool(dep.get("require_pull_requests", False), "deployment.require_pull_requests"),
        _bool(dep.get("enforce_admins", False), "deployment.enforce_admins"))

    smoke_raw = _object(raw.get("smoke", {}), "smoke", {
        "checks", "retries", "retry_delay_seconds", "timeout_seconds"})
    numbers = {}
    for key, default in (("retries", 30), ("retry_delay_seconds", 10), ("timeout_seconds", 30)):
        value = smoke_raw.get(key, default)
        minimum = 0 if key == "retry_delay_seconds" else 1
        if type(value) is not int or value < minimum:
            raise ValueError(f"smoke.{key} must be an integer >= {minimum}")
        numbers[key] = value
    checks_raw = smoke_raw.get("checks", [])
    if not isinstance(checks_raw, list):
        raise ValueError("smoke.checks must be a list")
    checks = []
    for item in checks_raw:
        item = _object(item, "smoke.checks[]", {"label", "paths", "contains"})
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("smoke.checks[].label must be nonempty")
        probe_paths = _strings(item.get("paths"), "smoke.checks[].paths")
        if not probe_paths:
            raise ValueError("smoke.checks[].paths must not be empty")
        for path in probe_paths:
            if ((not path.startswith("/") and path != "{root_route}") or path.startswith("//") or "\\" in path
                    or any(p == ".." for p in path.split("/"))):
                raise ValueError("smoke paths must be site-relative URLs starting with /")
        contains = item.get("contains")
        if contains is not None and (not isinstance(contains, str) or not contains):
            raise ValueError("smoke.checks[].contains must be a nonempty string")
        checks.append(SmokeCheck(label, probe_paths, contains))
    smoke = SmokeOptions(tuple(checks), **numbers)

    nav_raw = _object(raw.get("navigation", {}), "navigation", {
        "group_labels", "subject_order", "lab_prefixes", "last_lessons", "index_labels", "source_labels"})
    group_labels = nav_raw.get("group_labels", {})
    if not isinstance(group_labels, dict):
        raise ValueError("navigation.group_labels must be an object")
    labels = {}
    for group, translations in group_labels.items():
        _relative(group, "navigation.group_labels key")
        labels[group] = _labels(translations, "navigation.group_labels", languages)
    lists = {}
    for key in ("subject_order", "lab_prefixes", "last_lessons"):
        lists[key] = _strings(nav_raw.get(key, []), f"navigation.{key}")
        for path in lists[key]:
            _relative(path, f"navigation.{key}")
    navigation = NavigationOptions(
        labels, **lists,
        index_labels=_labels(nav_raw.get("index_labels", {}), "navigation.index_labels", languages),
        source_labels=_labels(nav_raw.get("source_labels", {}), "navigation.source_labels", languages))

    overrides = raw.get("slug_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("slug_overrides must map source paths below a language root to language-less routes")
    for source, route in overrides.items():
        _relative(source, "slug_overrides source")
        _relative(route, "slug_overrides route")
        if not source.lower().endswith(".md") or not re.fullmatch(r"[a-z0-9][a-z0-9/-]*", route):
            raise ValueError("slug_overrides must map .md source paths to lowercase routes")
    backlink_labels = _labels(raw.get("backlink_labels", {}), "backlink_labels", languages)
    maintenance_raw = _object(raw.get("maintenance", {}), "maintenance", {"heading_numbering"})
    numbering = maintenance_raw.get("heading_numbering", "section")
    if numbering not in ("document", "section"):
        raise ValueError("maintenance.heading_numbering must be 'document' or 'section'")
    maintenance = MaintenanceOptions(numbering)
    return ci, deployment, smoke, navigation, dict(overrides), backlink_labels, maintenance


PLAYGROUND_REQUIRED_FILES = (
    "playground.html",
    "playground.css",
    "playground.js",
    "clang-worker.js",
    "player.css",
)


def parse_playground(raw: object, repo: Path, languages) -> PlaygroundOptions | None:
    if raw is None:
        return None
    pg = _object(raw, "playground", {
        "source", "route", "sidebar_group", "label", "translations"})
    defaults = PlaygroundOptions()
    source = _relative(pg.get("source", defaults.source), "playground.source")
    source_dir = (repo / Path(*source.split("/"))).resolve()
    if not source_dir.is_relative_to(repo.resolve()) or not source_dir.is_dir():
        raise ValueError(f"playground.source directory not found: {source!r}")
    for req in PLAYGROUND_REQUIRED_FILES:
        if not (source_dir / req).is_file():
            raise ValueError(f"playground.source is missing {req!r}: {source!r}")
    route = _relative(pg.get("route", defaults.route), "playground.route")
    if not re.fullmatch(r"[a-z0-9][a-z0-9/-]*", route):
        raise ValueError("playground.route must be a lowercase route")
    sidebar_group = _relative(
        pg.get("sidebar_group", defaults.sidebar_group),
        "playground.sidebar_group")
    label = pg.get("label", defaults.label)
    if not isinstance(label, str) or not label.strip():
        raise ValueError("playground.label must be a nonempty string")
    translations = _labels(
        pg.get("translations", {}), "playground.translations", languages)
    return PlaygroundOptions(
        source=source,
        route=route,
        sidebar_group=sidebar_group,
        label=label,
        translations=translations,
    )

