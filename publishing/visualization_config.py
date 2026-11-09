"""Optional course-owned tracer policy, independent of the tracer's own toolchain."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

FIELDS = frozenset({'templates', 'roots', 'shell', 'traces'})


@dataclass(frozen=True)
class VisualizationOptions:
    # Directory holding the course's `generate.py` tracer adapter.
    templates: str = 'visualizations'
    roots: tuple[str, ...] = ()
    # Dev shell of the course flake that pins the tracer toolchain.
    shell: str = 'visualizations'
    # Generated, content-addressed traces; cached by CI and never committed.
    traces: str = '.cache/visualizations'


def contained_path(repo: Path, value: str) -> Path:
    """Reject both lexical escapes and symlinks outside the course repository."""
    if (not isinstance(value, str) or not value or value.strip() != value
            or '\\' in value or value.startswith('/')
            or any(part in {'', '.', '..'} for part in value.split('/'))
            or re.match(r'^[A-Za-z]:', value)):
        raise ValueError(f'visualizations path must be canonical and repository-relative: {value!r}')
    target = repo.joinpath(value)
    if not target.resolve().is_relative_to(repo.resolve()):
        raise ValueError(f'visualizations path escapes the repository: {value!r}')
    return target


def parse_visualizations(raw: object, repo: Path) -> VisualizationOptions | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError('visualizations must be an object')
    unknown = set(raw) - FIELDS
    if unknown:
        raise ValueError('unknown visualizations fields: ' + ', '.join(sorted(unknown)))
    roots = raw.get('roots')
    if not isinstance(roots, list) or not roots or any(not isinstance(p, str) for p in roots):
        raise ValueError('visualizations.roots must be a non-empty list of relative directories')
    if len(roots) != len(set(roots)):
        raise ValueError('visualizations.roots must not contain duplicates')
    defaults = VisualizationOptions()
    templates = raw.get('templates', defaults.templates)
    traces = raw.get('traces', defaults.traces)
    shell = raw.get('shell', defaults.shell)
    if not isinstance(shell, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', shell):
        raise ValueError('visualizations.shell must name a dev shell of the course flake')
    for value in [templates, traces, *roots]:
        contained_path(repo, value)
    for i, root in enumerate(roots):
        if any(root.startswith(other + '/') or other.startswith(root + '/')
               for other in roots[:i]):
            raise ValueError('visualizations.roots must not overlap')
    return VisualizationOptions(templates, tuple(roots), shell, traces)
