"""Course-owned static files shipped with the site and included on every page."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .visualization_config import contained_path

PUBLIC_DIR = 'site-assets'


@dataclass(frozen=True)
class SiteAssets:
    # Repository-relative files; scripts load deferred, styles as stylesheets.
    scripts: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()

    def files(self) -> tuple[str, ...]:
        return self.scripts + self.styles


def parse_site_assets(raw: object, repo: Path) -> SiteAssets:
    if raw is None:
        return SiteAssets()
    if not isinstance(raw, dict) or set(raw) - {'scripts', 'styles'}:
        raise ValueError('site_assets must be an object with optional scripts and styles lists')
    lists = {}
    for kind, suffix in (('scripts', '.js'), ('styles', '.css')):
        values = raw.get(kind, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError(f'site_assets.{kind} must be a list of repository-relative files')
        for value in values:
            if not value.endswith(suffix):
                raise ValueError(f'site_assets.{kind} entries must end in {suffix}: {value!r}')
            if not contained_path(repo, value).is_file():
                raise ValueError(f'site_assets.{kind} file not found: {value!r}')
        lists[kind] = tuple(values)
    if len(set(lists['scripts'] + lists['styles'])) != len(lists['scripts'] + lists['styles']):
        raise ValueError('site_assets must not list a file twice')
    return SiteAssets(**lists)


def public_path(path: str) -> str:
    return f'{PUBLIC_DIR}/{path}'


def head_entries(assets: SiteAssets, base: str) -> list[dict]:
    """Starlight `head` entries, in configuration order."""
    prefix = base.rstrip('/') + '/'
    entries = [{'tag': 'link', 'attrs': {'rel': 'stylesheet', 'href': prefix + public_path(p)}}
               for p in assets.styles]
    entries += [{'tag': 'script', 'attrs': {'src': prefix + public_path(p), 'defer': True}}
                for p in assets.scripts]
    return entries


def head_js(assets: SiteAssets, base: str) -> str:
    return json.dumps(head_entries(assets, base), ensure_ascii=False)


def copy_site_assets(assets: SiteAssets, repo: Path, public: Path) -> None:
    for path in assets.files():
        target = public / PUBLIC_DIR / Path(*path.split('/'))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contained_path(repo, path).read_bytes())
