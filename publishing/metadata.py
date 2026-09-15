"""Stable lesson metadata: slug generation + source-backlink handling (META-1..META-8).

Generates missing slugs from language + route_sections + source path,
validates existing slugs (never silently regenerates), inserts/refreshes
exactly one marked source-backlink block immediately after frontmatter,
and rejects duplicates/collisions safely (two-phase: validate all, then write).

Stdlib-only. Read-only helpers are reusable by `publishing check` (META-7);
`run_metadata_generate` is the `metadata generate` handler for publish.py.
Ordinary maintenance (maintain.py) never imports this module (META-8).
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

BACKLINK_START = "<!-- course-site-backlink:start -->"
BACKLINK_END = "<!-- course-site-backlink:end -->"
EN_LABEL = "This lesson on the website"
RU_LABEL = "Этот урок на сайте"

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_ORDERED_RE = re.compile(r"^(\d+)([a-z])?(?:_(\d+))?_(.+)$")
_COMPONENT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_LINE_RE = re.compile(r"^\s*slug\s*:\s*(.*)\s*$")
_BACKLINK_LINK_RE = re.compile(r"^\[(.*)\]\((.*)\)\s*$")

_FIX_GENERATE = "operation: metadata generate"
_FIX_EXPLICIT = "fix: correct the slug explicitly in the source file"


class MetadataError(Exception):
    def __init__(self, message: str, *, rule: str = "META-7",
                 path: str | Path | None = None,
                 hint: str = _FIX_GENERATE):
        self.rule = rule
        loc = str(path) if path is not None else "lesson metadata"
        super().__init__(f"{loc}: [{rule}] {message}; {hint}")


def _fold_key(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def slugify_component(raw: str) -> str:
    """Lowercase kebab-case with ordering-prefix stripping (META-2).

    Strips a leading ordering prefix understood by course maintenance
    (01_, 21a_, 01_02_, ...) then converts underscores/whitespace to
    hyphens, lowercases, replaces any other non-kebab char with a hyphen,
    collapses repeats and strips edge hyphens. `stub` naturally remains.
    Raises MetadataError if nothing remains.
    """
    m = _ORDERED_RE.match(raw)
    rest = m.group(4) if m else raw
    # underscores + any whitespace run -> hyphen
    s = re.sub(r"[_\s]+", "-", rest)
    s = s.lower()
    # any char outside a-z0-9- -> hyphen (keeps kebab strict)
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"\-{2,}", "-", s)
    s = s.strip("-")
    if not s:
        raise MetadataError(
            f"cannot derive slug component from {raw!r} (empty after "
            f"normalization)",
            rule="META-2", hint=_FIX_EXPLICIT)
    return s


def _is_valid_component(comp: str) -> bool:
    return bool(_COMPONENT_RE.match(comp))


def is_valid_slug(slug: str, language: str) -> bool:
    """A valid slug is non-empty kebab components starting with language."""
    if not isinstance(slug, str):
        return False
    s = slug.strip()
    if not s:
        return False
    if s.startswith("/") or s.endswith("/") or "//" in s:
        return False
    parts = s.split("/")
    if not parts or parts[0] != language:
        return False
    for p in parts:
        if not _is_valid_component(p):
            return False
    return True


def _label_for(lang: str) -> str:
    return RU_LABEL if lang == "ru" else EN_LABEL


def expected_backlink_url(pages_url: str, slug: str) -> str:
    return f"{pages_url.rstrip('/')}/{slug.strip('/')}/"


def expected_backlink_block(lang: str, slug: str, pages_url: str) -> str:
    label = _label_for(lang)
    url = expected_backlink_url(pages_url, slug)
    return f"{BACKLINK_START}\n[{label}]({url})\n{BACKLINK_END}\n"


# -- frontmatter ----------------------------------------------------------

def split_frontmatter(text: str):
    """Return (has_fm, fm_end_idx, fm_lines, rest_lines, all_lines).

    Lines are split without keeping ends; rewriting always uses \\n.
    Frontmatter is a leading --- line through the next --- line.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False, -1, [], lines, lines
    end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end == -1:
        return False, -1, [], lines, lines
    return True, end, lines[0:end + 1], lines[end + 1:], lines


def parse_slug_value(text: str):
    """Return (has_fm, slug_or_None, slug_count, fm_end_idx)."""
    has_fm, end, fm_lines, _rest, _all = split_frontmatter(text)
    if not has_fm:
        return False, None, 0, -1
    count = 0
    value = None
    for line in fm_lines[1:-1]:
        m = _SLUG_LINE_RE.match(line)
        if m:
            count += 1
            raw = m.group(1).strip()
            # strip surrounding quotes once
            if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"')
                                  or (raw[0] == "'" and raw[-1] == "'")):
                raw = raw[1:-1].strip()
            # strip inline comment? minimal: cut at unquoted # with space
            # before it (best-effort, keeps simple values intact).
            value = raw or None
    # empty `slug:` counts as present-but-empty -> treat as invalid later;
    # here return None but count>=1 so callers know it was present.
    if count > 0 and (value is None or value == ""):
        # keep None but count signals presence
        pass
    return True, value, count, end


def _insert_slug_into_frontmatter(fm_lines: list[str], slug: str) -> list[str]:
    """Return new fm_lines with `slug: X` added (no existing slug)."""
    out = list(fm_lines)
    # insert after title: line if present, else before closing ---
    title_idx = -1
    for i in range(1, len(out) - 1):
        if re.match(r"^\s*title\s*:", out[i]):
            title_idx = i
            break
    new_line = f"slug: {slug}"
    if title_idx != -1:
        out.insert(title_idx + 1, new_line)
    else:
        out.insert(len(out) - 1, new_line)
    return out


# -- index election + slug derivation -------------------------------------

def compute_index_election(repo_rels: list[str]) -> set[str]:
    """Elect one index lesson per directory (META-2).

    repo_rels are selected lesson repo-relative posix paths. In each
    directory containing selected lessons named index.md/README.md/doc.md
    (case-insensitive), elect the first existing in precedence
    index > README > doc. Returns the set of elected repo_rel strings.
    """
    by_dir: dict[str, dict[str, str]] = {}
    for rel in repo_rels:
        parent = rel.rpartition("/")[0]  # "" for top-level files
        base = rel.rpartition("/")[2].lower()
        by_dir.setdefault(parent, {})[base] = rel
    elected: set[str] = set()
    for _parent, names in by_dir.items():
        for cand in ("index.md", "readme.md", "doc.md"):
            if cand in names:
                elected.add(names[cand])
                break
    return elected


def _longest_route_match(after_root: str, route_sections) -> tuple[str, str] | None:
    best = None
    best_len = -1
    for rs in route_sections:
        src = rs.source
        if after_root == src or after_root.startswith(src + "/"):
            if len(src) > best_len:
                best = (src, rs.destination)
                best_len = len(src)
    return best


def expected_slug_for(after_root: str, language: str,
                      route_sections, is_index: bool) -> str:
    """Derive the canonical slug for a lesson without frontmatter (META-1..3)."""
    m = _longest_route_match(after_root, route_sections)
    if m is not None:
        src, dst = m
        mapped = dst + after_root[len(src):]
    else:
        mapped = after_root
    parts = [p for p in mapped.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise MetadataError(f"cannot derive slug from empty path {after_root!r}",
                            rule="META-1")
    *dir_parts, file_part = parts
    # strip extension (case-insensitive .md) for the file component
    if "." in file_part:
        stem, _, ext = file_part.rpartition(".")
        file_stem = stem if ext.lower() == "md" and stem else file_part
    else:
        file_stem = file_part
    slug_dirs: list[str] = []
    for d in dir_parts:
        if d.casefold() == "05a_programming_fundamentals":
            slug_dirs.append("advanced-programming-fundamentals")
        else:
            slug_dirs.append(slugify_component(d))
    if is_index:
        comps = slug_dirs
    else:
        if after_root == "labs/cpp/test1.md":
            file_slug = "assessment-1"
        else:
            file_slug = slugify_component(file_stem)
        comps = slug_dirs + [file_slug]
    if not comps:
        return language
    return language + "/" + "/".join(comps)


# -- backlink scanning (fence-aware) --------------------------------------

def _marker_indices(lines: list[str]) -> tuple[list[int], list[int]]:
    starts: list[int] = []
    ends: list[int] = []
    in_fence = False
    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        s = line.strip()
        if s == BACKLINK_START:
            starts.append(i)
        elif s == BACKLINK_END:
            ends.append(i)
    return starts, ends


def find_backlink_blocks(lines: list[str]):
    """Return list of (start_idx, end_idx) for well-paired blocks.

    Pairing is greedy in document order; orphans are returned separately
    via _marker_indices. Only lines outside fenced code count.
    """
    starts, ends = _marker_indices(lines)
    blocks: list[tuple[int, int]] = []
    ei = 0
    for s in starts:
        while ei < len(ends) and ends[ei] < s:
            ei += 1
        if ei < len(ends):
            blocks.append((s, ends[ei]))
            ei += 1
    return blocks


def _remove_backlink_blocks(body_lines: list[str]) -> list[str]:
    """Remove all marker-delimited backlink blocks from body lines.

    Fence-aware: markers inside fenced code are preserved. For each
    start marker with a following end marker, remove start..end inclusive.
    Orphan markers (and a following backlink-like link line) are removed
    alone so stale fragments never survive a refresh.
    """
    # compute fence state per line to preserve fenced markers
    in_fence = False
    fence_state: list[bool] = []
    for line in body_lines:
        if _FENCE_RE.match(line):
            fence_state.append(True)  # fence delimiter itself: never a marker
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
    used_ends: set[int] = set()
    for s in starts:
        nxt = None
        for e in ends:
            if e > s and e not in used_ends:
                nxt = e
                break
        if nxt is not None:
            used_ends.add(nxt)
            for i in range(s, nxt + 1):
                remove.add(i)
        else:
            remove.add(s)
            # also drop an immediately following backlink-like link line
            if s + 1 < len(body_lines) and not fence_state[s + 1]:
                if _BACKLINK_LINK_RE.match(body_lines[s + 1].strip()):
                    remove.add(s + 1)
    for e in ends:
        if e not in used_ends:
            remove.add(e)
    return [l for i, l in enumerate(body_lines) if i not in remove]


def build_new_text(original: str, final_slug: str, lang: str,
                   pages_url: str, slug_missing: bool) -> str:
    """Return the fully regenerated file text (frontmatter + one backlink)."""
    has_fm, fm_end, fm_lines, rest_lines, _all = split_frontmatter(original)
    if not has_fm:
        fm_lines = ["---", f"slug: {final_slug}", "---"]
        rest_lines = original.splitlines()
        # original had no frontmatter: keep body as-is (may be empty)
    elif slug_missing:
        fm_lines = _insert_slug_into_frontmatter(fm_lines, final_slug)
    # else: keep fm_lines untouched (never modify existing valid slug)
    clean_body = _remove_backlink_blocks(rest_lines)
    block = expected_backlink_block(lang, final_slug, pages_url)
    fm_text = "\n".join(fm_lines) + "\n"
    body_text = "\n".join(clean_body)
    # block already ends with \n; preserve author's body verbatim (including
    # any leading blank line, which then appears after the block).
    if body_text == "":
        return fm_text + block
    # ensure body starts right after block; if body has no leading newline
    # structure it is already line-oriented via join, so simple concat works:
    # fm ends with \n, block ends with \n, body has no trailing newline yet.
    if original.endswith("\n") or True:
        # normalize to single trailing newline for idempotency
        return fm_text + block + body_text.rstrip("\n") + "\n"
    return fm_text + block + body_text


def validate_backlink(lines: list[str], lang: str, slug: str,
                      pages_url: str):
    """Validate the single required backlink block. Returns error str or None.

    Checks (META-6/7): exactly one block, immediately after frontmatter,
    well-formed start/link/end, correct localized label, current URL.
    `lines` is the full file splitlines (without ends).
    """
    has_fm, fm_end, _fm, _rest, _all = split_frontmatter("\n".join(lines))
    if not has_fm:
        return "missing backlink block (no frontmatter present)"
    starts, ends = _marker_indices(lines)
    blocks = find_backlink_blocks(lines)
    if len(blocks) == 0:
        if starts or ends:
            return "malformed backlink block (unpaired markers)"
        return "missing backlink block"
    if len(blocks) > 1 or len(starts) > 1 or len(ends) > 1:
        return "duplicate backlink blocks"
    s, e = blocks[0]
    if s != fm_end + 1:
        return "backlink block is not immediately after frontmatter"
    if e != s + 2:
        return "malformed backlink block (expected start/link/end lines)"
    mid = lines[s + 1].strip()
    m = _BACKLINK_LINK_RE.match(mid)
    if not m:
        return "malformed backlink block (middle line is not a Markdown link)"
    label, url = m.group(1), m.group(2)
    if label != _label_for(lang):
        return (f"malformed backlink label {label!r} "
                f"(expected {_label_for(lang)!r})")
    want = expected_backlink_url(pages_url, slug)
    if url != want:
        return f"stale backlink URL {url!r} (expected {want!r})"
    return None


# -- inventory helpers -----------------------------------------------------

def _regen_hint(course_repo: Path) -> str:
    try:
        maint = Path(__file__).resolve().parent.parent
        cmd = (f"python3 {maint}/publish.py metadata generate "
               f"--course-repo {Path(course_repo).resolve()}")
    except Exception:
        cmd = ("python3 <course_maintenance>/publish.py metadata generate "
               "--course-repo <course_repository>")
    return (f"fix: run metadata generation: `{cmd}`; "
            f"{_FIX_GENERATE}")


def collect_metadata_state(course_repo: Path, config, inventory,
                           pages_url: str):
    """Two-phase collection: final slugs + per-file errors (no writes).

    Returns (final_slugs: dict repo_rel->slug, errors: list[str],
             missing: set repo_rel needing slug insertion).
    Existing valid slugs are never altered; invalid/conflicting ones are
    errors requiring explicit correction (META-5).
    """
    rels = [le.repo_rel for le in inventory.lessons]
    elected = compute_index_election(rels)
    by_rel = {le.repo_rel: le for le in inventory.lessons}
    # map language -> root for after_root computation
    lang_roots = {l.code: l.root for l in config.languages}

    final: dict[str, str] = {}
    missing: set[str] = set()
    errors: list[str] = []
    # phase 1a: read + validate existing / derive missing
    for rel in sorted(rels):
        lesson = by_rel[rel]
        lang = lesson.language
        try:
            text = lesson.source_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(
                f"{rel}: [META-7] cannot read lesson ({exc}); "
                f"{_regen_hint(course_repo)}")
            continue
        has_fm, slug_val, slug_count, _end = parse_slug_value(text)
        if slug_count > 1:
            errors.append(
                f"{rel}: [META-7] duplicate slug lines in frontmatter; "
                f"fix: keep exactly one `slug:` line {_FIX_EXPLICIT}; "
                f"{_FIX_GENERATE}")
            continue
        if not has_fm or slug_count == 0 or slug_val is None or slug_val == "":
            # missing: derive
            root = lang_roots.get(lang, lang)
            after = rel[len(root) + 1:] if rel.startswith(root + "/") else rel
            try:
                gen = expected_slug_for(after, lang, config.route_sections,
                                        rel in elected)
            except MetadataError as exc:
                errors.append(f"{rel}: [{exc.rule}] {exc}; "
                              f"{_regen_hint(course_repo)}")
                continue
            final[rel] = gen
            missing.add(rel)
        else:
            if not is_valid_slug(slug_val, lang):
                errors.append(
                    f"{rel}: [META-5] invalid slug {slug_val!r} "
                    f"(expected lowercase kebab components starting with "
                    f"{lang!r}); {_FIX_EXPLICIT}; {_FIX_GENERATE}")
                continue
            final[rel] = slug_val
    # phase 1b: duplicate slugs after NFC + casefold (META-4). One error
    # per extra file is enough to abort generation / fail the check.
    seen: dict[str, str] = {}
    first_rel_for_key: dict[str, str] = {}
    for rel in sorted(final):
        key = _fold_key(final[rel])
        if key not in seen:
            seen[key] = final[rel]
            first_rel_for_key[key] = rel
        else:
            other = first_rel_for_key[key]
            errors.append(
                f"{rel}: [META-4] duplicate slug {final[rel]!r} "
                f"(collides with {other!r} after Unicode normalization "
                f"and case folding); {_FIX_EXPLICIT}; {_FIX_GENERATE}")
    return final, errors, missing


def validate_all_metadata(course_repo: Path, config, inventory,
                          pages_url: str) -> list[str]:
    """Full read-only validation for `publishing check` (META-7).

    Covers missing/invalid/duplicate slugs plus missing/duplicate/
    malformed/stale backlinks. Every message carries the source path, the
    META rule, and the exact regeneration command when generation can fix it.
    """
    final, errors, missing = collect_metadata_state(
        course_repo, config, inventory, pages_url)
    errs = list(errors)
    hint = _regen_hint(course_repo)
    by_rel = {le.repo_rel: le for le in inventory.lessons}
    # Backlinks are checked for every lesson with a resolved slug (valid
    # existing or derivable). Lessons with slug errors are absent from
    # `final` and already reported; skip them here to avoid noise.
    for rel in sorted(final):
        lesson = by_rel[rel]
        try:
            text = lesson.source_path.read_text(encoding="utf-8")
        except OSError as exc:
            errs.append(f"{rel}: [META-7] cannot read lesson ({exc}); {hint}")
            continue
        prob = validate_backlink(text.splitlines(), lesson.language,
                                 final[rel], pages_url)
        if prob is not None:
            errs.append(f"{rel}: [META-7] {prob}; {hint}")
    # `collect` derives missing slugs without erroring; for the read-only
    # check a missing slug is itself a META-7 error requiring generation.
    # Report it even when a backlink error already exists for the same file
    # so contributors see both diagnostics with the same regen command.
    for rel in sorted(missing):
        errs.append(
            f"{rel}: [META-7] missing slug "
            f"(expected {final[rel]!r}); {hint}")
    return sorted(errs)


def run_metadata_generate(course_repo: Path, args) -> int:
    """Handler(course_repo, args) -> int for publish.py registry."""
    _ = args
    repo = Path(course_repo).resolve()
    try:
        from .config import load_config
        from .identity import infer_identity
        from .inventory import build_inventory
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

    final, errors, missing = collect_metadata_state(
        repo, config, inventory, identity.pages_url)
    if errors:
        for msg in sorted(errors):
            print(f"error: {msg}", file=sys.stderr)
        print(f"metadata generate: aborted without changes "
              f"({len(errors)} error(s)); fix the slugs explicitly; "
              f"{_FIX_GENERATE}", file=sys.stderr)
        return 1

    # phase 2: compute new texts (backlink refresh included), write only if all ok
    planned: list[tuple[Path, str]] = []
    by_rel = {le.repo_rel: le for le in inventory.lessons}
    for rel in sorted(final):
        lesson = by_rel[rel]
        try:
            original = lesson.source_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"error: {rel}: [META-7] cannot read lesson ({exc}); "
                  f"{_regen_hint(repo)}", file=sys.stderr)
            return 1
        slug_missing = rel in missing
        new_text = build_new_text(original, final[rel], lesson.language,
                                  identity.pages_url, slug_missing)
        if new_text != original:
            planned.append((lesson.source_path, new_text))

    for path, new_text in planned:
        try:
            path.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            print(f"error: {path}: [META-7] cannot write lesson ({exc})",
                  file=sys.stderr)
            return 1
    if planned:
        print(f"metadata generate: updated {len(planned)} lesson(s) "
              f"in {repo}")
    else:
        print(f"metadata generate: OK (no changes) in {repo}")
    return 0
