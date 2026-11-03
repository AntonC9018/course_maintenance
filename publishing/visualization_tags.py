"""Visualization markers and their preceding, outside-answer C++ source fences."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re

CPP_LANGUAGES = frozenset({'cpp', 'c++', 'cxx'})
ASSET_URL = re.compile(r'https://github\.com/user-attachments/assets/[A-Za-z0-9-]+\Z')
_OPEN_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})([^\n]*)$')
_DETAILS = re.compile(r'</?details\b[^>]*>|<visualization\b[^>]*>', re.IGNORECASE)
_EMBED = re.compile(
    r'\s*(?:<video\b[^>]*>\s*</video>|<img\b[^>]*>|'
    r'https://github\.com/user-attachments/assets/[A-Za-z0-9-]+(?=[ \t]*(?:\r?\n|$)))',
    re.DOTALL)


def normalize_source(source: str) -> str:
    """Ignore Markdown fence whitespace without changing the C++ statements."""
    return '\n'.join(line.rstrip() for line in source.replace('\r\n', '\n').splitlines()).strip('\n')


@dataclass(frozen=True)
class Fence:
    source: str
    start: int
    end: int
    depth: int
    language: str
    line: int


@dataclass(frozen=True)
class Tag:
    start: int
    end: int
    line: int
    type: str
    template: str
    src: str | None
    source: Fence
    embed_start: int
    embed_end: int


@dataclass
class ScanResult:
    fences: list[Fence] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class _TagParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.attributes = None
        self.error = None

    def handle_starttag(self, tag, attrs):
        if tag != 'visualization' or self.attributes is not None:
            self.error = 'expected one visualization tag'
        else:
            names = [key for key, _ in attrs]
            if len(names) != len(set(names)):
                self.error = 'duplicate visualization attribute'
            self.attributes = dict(attrs)

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        if data.strip():
            self.error = 'unexpected text in visualization marker'

    def handle_endtag(self, tag):
        self.error = 'visualization marker must not have a closing tag'


def scan_document(text: str, path: str | Path = '<markdown>') -> ScanResult:
    """Scan without interpreting fenced HTML or answer-only code as source.

    Markers are HTML comments containing one visualization tag. A source is
    the nearest preceding *top-level* code fence, which must be C++.
    Character offsets permit callers to replace just managed marker/embed text.
    """
    result = ScanResult()
    depth = 0
    fence = None
    last_source = None
    position = 0
    lines = text.splitlines(keepends=True)
    index = 0

    def error(line, message):
        result.errors.append(f'{path}:{line}: [VIS] {message}')

    while index < len(lines):
        line = lines[index]
        number = index + 1
        plain = line.rstrip('\r\n')
        if fence is not None:
            marker, start, body_start, open_depth, language, open_line = fence
            if re.fullmatch(r' {0,3}' + re.escape(marker[0]) + '{' + str(len(marker)) + r',}\s*', plain):
                found = Fence(normalize_source(text[body_start:position]), start,
                              position + len(line), open_depth, language, open_line)
                result.fences.append(found)
                if open_depth == 0:
                    last_source = found
                fence = None
            position += len(line)
            index += 1
            continue
        match = _OPEN_FENCE.match(plain)
        if match:
            marker, info = match.groups()
            language = info.strip().split(None, 1)[0].lower() if info.strip() else ''
            fence = (marker, position, position + len(line), depth, language, number)
            position += len(line)
            index += 1
            continue

        # Process comments and details in lexical order. Comments may span lines;
        # HTML tags mentioned in comments cannot change answer nesting.
        cursor = position
        line_end = position + len(line)
        while cursor < line_end:
            comment = text.find('<!--', cursor, line_end)
            detail = _DETAILS.search(text, cursor, line_end)
            if comment >= 0 and (detail is None or comment < detail.start()):
                close = text.find('-->', comment + 4)
                if close < 0:
                    if '<visualization' in text[comment:]:
                        error(number, 'unclosed visualization comment')
                    return result
                finish = close + 3
                content = text[comment + 4:close].strip()
                if re.search(r'<\s*visualization\b', content, re.IGNORECASE):
                    if '<!--' in content:
                        error(number, 'nested or unclosed visualization comment')
                        return result
                    parser = _TagParser()
                    try:
                        parser.feed(content)
                        parser.close()
                    except Exception as exc:
                        parser.error = str(exc)
                    attrs = parser.attributes or {}
                    problem = parser.error
                    if not re.fullmatch(r'<visualization\b[^>]*?/?>', content, re.DOTALL):
                        problem = 'expected one complete visualization tag'
                    elif set(attrs) - {'type', 'template', 'src'}:
                        problem = 'unknown visualization attribute'
                    elif attrs.get('type') not in {'static', 'animation'}:
                        problem = 'type must be static or animation'
                    elif 'template' in attrs and not re.fullmatch(r'[a-z][a-z0-9-]*', attrs['template'] or ''):
                        problem = 'invalid template identifier'
                    elif 'src' in attrs and not ASSET_URL.fullmatch(attrs['src'] or ''):
                        problem = 'src must be a GitHub user-attachment asset URL'
                    elif depth == 0:
                        problem = 'visualization must be inside an answer details block'
                    elif last_source is None:
                        problem = 'no preceding source fence outside details'
                    elif last_source.language not in CPP_LANGUAGES:
                        problem = 'nearest preceding outside-details fence must be C++'
                    if problem:
                        error(text.count('\n', 0, comment) + 1, problem)
                    else:
                        embed = _EMBED.match(text, finish)
                        result.tags.append(Tag(comment, finish,
                            text.count('\n', 0, comment) + 1, attrs['type'],
                            attrs.get('template', 'expression-timeline'), attrs.get('src'),
                            last_source, finish, embed.end() if embed else finish))
                cursor = finish
                if finish > line_end:
                    while index < len(lines) and position + len(lines[index]) < finish:
                        position += len(lines[index])
                        index += 1
                    line_end = position + len(lines[index]) if index < len(lines) else len(text)
            elif detail is not None:
                if detail.group().lower().startswith('<visualization'):
                    error(number, 'visualization marker must be inside an HTML comment')
                elif detail.group().startswith('</'):
                    depth = max(0, depth - 1)
                else:
                    depth += 1
                cursor = detail.end()
            else:
                break
        if index >= len(lines):
            break
        position += len(lines[index])
        index += 1
    if fence is not None and result.tags:
        error(fence[-1], 'unclosed code fence after a visualization')
    return result


def render_marker(tag: Tag, src: str) -> str:
    attributes = f'type="{tag.type}"'
    if tag.template != 'expression-timeline':
        attributes += f' template="{tag.template}"'
    marker = f'<!-- <visualization {attributes}\n     src="{escape(src, quote=True)}" /> -->'
    if tag.type == 'animation':
        # GitHub only resolves a bare attachment to its CSP-approved media host.
        # A raw video keeps github.com as its src and is blocked before redirecting.
        return marker + '\n\n' + src
    else:
        embed = f'<img alt=""\n  src="{escape(src, quote=True)}">'
    return marker + '\n' + embed


def project_visualizations(text: str) -> str:
    """Turn managed attachment paragraphs into site players without changing sources."""
    scanned = scan_document(text)
    for tag in reversed(scanned.tags):
        if tag.type == 'animation' and tag.src:
            embed = ('\n\n<video controls preload="metadata"\n'
                     f'  src="{escape(tag.src, quote=True)}"></video>')
            text = text[:tag.embed_start] + embed + text[tag.embed_end:]
    return text
