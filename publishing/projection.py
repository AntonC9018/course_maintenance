"""Deterministic Markdown web projections (PROJ-1..PROJ-6 + DIAG-1..DIAG-4).

Builds a disposable, slug-shaped Starlight content tree below an explicit
``--out`` directory (or an auto temp dir outside the source tree). Never
writes into the source tree. Stdlib-only, read-only w.r.t. sources.

Pipeline per lesson (deterministic, sorted):

1. PROJ-1: remove the marked source-backlink block (fence-aware).
2. LINK-2..6: rewrite links via :func:`publishing.links.rewrite_document`
   (canonical/blob/tree, images marked for copying).
3. PROJ-2: keep frontmatter title as sole H1; shift every authored ATX
   heading down one level (``#`` -> ``##``, capped at ``######``) and
   convert Setext ``===`` -> ``##`` / ``---`` -> ``###``. Fenced code
   untouched. After the shift no ``# `` remains, so no duplicate H1.
4. PROJ-3: convert GitHub-friendly inline math ``$`code`$`` into the
   pinned renderer input ``$code$`` (Starlight remark-math / rehype-katex,
   versions pinned in #12). Display ``$$`` blocks are already valid
   remark-math display and pass through unchanged. Ambiguous syntax
   (empty ``$`````$``, ``$`` inside, double backticks, unclosed ``$$``)
   is rejected with PROJ-3 rather than guessed. Fenced code untouched.
   Sources are never normalized.
5. DIAG-1/2/4: convert every `````mermaid`` fence into a deterministic
   static SVG via :mod:`publishing.mermaid` (pinned Playwright/Chromium
   when available, deterministic fallback offline). Invalid diagrams fail
   with source path + Mermaid diagnostic (DIAG-2); IDs normalized for
   repeatability (DIAG-4). No client JS emitted (DIAG-3).
6. PROJ-5: inject renderer-only ``sidebar.order`` derived from source
   numbering (numeric incl ``21a``, unnumbered alphabetical, per
   slug-parent group for SITE-9) plus ``nav.json``. Never written back.
7. PROJ-6: byte-identical outputs for identical inputs/config. No
   timestamps are emitted anywhere (documented here); second build of
   the same inputs is byte-identical.

Outputs below ``<out>`` (all deterministic, no timestamps):

- ``src/content/docs/<slug>.md`` -- projected lessons (mermaid fences
  replaced by inline static SVGs);
- ``mermaid/<flat-slug>-<idx>.svg`` -- static Mermaid SVGs (DIAG-1, never
  committed, DIAG-3);
- ``<copy_rel>`` (``assets/<owner>/<repo>/<repo-rel>``) -- copied images,
  destinations are the verbatim ``rewrite_document`` URLs
  (projection-root-relative placeholders; #11 makes them site-absolute);
- ``astro.config.mjs`` -- placeholder renderer config;
- ``nav.json`` -- sorted renderer nav data (slug/title/order/lang/source);
- ``mermaid/README.md`` -- documents the static SVG directory;
- ``dist/.gitkeep`` -- placeholder (full static site in #11).

PROJ-4: fenced code, tables, nested ``<details>``, raw C++ code spans and
ordinary Markdown pass through untouched (transforms skip fences).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from maintenance.patterns import FENCE_RE, ORDERED_PATTERN

from .metadata import BACKLINK_END, BACKLINK_START, split_frontmatter

_FIX_PROJECTION = "operation: projection build"
_ATX_RE = re.compile(r'^(\s{0,3})(#{1,6})(?:\s+(.*))?$')
_SETEXT_RE = re.compile(r'^\s{0,3}(=+|-+)\s*$')
_TITLE_RE = re.compile(r'^\s*title\s*:\s*(.*)\s*$')
_SIDEBAR_RE = re.compile(r'^\s*sidebar\s*:\s*(.*)\s*$')
_ORDER_RE = re.compile(r'^\s*order\s*:\s*(.*)\s*$')
_CODE_SPAN_RE = re.compile(r'`[^`]*`')


class ProjectionError(Exception):
    def __init__(self, message: str, *, rule: str = "PROJ-3",
                 path: str | Path | None = None,
                 hint: str = _FIX_PROJECTION):
        self.rule = rule
        loc = str(path) if path is not None else "projection"
        super().__init__(f"{loc}: [{rule}] {message}; {hint}")


# -- PROJ-1 ---------------------------------------------------------------

def strip_backlink_lines(body_lines: list[str]) -> list[str]:
    """Remove marked backlink blocks (fence-aware, deterministic)."""
    in_fence = False
    fence_state: list[bool] = []
    for line in body_lines:
        if FENCE_RE.match(line):
            fence_state.append(True)
            in_fence = not in_fence
            continue
        fence_state.append(in_fence)
    starts: list[int] = []
    ends: list[int] = []
    for i, line in enumerate(body_lines):
        if fence_state[i]:
            continue
        s = line.strip()
        if s == BACKLINK_START:
            starts.append(i)
        elif s == BACKLINK_END:
            ends.append(i)
    remove: set[int] = set()
    used: set[int] = set()
    for s in starts:
        nxt = None
        for e in ends:
            if e > s and e not in used:
                nxt = e
                break
        if nxt is not None:
            used.add(nxt)
            for i in range(s, nxt + 1):
                remove.add(i)
        else:
            remove.add(s)
    for e in ends:
        if e not in used:
            remove.add(e)
    return [l for i, l in enumerate(body_lines) if i not in remove]


# -- PROJ-2 ---------------------------------------------------------------

def shift_headings_body(body_lines: list[str]) -> list[str]:
    """Shift every authored heading down one level (fence-aware).

    ATX ``#`` -> ``##`` ... ``#####`` -> ``######``, ``######`` stays.
    Setext ``===`` (H1) -> ``## text``, ``---`` (H2, only when the
    previous line is non-blank paragraph text) -> ``### text``.
    Thematic breaks (``---`` after blank) and fenced code untouched.
    """
    out: list[str] = []
    in_fence = False
    for line in body_lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        m = _ATX_RE.match(line)
        if m:
            leading, hashes, rest = m.group(1), m.group(2), m.group(3)
            # ``####### x`` (7 hashes) does not match (needs space after
            # 1..6 hashes); a bare ``#`` with no space is not a heading.
            # Our regex already requires space-or-EOL after hashes; a line
            # like ``#nospace`` has rest None but hashes followed by text
            # without space -- distinguish: re matched ``#`` + rest?
            # ``_ATX_RE`` with ``(?:\\s+(.*))?`` only matches ``#nospace``
            # as hashes=``#`` rest=None? No: ``#nospace`` -> hashes would
            # try 1 hash then require space, fails, so backtrack? The regex
            # ``(#{1,6})(?:\\s+(.*))?`` on ``#nospace`` matches hashes=``#``
            # with no suffix (rest None) -- that would wrongly treat it as
            # heading. Guard: if rest is None, the line must be exactly
            # hashes (+ whitespace).
            if rest is None:
                stripped = line.strip()
                bare = stripped.lstrip()
                # bare hashes only (e.g. ``#``) -> heading with empty text
                if bare.strip('#') != '':
                    out.append(line)
                    continue
                level = len(hashes)
                new_level = min(level + 1, 6)
                out.append(f"{leading}{'#' * new_level}")
                continue
            level = len(hashes)
            new_level = min(level + 1, 6)
            out.append(f"{leading}{'#' * new_level} {rest}")
            continue
        # Setext underline?
        if _SETEXT_RE.match(line) and out:
            prev = out[-1]
            # underline inside fence already handled; prev must be non-blank
            # paragraph text, not already a heading/fence.
            if prev.strip() == '' or FENCE_RE.match(prev):
                out.append(line)
                continue
            if _ATX_RE.match(prev):
                out.append(line)
                continue
            marks = line.strip()
            if marks.startswith('='):
                out[-1] = f"## {prev.strip()}"
                continue
            # '-' underline: setext H2 only when directly under text.
            out[-1] = f"### {prev.strip()}"
            continue
        out.append(line)
    return out


# -- PROJ-3 ---------------------------------------------------------------

def _is_single_dollar(line: str, pos: int) -> bool:
    if pos < 0 or pos >= len(line) or line[pos] != '$':
        return False
    if pos - 1 >= 0 and line[pos - 1] == '$':
        return False
    if pos + 1 < len(line) and line[pos + 1] == '$':
        return False
    return True


def _convert_inline_line(line: str):
    """Convert valid $`code`$ -> $code$ on one fence-free line.

    Returns (new_line, had_ambiguous). Only single-$ delimiters count;
    $$ display is handled separately. $-inside-code-spans is ordinary
    text, not math.
    """
    spans = [(m.start(), m.end())
             for m in _CODE_SPAN_RE.finditer(line)]
    inside = lambda p: any(s <= p < e for s, e in spans)

    valid_repls: list[tuple[int, int, str]] = []
    handled_before: set[int] = set()
    ambiguous = False

    for s, e in spans:
        before = s - 1
        after = e
        has_before = before >= 0 and line[before] == '$' \
            and not inside(before) and _is_single_dollar(line, before)
        has_after = after < len(line) and line[after] == '$' \
            and not inside(after) and _is_single_dollar(line, after)
        if has_before and has_after:
            handled_before.add(before)
            content = line[s + 1:e - 1]
            if content == '' or content.strip() == '' \
                    or '$' in content:
                ambiguous = True
            else:
                valid_repls.append((before, after + 1, f"${content}$"))
        elif has_before or has_after:
            # $ on exactly one side of a code span is an incomplete
            # inline-math attempt: reject rather than guess.
            if has_before:
                handled_before.add(before)
            ambiguous = True

    # Any remaining single-$ + backtick outside code spans that did not
    # open a valid span+$-pair is ambiguous (missing close/backtick).
    for i in range(len(line) - 1):
        if line[i] == '$' and line[i + 1] == '`' and not inside(i):
            if not _is_single_dollar(line, i):
                continue
            if i in handled_before:
                continue
            # If the backtick at i+1 starts a span we already handled
            # (valid or one-sided), skip; else it is a dangling opener.
            ambiguous = True

    if ambiguous:
        return line, True
    # apply rightmost-first to keep indices valid
    new_line = line
    for a, b, rep in sorted(valid_repls, reverse=True):
        new_line = new_line[:a] + rep + new_line[b:]
    return new_line, False


def convert_math_body(body_lines: list[str]):
    """Convert inline ``$`code`$`` -> ``$code$``; validate ``$$`` blocks.

    Returns (new_lines, errors). Errors are ``[PROJ-3]`` diagnostics;
    callers prepend the source path. Fenced lines untouched; ``$$``
    inside inline code spans untouched.
    """
    errors: list[str] = []
    converted: list[str] = []
    in_fence = False
    for line in body_lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            converted.append(line)
            continue
        if in_fence:
            converted.append(line)
            continue
        new_line, bad = _convert_inline_line(line)
        if bad:
            errors.append(
                "[PROJ-3] ambiguous inline math (a '$`' sequence does not "
                "form exactly '$`code`$' with non-empty code containing no "
                "backtick or '$'; fix the delimiters explicitly)")
            converted.append(line)
            continue
        converted.append(new_line)

    # Display $$ validation (outside fences + outside inline code spans).
    in_fence = False
    total = 0
    for line in converted:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        spans = [(m.start(), m.end())
                 for m in _CODE_SPAN_RE.finditer(line)]
        idx = 0
        while True:
            j = line.find('$$', idx)
            if j == -1:
                break
            if any(s <= j < e for s, e in spans):
                idx = j + 2
                continue
            total += 1
            idx = j + 2
    if total % 2 != 0:
        errors.append(
            "[PROJ-3] ambiguous display math (odd number of '$$' delimiters "
            "outside fenced code and code spans; close or remove the "
            "unpaired '$$')")
    return converted, errors


# -- PROJ-5 ordering ------------------------------------------------------

def source_order_key(repo_rel: str):
    """Sort key: numbered (numeric incl 21a) first, unnumbered alpha."""
    name = repo_rel.rpartition('/')[2]
    stem = name[:-3] if name.lower().endswith('.md') else name
    m = ORDERED_PATTERN.match(stem)
    if m:
        num = int(m.group(1))
        letter = m.group(2) or ''
        sub = int(m.group(3)) if m.group(3) is not None else -1
        rest = (m.group(4) or '').casefold()
        return (0, num, letter, sub, rest, repo_rel.casefold())
    return (1, repo_rel.casefold())


def compute_orders(repo_rels: list[str],
                   final_slugs: dict[str, str]) -> dict[str, int]:
    """Per slug-parent rank (1-based) ordered by source numbering."""
    by_parent: dict[str, list[str]] = {}
    for rel in repo_rels:
        slug = final_slugs.get(rel)
        if slug is None:
            continue
        parent = slug.rpartition('/')[0]
        by_parent.setdefault(parent, []).append(rel)
    orders: dict[str, int] = {}
    for _parent, members in by_parent.items():
        members.sort(key=source_order_key)
        for i, rel in enumerate(members, start=1):
            orders[rel] = i
    return orders


def parse_title_value(fm_lines: list[str]) -> str | None:
    for line in fm_lines[1:-1] if len(fm_lines) >= 2 else []:
        m = _TITLE_RE.match(line)
        if m:
            raw = m.group(1).strip()
            if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"')
                                  or (raw[0] == "'" and raw[-1] == "'")):
                raw = raw[1:-1].strip()
            return raw or None
    return None


def inject_order(fm_lines: list[str], order: int) -> list[str]:
    out = list(fm_lines)
    if len(out) < 2 or out[0].strip() != '---' or out[-1].strip() != '---':
        return out
    side_idx = -1
    for i in range(1, len(out) - 1):
        if _SIDEBAR_RE.match(out[i]):
            side_idx = i
            break
    if side_idx == -1:
        out.insert(len(out) - 1, 'sidebar:')
        out.insert(len(out) - 1, f'  order: {order}')
        return out
    # find existing order under sidebar block (indented lines after it)
    for j in range(side_idx + 1, len(out) - 1):
        line = out[j]
        if line.strip() == '' or _SIDEBAR_RE.match(line):
            continue
        if _ORDER_RE.match(line) and (line.startswith(' ')
                                      or line.startswith('\t')):
            out[j] = f'  order: {order}'
            return out
        if not line.startswith(' ') and not line.startswith('\t'):
            break
    out.insert(side_idx + 1, f'  order: {order}')
    return out


# -- orchestration ---------------------------------------------------------

def _out_inside_or_equal(repo: Path, out: Path) -> str | None:
    try:
        out.relative_to(repo)
        return 'equal' if out == repo else 'inside'
    except ValueError:
        pass
    try:
        repo.relative_to(out)
        return 'parent'
    except ValueError:
        return None


def validate_out_location(repo: Path, out: Path) -> str | None:
    """Return error string if out is not safely outside source, else None."""
    verdict = _out_inside_or_equal(repo.resolve(), out.resolve()
                                   if out.is_absolute()
                                   else (Path.cwd() / out).resolve())
    if verdict is not None:
        return (f"output directory {out} must be outside the course "
                f"repository {repo} (never write into sources)")
    return None


def collect_projection_data(course_repo: Path, config, identity,
                            inventory, final_slugs, link_index):
    """In-memory projection. Returns (files, copies, nav, errors).

    files: dict output_rel-posix -> text (markdown under
    ``src/content/docs/`` plus static Mermaid SVGs under ``mermaid/``,
    DIAG-1). copies: sorted list of (abs source Path, copy_rel). nav:
    sorted list of dicts. errors: sorted diagnostics with source path +
    rule + fix (including DIAG-2 for unrenderable diagrams).
    """
    from .links import rewrite_document
    from .mermaid import process_mermaid_blocks

    repo = Path(course_repo).resolve()
    orders = compute_orders([le.repo_rel for le in inventory.lessons],
                            final_slugs)
    by_rel = {le.repo_rel: le for le in inventory.lessons}
    files: dict[str, str] = {}
    copies: dict[str, Path] = {}
    copy_rel_by_src: dict[str, str] = {}
    mermaid_files: dict[str, str] = {}
    nav: list[dict] = []
    errors: list[str] = []

    for rel in sorted(final_slugs):
        lesson = by_rel.get(rel)
        if lesson is None:
            continue
        slug = final_slugs[rel]
        try:
            original = lesson.source_path.read_text(encoding='utf-8')
        except OSError as exc:
            errors.append(f"{rel}: [PROJ-6] cannot read lesson ({exc}); "
                          f"{_FIX_PROJECTION}")
            continue
        has_fm, _end, fm_lines, rest_lines, _all = split_frontmatter(original)
        stripped = strip_backlink_lines(rest_lines)
        if has_fm:
            fm_text = '\n'.join(fm_lines) + '\n'
            if stripped:
                combined = fm_text + '\n'.join(stripped).rstrip('\n') + '\n'
            else:
                combined = fm_text
        else:
            combined = ('\n'.join(stripped) + '\n') if stripped else ''
        rewritten, file_copies, link_errors = rewrite_document(
            lesson.source_path, combined, link_index)
        for e in link_errors:
            errors.append(e)
        if link_errors:
            continue
        has_fm2, _e2, fm2, rest2, _a2 = split_frontmatter(rewritten)
        shifted = shift_headings_body(rest2)
        converted, math_errors = convert_math_body(shifted)
        for e in math_errors:
            errors.append(f"{rel}: {e}; {_FIX_PROJECTION}")
        if math_errors:
            continue
        # DIAG-1: Mermaid fences -> deterministic static SVGs (after math so
        # SVG content is final; fences were skipped by link/math stages).
        converted2, svg_files, mermaid_errors = process_mermaid_blocks(
            converted, source_path=rel, slug=slug)
        for e in mermaid_errors:
            errors.append(e)
        if mermaid_errors:
            continue
        for svg_rel, svg_content in svg_files:
            # Slugs are unique; diagram indices unique per file, so rels
            # are unique. Defensive: on collision keep first (deterministic).
            if svg_rel not in mermaid_files:
                mermaid_files[svg_rel] = svg_content
        converted = converted2
        order = orders.get(rel, 1)
        if has_fm2:
            fm3 = inject_order(fm2, order)
            title = parse_title_value(fm3)
        else:
            title = None
            fm3 = ['---', f'slug: {slug}', 'sidebar:',
                   f'  order: {order}', '---']
        if converted:
            projected = ('\n'.join(fm3) + '\n'
                         + '\n'.join(converted).rstrip('\n') + '\n')
        else:
            projected = '\n'.join(fm3) + '\n'
        out_rel = 'src/content/docs/' + slug.strip('/') + '.md'
        files[out_rel] = projected
        for src_abs, copy_rel in file_copies:
            key = str(src_abs)
            if key not in copies:
                copies[key] = src_abs
                copy_rel_by_src[key] = copy_rel
        nav.append({
            'slug': slug,
            'title': title if title is not None else '',
            'lang': lesson.language,
            'source': rel,
            'order': order,
            'output': out_rel,
        })

    nav.sort(key=lambda e: e['slug'])
    copy_list = sorted(
        ((copies[k], copy_rel_by_src.get(k, Path(k).name)) for k in copies),
        key=lambda t: t[1])
    # Merge static Mermaid SVGs (DIAG-1, DIAG-4 deterministic) into files so
    # both projection and site writers emit them without signature changes.
    for svg_rel in sorted(mermaid_files):
        files[svg_rel] = mermaid_files[svg_rel]
    # deterministic file order
    files = dict(sorted(files.items()))
    return files, copy_list, nav, sorted(errors)


def _astro_config_text(config, identity) -> str:
    titles = ', '.join(f'{k}={v!r}'
                       for k, v in sorted(config.site_title.items()))
    lines = [
        '// Placeholder renderer config (issue #10).',
        '// Full Astro Starlight config (SITE-1..SITE-14) lands in #11.',
        f'// Site titles: {titles}',
        f'// Pages: {identity.pages_url}',
        f'// Base: /{identity.repo}/',
        '// No timestamps emitted (PROJ-6).',
        'export default {};',
        '',
    ]
    return '\n'.join(lines)


def _mermaid_readme_text() -> str:
    return (
        '# Static Mermaid SVGs (issue #12, DIAG-1..DIAG-4)\n\n'
        'Each ````mermaid`` fence in the projected lessons is rendered to a\n'
        'deterministic static SVG during the build using pinned Playwright +\n'
        'Chromium (renderer/package.json + render-mermaid.mjs; offline\n'
        'fallback is deterministic and normalized for repeatable tests).\n'
        'Projected Markdown embeds the same SVG inline (no Mermaid client\n'
        'JavaScript is shipped, DIAG-3) and this directory holds one\n'
        '``<flat-slug>-<idx>.svg`` per diagram for inspection/smoke tests.\n'
        'All files here are disposable build artifacts, never committed.\n'
        'No timestamps emitted (PROJ-6, DIAG-4).\n')


def write_projection(out_dir: Path, files: dict[str, str],
                     copy_list, nav: list[dict],
                     config, identity) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel in sorted(files):
        dest = out_dir / Path(*rel.split('/'))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(files[rel], encoding='utf-8')
    for src_abs, copy_rel in sorted(copy_list, key=lambda t: t[1]):
        # Images are served from public/ below the Pages base (SITE-2);
        # markdown references /<repo>/assets/... (see links.resolve_link).
        # Copy to public/<copy_rel> so Astro copies public/ -> dist/.
        dest = out_dir / "public" / Path(*copy_rel.split('/'))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(Path(src_abs).read_bytes())
    (out_dir / 'nav.json').write_text(
        json.dumps(nav, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')
    (out_dir / 'astro.config.mjs').write_text(
        _astro_config_text(config, identity), encoding='utf-8')
    mermaid_dir = out_dir / 'mermaid'
    mermaid_dir.mkdir(parents=True, exist_ok=True)
    (mermaid_dir / 'README.md').write_text(
        _mermaid_readme_text(), encoding='utf-8')
    dist_dir = out_dir / 'dist'
    dist_dir.mkdir(parents=True, exist_ok=True)
    keep = dist_dir / '.gitkeep'
    if not keep.exists():
        keep.write_bytes(b'')


def _clean_out_dir(out_dir: Path) -> None:
    if not out_dir.exists():
        return
    for child in sorted(out_dir.iterdir(), key=lambda p: p.name):
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                pass


def run_projection_build(course_repo: Path, args) -> int:
    """Handler(course_repo, args) -> int for publish.py registry."""
    repo = Path(course_repo).resolve()
    raw_out = getattr(args, 'out', None)
    check_mode = bool(getattr(args, 'check', False))

    if raw_out is not None:
        cand = Path(raw_out)
        out_path = cand if cand.is_absolute() else (Path.cwd() / cand)
        out_resolved = out_path.resolve()
    else:
        out_resolved = None

    if out_resolved is not None:
        problem = validate_out_location(repo, out_resolved)
        if problem is not None:
            print(f"error: {problem}", file=sys.stderr)
            return 2

    try:
        from .config import load_config
        from .identity import infer_identity
        from .inventory import build_inventory
        from .links import build_link_index
        from .metadata import collect_metadata_state
    except ImportError as exc:  # pragma: no cover - same package
        print(f"error: publishing package incomplete: {exc}",
              file=sys.stderr)
        return 2

    try:
        config = load_config(repo)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        identity = infer_identity(repo)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        inventory = build_inventory(repo, config)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        from .metadata import validate_all_metadata
        meta_errors = validate_all_metadata(
            repo, config, inventory, identity.pages_url)
    except Exception as exc:
        print(f"error: publishing check failed for {repo}: {exc}",
              file=sys.stderr)
        return 1
    if meta_errors:
        for msg in meta_errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    try:
        final, collect_errors, _missing = collect_metadata_state(
            repo, config, inventory, identity.pages_url)
        if collect_errors:
            for msg in sorted(collect_errors):
                print(f"error: {msg}", file=sys.stderr)
            return 1
        link_index = build_link_index(repo, config, identity,
                                      inventory, final)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        from .links import validate_all_links
        link_errors = validate_all_links(repo, config, identity,
                                         inventory, final)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if link_errors:
        for msg in link_errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    files, copy_list, nav, proj_errors = collect_projection_data(
        repo, config, identity, inventory, final, link_index)
    if proj_errors:
        for msg in proj_errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    # PROJ-6: two in-memory builds must be byte-identical.
    files2, copy_list2, nav2, _e2 = collect_projection_data(
        repo, config, identity, inventory, final, link_index)
    if files2 != files or nav2 != nav or [
            (str(a), r) for a, r in copy_list2] != [
            (str(a), r) for a, r in copy_list]:
        print("error: projection is not deterministic "
              "([PROJ-6] two builds differed); "
              f"{_FIX_PROJECTION}", file=sys.stderr)
        return 1

    if check_mode:
        n = sum(1 for k in files if k.startswith("src/content/docs/"))
        print(f"projection check: OK ({n} lesson(s); "
              f"{len(copy_list)} image(s); deterministic; "
              f"source unchanged; no writes)")
        return 0

    if out_resolved is None:
        out_resolved = Path(
            tempfile.mkdtemp(prefix='course-projection-')).resolve()
        problem = validate_out_location(repo, out_resolved)
        if problem is not None:  # pragma: no cover - /tmp sibling
            print(f"error: {problem}", file=sys.stderr)
            return 2
    else:
        out_resolved.mkdir(parents=True, exist_ok=True)
        _clean_out_dir(out_resolved)

    try:
        write_projection(out_resolved, files, copy_list, nav,
                         config, identity)
    except OSError as exc:
        print(f"error: cannot write projection to {out_resolved}: {exc}; "
              f"{_FIX_PROJECTION}", file=sys.stderr)
        return 1

    print(f"projection build: OK "
          f"({sum(1 for k in files if k.startswith('src/content/docs/'))} "
          f"lesson(s), "
          f"{len(copy_list)} image(s)) in {out_resolved}")
    return 0
