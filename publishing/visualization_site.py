"""What a visualization tag becomes: a site link on GitHub, a player on the site.

On GitHub the tag's body is a localized link to the same example on the site,
written by ``metadata generate`` and checked exactly by ``publishing check``.
The site projection replaces the whole tag with a player element that embeds
the example's trace; the course's site assets render it.
"""
from __future__ import annotations

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


def _plain(heading: str) -> str:
    """The text content Markdown renders for a heading's inline syntax."""
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', heading)
    text = re.sub(r'(`+)(.*?)\1', r'\2', text)
    text = re.sub(r'(\*\*|__|~~)(.*?)\1', r'\2', text)
    text = re.sub(r'(?<!\w)[*_](?=\S)(.*?)(?<=\S)[*_](?!\w)', r'\1', text)
    return re.sub(r'<[^>]*>', '', text)


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


def link_body(language: str, page_url: str, anchor: str | None) -> str:
    label = LINK_LABELS.get(language, LINK_LABELS['en'])
    target = page_url + (f'#{anchor}' if anchor else '')
    return f'\n\n[{label}]({target})\n\n'


def with_site_links(text: str, language: str, page_url: str) -> str:
    """Rewrite every tag body to its link; the rest of the text is untouched."""
    anchors = heading_anchors(text)
    for tag in reversed(scan_document(text).tags):
        anchor = next((slug for offset, slug in reversed(anchors) if offset < tag.start), None)
        text = text[:tag.body_start] + link_body(language, page_url, anchor) + text[tag.body_end:]
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
