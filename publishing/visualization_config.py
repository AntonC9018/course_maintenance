"""Optional course-owned renderer and asset policy, independent of media tooling."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class VisualizationOptions:
    templates: str = 'visualizations'
    roots: tuple[str, ...] = ()
    manifest: str = 'visualizations/assets.json'
    repository: str = ''
    issue: int = 0


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
    unknown = set(raw) - {'templates', 'roots', 'manifest', 'repository', 'issue'}
    if unknown:
        raise ValueError('unknown visualizations fields: ' + ', '.join(sorted(unknown)))
    roots = raw.get('roots')
    if not isinstance(roots, list) or not roots or any(not isinstance(p, str) for p in roots):
        raise ValueError('visualizations.roots must be a non-empty list of relative directories')
    if len(roots) != len(set(roots)):
        raise ValueError('visualizations.roots must not contain duplicates')
    repository = raw.get('repository')
    if not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('visualizations.repository must be OWNER/REPO')
    issue = raw.get('issue')
    if type(issue) is not int or issue <= 0:
        raise ValueError('visualizations.issue must be a positive issue number')
    templates = raw.get('templates', 'visualizations')
    manifest = raw.get('manifest', 'visualizations/assets.json')
    for value in [templates, manifest, *roots]:
        contained_path(repo, value)
    for i, root in enumerate(roots):
        if any(root.startswith(other + '/') or other.startswith(root + '/')
               for other in roots[:i]):
            raise ValueError('visualizations.roots must not overlap')
    return VisualizationOptions(templates, tuple(roots), manifest, repository, issue)
