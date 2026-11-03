"""Local media generation/upload and dependency-free referenced-asset validation."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .visualization_config import VisualizationOptions, contained_path
from .visualization_tags import ASSET_URL, render_marker, scan_document


class VisualizationError(Exception):
    pass


def discover_files(repo: Path, options: VisualizationOptions, selected_paths=None) -> list[Path]:
    files = set()
    selected = None if selected_paths is None else {Path(p).resolve() for p in selected_paths}
    for root in options.roots:
        directory = contained_path(repo, root)
        for path in directory.rglob('*.md'):
            if not path.resolve().is_relative_to(repo.resolve()):
                raise VisualizationError(f'{path}: [VIS] source symlink escapes repository')
            if selected is None or path.resolve() in selected:
                files.add(path)
    return sorted(files)


def _load_manifest(path: Path) -> dict:
    if not path.exists():
        return {'version': 1, 'assets': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('assets'), list):
            raise ValueError('expected version 1 and an assets list')
        for entry in data['assets']:
            if (not isinstance(entry, dict)
                    or not isinstance(entry.get('source'), str)
                    or not isinstance(entry.get('template'), str)
                    or entry.get('type') not in {'animation', 'static'}
                    or not isinstance(entry.get('src'), str)
                    or not ASSET_URL.fullmatch(entry['src'])):
                raise ValueError('invalid asset entry')
        return data
    except (OSError, ValueError) as exc:
        raise VisualizationError(f'{path}: [VIS] invalid asset manifest: {exc}') from exc


def _save_manifest(path: Path, manifest: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     prefix='.assets-', delete=False) as output:
        temporary = Path(output.name)
        output.write(content)
    temporary.replace(path)


def asset_exists(url: str) -> bool:
    """Only confirmed absence permits replacement; outages must preserve existing assets."""
    if not ASSET_URL.fullmatch(url):
        return False
    failure = None
    for _ in range(2):
        try:
            try:
                with urlopen(Request(url, method='HEAD', headers={'Cache-Control': 'no-cache'}),
                             timeout=20) as response:
                    if 200 <= response.status < 300:
                        return True
                    raise OSError(f'unexpected HTTP status {response.status}')
            except HTTPError as exc:
                if exc.code in {404, 410}:
                    exc.close()
                    return False
                if exc.code not in {403, 405, 501}:
                    raise
                exc.close()
            with urlopen(Request(url, headers={'Range': 'bytes=0-0',
                                               'Cache-Control': 'no-cache'}), timeout=20) as response:
                if 200 <= response.status < 300:
                    return True
                raise OSError(f'unexpected HTTP status {response.status}')
        except HTTPError as exc:
            if exc.code in {404, 410}:
                exc.close()
                return False
            failure = str(exc)
            exc.close()
        except (URLError, OSError, ValueError) as exc:
            failure = str(exc)
    raise VisualizationError(f'cannot verify asset availability after two attempts: {failure}')


def _command(argv: list[str], *, timeout=120) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                encoding='utf-8', timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VisualizationError(f'command failed ({argv[0]}): {exc}') from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise VisualizationError(f'{Path(argv[0]).name} exited {result.returncode}: {detail[-2000:]}')
    return result.stdout


def upload_asset(path: Path, options: VisualizationOptions, body_file: Path) -> str:
    """Upload once, then recover the durable comment without repeating its upload."""
    if path.stat().st_size > 100 * 1024 * 1024:
        raise VisualizationError('asset exceeds the 100 MiB GitHub attachment limit')
    body_file.write_text('Generated course visualization. Referenced assets are retained.\n', encoding='utf-8')
    failure = None
    comment_id = None
    for _ in range(2):
        try:
            comment = _command(['gh', 'issue', 'comment', str(options.issue),
                '--repo', options.repository, '--body-file', str(body_file), '--attach', str(path)])
            match = re.search(r'#issuecomment-(\d+)', comment)
            if not match:
                # The server may already have accepted it. Avoid another upload
                # when the command succeeded but returned an unexpected result.
                raise VisualizationError('gh created a comment but did not return its URL; '
                                         'inspect the upload issue before retrying')
            comment_id = match.group(1)
            break
        except VisualizationError as exc:
            failure = exc
            if 'did not return its URL' in str(exc):
                raise
    if comment_id is None:
        raise VisualizationError(f'asset upload failed after two attempts: {failure}')
    for _ in range(2):
        try:
            raw = _command(['gh', 'api',
                f'repos/{options.repository}/issues/comments/{comment_id}'])
            body = json.loads(raw).get('body', '')
            urls = re.findall(r'https://github\.com/user-attachments/assets/[A-Za-z0-9-]+', body)
            if len(set(urls)) != 1:
                raise VisualizationError('uploaded comment must contain exactly one asset URL')
            return urls[0]
        except (VisualizationError, ValueError) as exc:
            failure = exc
    raise VisualizationError(f'cannot recover uploaded comment {comment_id} after two attempts: '
                             f'{failure}; asset retained on issue {options.issue}')


def _documents(repo, options, selected_paths):
    for path in discover_files(repo, options, selected_paths):
        text = path.read_text(encoding='utf-8')
        yield path, text, scan_document(text, path.relative_to(repo))


def validate(repo: Path, config, selected_paths=None, *, remote=False, exists=None) -> list[str]:
    """Read-only: never invoke a compiler, renderer, browser or upload command."""
    options = config.visualizations
    if options is None:
        return []
    exists = exists or asset_exists
    try:
        manifest = _load_manifest(contained_path(repo, options.manifest))
        documents = list(_documents(repo, options, selected_paths))
    except (VisualizationError, ValueError, OSError) as exc:
        return [str(exc)]
    errors = []
    checked = {}
    for path, text, scanned in documents:
        errors.extend(scanned.errors)
        for tag in scanned.tags:
            location = f'{path.relative_to(repo)}:{tag.line}: [VIS]'
            entries = [entry for entry in manifest['assets']
                if entry['source'] == tag.source.source and entry['template'] == tag.template
                and entry['type'] == tag.type and entry['src'] == tag.src]
            if not entries:
                errors.append(f'{location} missing or stale asset; run visualizations generate')
            if not tag.src:
                continue
            expected = render_marker(tag, tag.src)
            if text[tag.start:tag.embed_end] != expected:
                errors.append(f'{location} missing or stale media embed; run visualizations generate')
            if remote:
                if tag.src not in checked:
                    try:
                        checked[tag.src] = exists(tag.src)
                    except VisualizationError as exc:
                        checked[tag.src] = str(exc)
                if isinstance(checked[tag.src], str):
                    errors.append(f'{location} {checked[tag.src]}; retry the check')
                elif not checked[tag.src]:
                    errors.append(f'{location} referenced asset is unavailable: {tag.src}')
    return errors


def generate(repo: Path, config, selected_paths=None, *, exists=None,
             command=None, uploader=None) -> list[str]:
    """Generate only tagged sources; reuse exact source/template/media across languages."""
    options = config.visualizations
    if options is None:
        return []
    exists = exists or asset_exists
    command = command or _command
    uploader = uploader or upload_asset
    try:
        documents = list(_documents(repo, options, selected_paths))
        errors = [error for _, _, scanned in documents for error in scanned.errors]
        if errors:
            return errors
        if not any(scanned.tags for _, _, scanned in documents):
            return []
        manifest_path = contained_path(repo, options.manifest)
        manifest = _load_manifest(manifest_path)
        renderer = contained_path(repo, options.templates + '/generate.py')
        revision = command([sys.executable, str(renderer), 'revision']).strip()
        if not revision:
            raise VisualizationError('renderer revision must not be empty')
    except (VisualizationError, ValueError, OSError) as exc:
        return [str(exc)]
    # Cache existence responses and freshly generated assets across files/languages.
    checked = {}
    with tempfile.TemporaryDirectory(prefix='course-visualizations-') as directory:
        scratch = Path(directory)
        for path, text, scanned in documents:
            replacements = []
            for tag in scanned.tags:
                location = f'{path.relative_to(repo)}:{tag.line}: [VIS]'
                try:
                    matching = [entry for entry in reversed(manifest['assets'])
                        if entry['source'] == tag.source.source and entry['template'] == tag.template
                        and entry['type'] == tag.type and entry.get('renderer_revision') == revision]
                    src = None
                    for entry in matching:
                        url = entry['src']
                        if url not in checked:
                            checked[url] = exists(url)
                        if checked[url]:
                            src = url
                            break
                    if src is None:
                        source = scratch / 'snippet.cpp'
                        source.write_text(tag.source.source + '\n', encoding='utf-8')
                        print(f'visualizations: probing {path.relative_to(repo)}:{tag.line}', flush=True)
                        probe = json.loads(command([sys.executable, str(renderer), 'probe',
                                                   '--source', str(source)]))
                        if probe.get('supported') is not True:
                            raise VisualizationError(f'unsupported snippet: {probe.get("reason", "unknown reason")}')
                        asset = scratch / ('asset.mp4' if tag.type == 'animation' else 'asset.svg')
                        if asset.exists():
                            asset.unlink()
                        print(f'visualizations: rendering {path.relative_to(repo)}:{tag.line}', flush=True)
                        command([sys.executable, str(renderer), 'render', '--source', str(source),
                            '--output', str(asset), '--type', tag.type, '--template', tag.template],
                            timeout=3600)
                        if not asset.is_file() or asset.stat().st_size == 0:
                            raise VisualizationError('renderer did not create a nonempty asset')
                        print(f'visualizations: uploading {asset.stat().st_size} bytes for '
                              f'{path.relative_to(repo)}:{tag.line}', flush=True)
                        src = uploader(asset, options, scratch / 'upload-body.md')
                        if not ASSET_URL.fullmatch(src):
                            raise VisualizationError('uploader returned an invalid asset URL')
                        manifest['assets'].append({'source': tag.source.source, 'template': tag.template,
                            'type': tag.type, 'src': src, 'renderer_revision': revision})
                        _save_manifest(manifest_path, manifest)
                        checked[src] = True
                    replacements.append((tag.start, tag.embed_end, render_marker(tag, src)))
                except (VisualizationError, ValueError, OSError) as exc:
                    errors.append(f'{location} {exc}; existing media retained')
            updated = text
            for start, end, replacement in reversed(replacements):
                updated = updated[:start] + replacement + updated[end:]
            if updated != text:
                path.write_text(updated, encoding='utf-8')
    return errors


def _run(repo: Path, args, *, check: bool) -> int:
    from .config import ConfigError, load_config
    try:
        config = load_config(repo)
        errors = validate(repo, config, remote=True) if check or getattr(args, 'check', False) else generate(repo, config)
    except (ConfigError, VisualizationError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f'error: {error}', file=sys.stderr)
    if not errors:
        print('visualizations: OK')
    return 1 if errors else 0


def run_visualizations_generate(course_repo: Path, args) -> int:
    return _run(course_repo, args, check=False)


def run_visualizations_check(course_repo: Path, args) -> int:
    return _run(course_repo, args, check=True)
