"""Route and link resolution (LINK-1..LINK-8).

Builds a deterministic index from normalized absolute source paths to
canonical lesson URLs for the course repo + configured peers, then
resolves relative links from their original source locations before any
projection move.

Rewriting rules (spec LINK-3..6):

- preserve query strings + fragments exactly;
- published Markdown -> canonical site URL (Pages base + slug + trailing
  slash, identical to ``metadata.expected_backlink_url``);
- excluded Markdown + ordinary files -> GitHub ``blob`` URLs, dirs ->
  ``tree`` URLs, always ``master`` (via identity default_branch);
- locally embedded images (``![...](...)`` plus ``<img src>``) are marked
  for copying into the projection; other artifacts remain GitHub links.

Validation (LINK-7..8):

- missing / escaping / ambiguous / unsupported targets raise LinkError
  instead of guessing;
- Markdown heading fragments are validated with the same GitHub-anchor
  rules as course maintenance (reuses ``maintenance.links.github_slug``).

Stdlib-only. Read-only: never writes source files. The image ``copy_rel``
mapping is deterministic (``assets/<owner>/<repo>/<repo-rel>``) so issue
#10 projection can copy without guessing.
"""

from __future__ import annotations

import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from maintenance.links import github_slug
from maintenance.patterns import EXTERNAL_PREFIXES, FENCE_RE
from maintenance.patterns import HEADING_RE, LINK_RE

_FIX_LINK = ("fix: correct the link in the source file; "
             "operation: publishing check")
_IMG_RE = re.compile(
    r'(<img\b[^>]*?\bsrc\s*=\s*["\'])([^"\']+)(["\'])',
    re.IGNORECASE)
_CODE_SPAN_RE = re.compile(r'`[^`]*`')
_WINDOWS_ABS_RE = re.compile(r'^[a-zA-Z]:[\\/]')
_SCHEME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*:')


class LinkError(Exception):
    def __init__(self, message: str, *, rule: str = "LINK-7",
                 path: str | Path | None = None,
                 hint: str = _FIX_LINK):
        self.rule = rule
        loc = str(path) if path is not None else "lesson link"
        super().__init__(f"{loc}: [{rule}] {message}; {hint}")


def _fold_key(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def _is_external(dest: str) -> bool:
    return dest.strip().lower().startswith(EXTERNAL_PREFIXES)


def _quote_rel(rel_posix: str) -> str:
    if rel_posix in ("", "."):
        return ""
    return "/".join(urllib.parse.quote(p, safe="") for p in rel_posix.split("/"))


@dataclass(frozen=True)
class LessonEntry:
    repo_root: Path
    repo_rel: str
    slug: str
    canonical_url: str


@dataclass
class LinkIndex:
    course_repo: Path
    lessons: dict[str, LessonEntry] = field(default_factory=dict)
    repos: list[tuple[Path, object]] = field(default_factory=list)

    def to_deterministic_dict(self) -> dict[str, str]:
        return {k: self.lessons[k].canonical_url
                for k in sorted(self.lessons)}

    def repo_for_path(self, abs_path: Path):
        resolved = abs_path.resolve() if not abs_path.is_absolute() \
            else abs_path
        # repos sorted longest-root-first for correct containment
        for root, ident in sorted(self.repos,
                                  key=lambda t: len(str(t[0])),
                                  reverse=True):
            try:
                resolved.relative_to(root)
                return root, ident
            except ValueError:
                continue
        return None


def _peer_root(course_repo: Path, peer_rel: str) -> Path:
    return (course_repo.joinpath(*peer_rel.split("/"))).resolve()


def build_link_index(course_repo: Path | str, config,
                     identity, inventory,
                     final_slugs: dict[str, str]) -> LinkIndex:
    """Build LINK-1 index (main + peers). Deterministic, read-only."""
    # Local imports avoid cycles when publishing.check imports this module.
    from .config import load_config
    from .identity import infer_identity
    from .inventory import build_inventory
    from .metadata import collect_metadata_state, expected_backlink_url

    repo = Path(course_repo).resolve()
    index = LinkIndex(course_repo=repo)
    index.repos.append((repo, identity))

    def _add_repo(repo_root: Path, repo_ident, repo_inv, repo_final):
        for lesson in sorted(repo_inv.lessons, key=lambda l: l.repo_rel):
            slug = repo_final.get(lesson.repo_rel)
            if slug is None:
                continue
            key = str(lesson.source_path.resolve())
            url = expected_backlink_url(repo_ident.pages_url, slug)
            try:
                rel = lesson.source_path.resolve().relative_to(
                    repo_root).as_posix()
            except ValueError:
                rel = lesson.repo_rel
            index.lessons[key] = LessonEntry(
                repo_root=repo_root, repo_rel=rel, slug=slug,
                canonical_url=url)

    _add_repo(repo, identity, inventory, final_slugs)

    for peer_rel in sorted(set(config.peer_repositories)):
        peer_root = _peer_root(repo, peer_rel)
        try:
            peer_config = load_config(peer_root)
        except Exception as exc:
            raise LinkError(
                f"cannot build lesson index for peer {peer_rel!r} "
                f"(resolved to {peer_root}): {exc}",
                rule="LINK-1", path=config.source_path) from exc
        try:
            peer_ident = infer_identity(peer_root)
        except Exception as exc:
            raise LinkError(
                f"cannot infer identity for peer {peer_rel!r} "
                f"(resolved to {peer_root}): {exc}",
                rule="LINK-1", path=peer_root) from exc
        try:
            peer_inv = build_inventory(peer_root, peer_config)
        except Exception as exc:
            raise LinkError(
                f"cannot inventory peer {peer_rel!r} "
                f"(resolved to {peer_root}): {exc}",
                rule="LINK-1", path=peer_root) from exc
        peer_final, peer_errors, _m = collect_metadata_state(
            peer_root, peer_config, peer_inv, peer_ident.pages_url)
        if peer_errors:
            raise LinkError(
                f"peer {peer_rel!r} has invalid metadata: "
                f"{sorted(peer_errors)[0]}",
                rule="LINK-1", path=peer_root)
        index.repos.append((peer_root, peer_ident))
        _add_repo(peer_root, peer_ident, peer_inv, peer_final)

    # Deterministic iteration order for byte-identical downstream use.
    index.lessons = dict(sorted(index.lessons.items()))
    index.repos.sort(key=lambda t: str(t[0]))
    return index


@dataclass(frozen=True)
class ResolvedLink:
    kind: str  # canonical | github-blob | github-tree | image |
               # external | anchor-only
    url: str
    copy_source: Path | None = None
    copy_rel: str | None = None


def _split_dest(raw: str) -> tuple[str, str, str, str]:
    """Split raw dest into (path, query_suffix, frag_suffix, frag_value).

    query_suffix includes leading '?' or is ''; frag_suffix includes
    leading '#' or is ''. frag_value is the decoded-agnostic raw fragment
    (still encoded) without '#'.
    """
    rest, hash_sep, frag = raw.partition("#")
    frag_suffix = (hash_sep + frag) if hash_sep else ""
    path, q_sep, query = rest.partition("?")
    query_suffix = (q_sep + query) if q_sep else ""
    return path, query_suffix, frag_suffix, frag if hash_sep else ""


def _heading_slugs(target_file: Path) -> set[str]:
    slugs: set[str] = set()
    try:
        text = target_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return slugs
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(line)
        if not m:
            continue
        slug = github_slug(m.group(2))
        if slug:
            slugs.add(slug)
    return slugs


def _ambiguous_variant(parent: Path, want_name: str) -> str | None:
    try:
        entries = list(parent.iterdir())
    except OSError:
        return None
    want = _fold_key(want_name)
    for e in entries:
        if e.name != want_name and _fold_key(e.name) == want:
            return e.name
    return None


def resolve_link(source_abs: Path | str, raw_dest: str, *,
                 is_image: bool, index: LinkIndex) -> ResolvedLink:
    """Resolve one link destination (LINK-2..8). Raises LinkError."""
    src = Path(source_abs).resolve()
    dest = raw_dest.strip()
    if dest.startswith("<") and dest.endswith(">") and len(dest) >= 2:
        dest = dest[1:-1].strip()
    if not dest:
        raise LinkError("empty link destination is unsupported "
                        "(use a relative path)", rule="LINK-7", path=src)
    if _is_external(dest):
        return ResolvedLink(kind="external", url=raw_dest.strip())

    # Scheme-like destinations that are not known-external are unsupported
    # (file:, tel:, javascript:, windows drive, ...). Fragment/query-only
    # never reach here as unsupported because they lack a scheme part.
    head_for_scheme = dest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if _SCHEME_RE.match(head_for_scheme) or _WINDOWS_ABS_RE.match(dest):
        raise LinkError(
            f"unsupported link destination {raw_dest!r} "
            f"(only relative local paths, '#fragments', '?queries', "
            f"and http(s)/mailto external URLs are supported)",
            rule="LINK-7", path=src)
    if dest.startswith("/"):
        raise LinkError(
            f"unsupported absolute link {raw_dest!r} "
            f"(use a path relative to the source file)",
            rule="LINK-7", path=src)

    path_part, query_suffix, frag_suffix, frag_raw = _split_dest(dest)
    suffix = query_suffix + frag_suffix

    if "\\" in path_part:
        raise LinkError(
            f"unsupported link {raw_dest!r} (use forward slashes, not "
            f"backslashes)",
            rule="LINK-7", path=src)

    # Anchor/query-only: target is the source document itself.
    if path_part == "":
        if frag_raw:
            decoded = urllib.parse.unquote(frag_raw)
            if src.suffix.lower() == ".md" and src.is_file():
                if decoded not in _heading_slugs(src):
                    raise LinkError(
                        f"anchor #{frag_raw!r} not found in "
                        f"{src.name} (no such heading)",
                        rule="LINK-8", path=src)
        return ResolvedLink(kind="anchor-only", url=suffix or raw_dest.strip())

    decoded_path = urllib.parse.unquote(path_part)
    if decoded_path == "":
        raise LinkError(f"unsupported link destination {raw_dest!r}",
                        rule="LINK-7", path=src)

    resolved = (src.parent / decoded_path).resolve()

    owned = index.repo_for_path(resolved)
    if owned is None:
        raise LinkError(
            f"link target {raw_dest!r} escapes the course repository "
            f"and all configured peer repositories "
            f"(resolved to {resolved})",
            rule="LINK-7", path=src)
    repo_root, repo_ident = owned
    try:
        repo_rel = resolved.relative_to(repo_root).as_posix()
        if repo_rel == ".":
            repo_rel = ""
    except ValueError:  # pragma: no cover - containment already checked
        raise LinkError(
            f"link target {raw_dest!r} escapes the repository "
            f"(resolved to {resolved})",
            rule="LINK-7", path=src)

    if ".git" in resolved.relative_to(repo_root).parts \
            if repo_rel else False:
        raise LinkError(
            f"unsupported link target {raw_dest!r} (must not point "
            f"inside .git)",
            rule="LINK-7", path=src)

    if not resolved.exists() and not resolved.is_symlink():
        # Ambiguous (case/Unicode-only mismatch) must not fall back.
        alt = _ambiguous_variant(resolved.parent, resolved.name)
        if alt is not None:
            raise LinkError(
                f"ambiguous link target {raw_dest!r} "
                f"(found {alt!r} differing only by case or Unicode "
                f"normalization; fix the link to match the on-disk name)",
                rule="LINK-7", path=src)
        raise LinkError(
            f"missing link target {raw_dest!r} "
            f"(resolved to {resolved.relative_to(repo_root).as_posix()!r} "
            f"in {repo_ident.owner}/{repo_ident.repo})",
            rule="LINK-7", path=src)

    branch = getattr(repo_ident, "default_branch", "master") or "master"

    if resolved.is_dir():
        if is_image:
            raise LinkError(
                f"unsupported image target {raw_dest!r} (is a directory)",
                rule="LINK-7", path=src)
        quoted = _quote_rel(repo_rel)
        base = f"{repo_ident.github_url}/tree/{branch}"
        url = f"{base}/{quoted}" if quoted else base
        return ResolvedLink(kind="github-tree", url=url + suffix)

    # File target from here on.
    if is_image:
        copy_rel_raw = f"assets/{repo_ident.owner}/{repo_ident.repo}/" \
            f"{repo_rel}" if repo_rel else \
            f"assets/{repo_ident.owner}/{repo_ident.repo}"
        quoted_asset = "/".join(
            urllib.parse.quote(p, safe="") for p in copy_rel_raw.split("/"))
        # Astro serves public/ below the Pages project base (SITE-2), so
        # image URLs are absolute with the owning repo's base prefix
        # (e.g. /R/assets/O/R/en/assets/pic.png). Relative assets/... would
        # resolve against the lesson's nested slug and fail the renderer
        # build (ImageNotFound). Copy destination is public/<copy_rel>
        # (see projection/site writers); URL is base + copy_rel.
        base = f"/{repo_ident.repo}/"
        return ResolvedLink(kind="image", url=base + quoted_asset + suffix,
                            copy_source=resolved,
                            copy_rel=copy_rel_raw)

    key = str(resolved.resolve())
    entry = index.lessons.get(key)
    if entry is not None:
        if frag_raw and resolved.suffix.lower() == ".md":
            decoded = urllib.parse.unquote(frag_raw)
            if decoded not in _heading_slugs(resolved):
                raise LinkError(
                    f"anchor #{frag_raw!r} not found in "
                    f"{repo_rel} (no such heading)",
                    rule="LINK-8", path=src)
        return ResolvedLink(kind="canonical",
                            url=entry.canonical_url + suffix)

    # Excluded Markdown or ordinary file -> blob URL.
    if frag_raw and resolved.suffix.lower() == ".md":
        decoded = urllib.parse.unquote(frag_raw)
        if decoded not in _heading_slugs(resolved):
            raise LinkError(
                f"anchor #{frag_raw!r} not found in {repo_rel} "
                f"(no such heading)",
                rule="LINK-8", path=src)
    quoted = _quote_rel(repo_rel)
    url = f"{repo_ident.github_url}/blob/{branch}/{quoted}"
    return ResolvedLink(kind="github-blob", url=url + suffix)


def _code_spans(line: str):
    return [(m.start(), m.end())
            for m in _CODE_SPAN_RE.finditer(line)]


def _inside(pos: int, spans) -> bool:
    return any(s <= pos < e for s, e in spans)


def _source_repo_rel(source_abs: Path, index: LinkIndex) -> str:
    try:
        return source_abs.resolve().relative_to(
            index.course_repo).as_posix()
    except ValueError:
        return str(source_abs.resolve())


def rewrite_document(source_abs: Path | str, text: str,
                     index: LinkIndex):
    """Rewrite one Markdown document's links (read-only helper).

    Returns (new_text, copies, errors) where copies is a sorted unique
    list of (absolute source Path, projection-relative posix rel) for
    embedded images, and errors are LINK-7/8 diagnostics with source
    path + rule + fix. External links are left unchanged. Code fences
    and inline code spans are skipped. Frontmatter is preserved as-is.
    """
    src = Path(source_abs).resolve()
    repo_rel = _source_repo_rel(src, index)

    # Preserve frontmatter verbatim; only rewrite the body.
    fm_end = -1
    lines_all = text.splitlines(keepends=True)
    body_start = 0
    if lines_all and lines_all[0].strip() == "---":
        for i in range(1, len(lines_all)):
            if lines_all[i].strip() == "---":
                fm_end = i
                body_start = i + 1
                break
    head_text = "".join(lines_all[:body_start])
    body_lines = lines_all[body_start:]

    copies: dict[str, Path] = {}
    copy_rel_by_src: dict[str, str] = {}
    errors: list[str] = []
    out_lines: list[str] = []
    in_fence = False

    for offset, line in enumerate(body_lines, start=body_start + 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        spans = _code_spans(line)

        def _repl_link(m):
            prefix, target, title, suffix_p = (
                m.group(1), m.group(2), m.group(3) or "", m.group(4))
            if _inside(m.start(2), spans):
                return m.group(0)
            if _is_external(target.strip()):
                return m.group(0)
            is_img = prefix.startswith("!")
            try:
                out = resolve_link(src, target, is_image=is_img,
                                   index=index)
            except LinkError as exc:
                errors.append(
                    f"{repo_rel}:{offset}: {exc}")
                return m.group(0)
            if out.kind == "external":
                return m.group(0)
            if out.kind == "anchor-only":
                return f"{prefix}{out.url}{title}{suffix_p}"
            if out.kind == "image" and out.copy_source is not None:
                key = str(out.copy_source)
                copies[key] = out.copy_source
                if out.copy_rel:
                    copy_rel_by_src[key] = out.copy_rel
            return f"{prefix}{out.url}{title}{suffix_p}"

        line = LINK_RE.sub(_repl_link, line)

        def _repl_img(m):
            pre, target, post = m.group(1), m.group(2), m.group(3)
            if _inside(m.start(2), spans):
                return m.group(0)
            if _is_external(target.strip()):
                return m.group(0)
            try:
                out = resolve_link(src, target, is_image=True, index=index)
            except LinkError as exc:
                errors.append(f"{repo_rel}:{offset}: {exc}")
                return m.group(0)
            if out.kind == "external":
                return m.group(0)
            if out.copy_source is not None:
                key = str(out.copy_source)
                copies[key] = out.copy_source
                if out.copy_rel:
                    copy_rel_by_src[key] = out.copy_rel
            return f"{pre}{out.url}{post}"

        line = _IMG_RE.sub(_repl_img, line)
        out_lines.append(line)

    new_text = head_text + "".join(out_lines)
    copy_list = sorted(
        ((copies[k], copy_rel_by_src.get(k, Path(k).name))
         for k in copies),
        key=lambda t: t[1])
    return new_text, copy_list, errors


def validate_all_links(course_repo: Path, config, identity,
                       inventory, final_slugs) -> list[str]:
    """Read-only LINK validation for `publishing check` (LINK-7/8)."""
    try:
        index = build_link_index(course_repo, config, identity,
                                 inventory, final_slugs)
    except LinkError as exc:
        return [str(exc)]
    errs: list[str] = []
    for lesson in sorted(inventory.lessons, key=lambda l: l.repo_rel):
        try:
            text = lesson.source_path.read_text(encoding="utf-8")
        except OSError as exc:
            errs.append(
                f"{lesson.repo_rel}: [LINK-7] cannot read lesson ({exc}); "
                f"{_FIX_LINK}")
            continue
        _new, _copies, link_errors = rewrite_document(
            lesson.source_path, text, index)
        errs.extend(link_errors)
    return sorted(errs)
