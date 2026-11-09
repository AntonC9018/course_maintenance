"""Paired visualization markers and the C++ source fence each one illustrates.

A tag is two HTML comments inside an answer-style ``<details>`` block::

    <!-- <visualization> -->
    ...maintenance-owned body...
    <!-- </visualization> -->

``template="name"`` on the opening marker overrides the tracer's own choice.
The source is the nearest preceding top-level code fence, which must be C++.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

CPP_LANGUAGES = frozenset({'cpp', 'c++', 'cxx'})
_OPEN_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})([^\n]*)$')
_DETAILS = re.compile(r'</?details\b[^>]*>|</?visualization\b[^>]*>', re.IGNORECASE)
_MENTIONS_TAG = re.compile(r'<\s*/?\s*visualization\b', re.IGNORECASE)
_OPENING = re.compile(r'<visualization(?:\s+template="([a-z][a-z0-9-]*)")?\s*>')
_CLOSING = re.compile(r'</visualization\s*>', re.IGNORECASE)
_CLOSE_MARKER = re.compile(r'<!--\s*</visualization\s*>\s*-->', re.IGNORECASE)
_BLOCK_BOUNDARY = re.compile(
    r'<!--\s*<\s*/?\s*visualization\b|</?details\b|^ {0,3}(?:`{3,}|~{3,})',
    re.IGNORECASE | re.MULTILINE)


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
    # None lets the tracer choose; only an explicit override is recorded.
    template: str | None
    source: Fence
    body_start: int
    body_end: int


@dataclass
class ScanResult:
    fences: list[Fence] = field(default_factory=list)
    tags: list[Tag] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _tag_problem(content: str, depth: int, source: Fence | None) -> str | None:
    if _CLOSING.fullmatch(content):
        return 'closing visualization marker has no matching opening marker'
    if '<!--' in content:
        return 'nested or unclosed visualization comment'
    if not _OPENING.fullmatch(content):
        return 'expected <visualization> or <visualization template="name">'
    if depth == 0:
        return 'visualization must be inside a details block'
    if source is None:
        return 'no preceding source fence outside details'
    if source.language not in CPP_LANGUAGES:
        return 'nearest preceding outside-details fence must be C++'
    return None


def scan_document(text: str, path: str | Path = '<markdown>') -> ScanResult:
    """Scan without interpreting fenced HTML or answer-only code as source.

    Character offsets let callers replace a tag's body without touching the rest.
    """
    result = ScanResult()
    depth = 0
    fence = None
    last_source = None
    position = 0
    lines = text.splitlines(keepends=True)
    index = 0

    def error(offset, message):
        result.errors.append(f'{path}:{text.count(chr(10), 0, offset) + 1}: [VIS] {message}')

    while index < len(lines):
        line = lines[index]
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
            fence = (marker, position, position + len(line), depth, language, index + 1)
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
                    if _MENTIONS_TAG.search(text, comment):
                        error(comment, 'unclosed visualization comment')
                    return result
                finish = close + 3
                content = text[comment + 4:close].strip()
                if _MENTIONS_TAG.search(content):
                    problem = _tag_problem(content, depth, last_source)
                    closing = None if problem else _CLOSE_MARKER.search(text, finish)
                    if not problem and (closing is None
                                        or _BLOCK_BOUNDARY.search(text, finish, closing.start())):
                        problem = 'opening marker needs a closing <!-- </visualization> --> before the next block'
                    if problem:
                        error(comment, problem)
                        if problem.startswith('nested'):
                            return result
                    else:
                        result.tags.append(Tag(
                            comment, closing.end(), text.count('\n', 0, comment) + 1,
                            _OPENING.fullmatch(content).group(1), last_source,
                            finish, closing.start()))
                        finish = closing.end()
                cursor = finish
                if finish > line_end:
                    while index < len(lines) and position + len(lines[index]) < finish:
                        position += len(lines[index])
                        index += 1
                    line_end = position + len(lines[index]) if index < len(lines) else len(text)
            elif detail is not None:
                if _MENTIONS_TAG.match(detail.group()):
                    error(detail.start(), 'visualization marker must be inside an HTML comment')
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
        result.errors.append(f'{path}:{fence[-1]}: [VIS] unclosed code fence after a visualization')
    return result


def project_visualizations(text: str) -> str:
    """Drop tags from the site projection until the site player renders them."""
    for tag in reversed(scan_document(text).tags):
        text = text[:tag.start] + text[tag.end:]
    return text
