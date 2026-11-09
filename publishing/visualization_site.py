"""What a visualization tag becomes: a site link on GitHub, a player on the site.

On GitHub the tag's body is a localized link to the same example on the site,
written by ``metadata generate`` and checked exactly by ``publishing check``.
The site projection replaces the whole tag with a player element that embeds
the example's trace; the course's site assets render it.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata

from .visualization_tags import Tag, scan_document

LINK_LABELS = {
    'en': '▶ Step through this example on the course site',
    'ru': '▶ Пошаговое выполнение на сайте курса',
}
_HEADING = re.compile(r'^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$')
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')


_CODE_SPAN = re.compile(r'(`+)(.+?)(?<!`)\1(?!`)')


def _plain_inline(text: str) -> str:
    """Text content of inline Markdown outside code spans."""
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'(\*\*|__|~~)(.*?)\1', r'\2', text)
    text = re.sub(r'(?<!\w)[*_](?=\S)(.*?)(?<=\S)[*_](?!\w)', r'\1', text)
    # Astro's smartypants turns dash runs into dashes the slugger then drops.
    text = text.replace('---', '\u2014').replace('--', '\u2013')
    text = re.sub(r'\\([!-/:-@\[-`{-~])', r'\1', text)
    return html.unescape(text)


def _plain(heading: str) -> str:
    """The text content Markdown renders for a heading's inline syntax.

    Code spans are literal: no entities, tags or emphasis inside them.
    """
    parts = []
    last = 0
    for span in _CODE_SPAN.finditer(heading):
        parts.append(_plain_inline(heading[last:span.start()]))
        content = span.group(2)
        if content.startswith(' ') and content.endswith(' ') and content.strip():
            content = content[1:-1]
        parts.append(content)
        last = span.end()
    parts.append(_plain_inline(heading[last:]))
    return ''.join(parts)


def _slug(text: str) -> str:
    """github-slugger, which Astro uses for heading ids."""
    kept = ''.join(ch for ch in text.lower()
                   if ch in ' -_' or ch.isalnum() or unicodedata.category(ch)[0] == 'M')
    return kept.replace(' ', '-')


def heading_anchors(text: str) -> list[tuple[int, str]]:
    """(offset, id) of every heading the site renders, deduplicated per page.

    A lesson's only H1 becomes the page title, so it gets no id in the content.
    """
    headings = []
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        plain = line.rstrip('\r\n')
        opening = _FENCE.match(plain)
        if fence:
            if opening and opening.group(1)[0] == fence[0] and len(opening.group(1)) >= len(fence) \
                    and not plain.strip()[len(opening.group(1)):].strip():
                fence = None
        elif opening:
            fence = opening.group(1)
        else:
            match = _HEADING.match(plain)
            if match:
                headings.append((offset, len(match.group(1)), _plain(match.group(2))))
        offset += len(line)
    if sum(1 for _, level, _ in headings if level == 1) == 1:
        headings = [heading for heading in headings if heading[1] != 1]
    occurrences: dict[str, int] = {}
    anchors = []
    for offset, _, title in headings:
        slug = original = _slug(title)
        while slug in occurrences:
            occurrences[original] += 1
            slug = f'{original}-{occurrences[original]}'
        occurrences[slug] = 0
        anchors.append((offset, slug))
    return anchors


def link_label(language: str, template: str | None = None, labels=None) -> str:
    """The course's label for a template override, else the built-in step-through label."""
    configured = (labels or {}).get(template, {}) if template else {}
    return configured.get(language) or LINK_LABELS.get(language, LINK_LABELS['en'])


def link_body(language: str, page_url: str, anchor: str | None, label: str | None = None) -> str:
    label = label or link_label(language)
    target = page_url + (f'#{anchor}' if anchor else '')
    return f'\n\n[{label}]({target})\n\n'


def with_site_links(text: str, language: str, page_url: str, labels=None) -> str:
    """Rewrite every tag body to its link; the rest of the text is untouched.

    ``labels`` maps a template override to per-language link labels.
    """
    anchors = heading_anchors(text)
    for tag in reversed(scan_document(text).tags):
        anchor = next((slug for offset, slug in reversed(anchors) if offset < tag.start), None)
        label = link_label(language, tag.template, labels)
        body = link_body(language, page_url, anchor, label)
        text = text[:tag.body_start] + body + text[tag.body_end:]
    return text


def player(trace: str) -> str:
    """One raw-HTML line, so Markdown neither splits nor rewrites the trace."""
    data = json.dumps(json.loads(trace), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    data = data.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    return f'<div class="course-visualization"><script type="application/json">{data}</script></div>'


def with_players(text: str, load) -> tuple[str, list[Tag]]:
    """Replace each tag with its player; ``load(tag)`` returns its trace or None.

    Returns the projected text and the tags that have no trace.
    """
    missing = []
    for tag in reversed(scan_document(text).tags):
        trace = load(tag)
        if trace is None:
            missing.append(tag)
            continue
        text = text[:tag.start] + player(trace) + text[tag.end:]
    return text, missing[::-1]


def broken_site_links(repo, config, pages_url: str, dist) -> list[str]:
    """Tag links whose page or heading id is missing from the built site.

    The anchors are computed, not rendered, so this checks them against
    the renderer's own output after a real build.
    """
    from pathlib import Path
    from .visualization_traces import markdown_files
    if config.visualizations is None:
        return []
    prefix = pages_url.rstrip('/') + '/'
    link = re.compile(r'\]\((' + re.escape(prefix) + r'[^)#\s]*)(?:#([^)\s]+))?\)')
    errors = []
    ids: dict[Path, set[str]] = {}
    for path in markdown_files(repo, config.visualizations):
        text = path.read_text(encoding='utf-8')
        for tag in scan_document(text).tags:
            found = link.search(text, tag.body_start, tag.body_end)
            if found is None:
                continue  # publishing check reports missing links
            page = Path(dist) / found.group(1)[len(prefix):] / 'index.html'
            if page not in ids:
                ids[page] = (set(re.findall(r'\bid="([^"]+)"', page.read_text(encoding='utf-8')))
                             if page.is_file() else None)
            where = f'{path.relative_to(repo)}:{tag.line}: [VIS]'
            if ids[page] is None:
                errors.append(f'{where} site link points to a missing page: {found.group(1)}')
            elif found.group(2) and found.group(2) not in ids[page]:
                errors.append(f'{where} site link anchor #{found.group(2)} is not a heading id '
                              f'on the built page')
    return errors
