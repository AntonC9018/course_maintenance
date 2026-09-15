"""Static Mermaid rendering (DIAG-1..DIAG-4, issue #12).

Stdlib-only Python. Converts every `````mermaid`` fence into a deterministic
static SVG during projection/site builds. No Mermaid client JavaScript is
ever emitted (DIAG-3) and no SVGs are committed to the course repo (all
outputs live below the disposable ``--out`` directory).

Pipeline:

- :func:`extract_mermaid_blocks` finds fences fence-aware (ignores markers
  inside other fences).
- :func:`validate_diagram` rejects empty/unknown/ambiguous diagrams with
  source path + Mermaid diagnostic (DIAG-2) instead of guessing.
- :func:`render_diagram` tries the pinned Playwright/Chromium toolchain via
  ``renderer/render-mermaid.mjs`` when available, otherwise falls back to a
  deterministic placeholder SVG (mockable in unit tests for offline use).
- :func:`normalize_svg` strips nondeterministic identifiers so repeat builds
  are byte-identical (DIAG-4).
- :func:`process_mermaid_blocks` replaces fences with inline static SVGs and
  collects ``mermaid/<flat-slug>-<idx>.svg`` files for the disposable output.
- :func:`check_no_mermaid_client_js` inspects built output for forbidden
  client code.

Real diagrams in the initial corpus (both ``flowchart LR`` examples from
``en/labs/algoritms/04_graphs.md`` and its Russian counterpart) render as
static SVGs; invalid diagrams fail the build with path + diagnostic.
"""

from __future__ import annotations

import hashlib
import html
import re
import subprocess
from pathlib import Path

from maintenance.patterns import FENCE_RE

_FIX_MERMAID = "operation: projection build"
_FIX_SITE = "operation: site build"

MERMAID_OPEN_RE = re.compile(
    r"^\s*(```|~~~)\s*mermaid\b.*$", re.IGNORECASE)
BARE_FENCE_RE = re.compile(r"^\s*(```|~~~)\s*$")

# Mermaid diagram types accepted by the pinned renderer (mermaid 10.9.3).
# First non-empty, non-comment line must start with one of these (case
# sensitive except for the lowercase aliases below). Unknown types fail
# with DIAG-2 rather than guessing.
KNOWN_DIAGRAM_KEYWORDS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram-v2",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "journey",
    "gitGraph",
    "gitgraph",
    "C4Context",
    "C4Container",
    "C4Component",
    "C4Dynamic",
    "C4Deployment",
    "sankey-beta",
    "xychart-beta",
    "requirementDiagram",
    "quadrantChart",
    "block-beta",
    "packet-beta",
    "kanban",
    "architecture-beta",
    "radar-beta",
)

FORBIDDEN_MERMAID_PATTERNS = (
    r"mermaid\.min\.js",
    r"mermaid\.esm(?:\.min)?\.js",
    r"cdn\.jsdelivr\.net/.*/mermaid",
    r"unpkg\.com/.*/mermaid",
    r"mermaid\.initialize\s*\(",
    r"mermaid\.run\s*\(",
    r"mermaid\.contentLoaded",
    r"<script[^>]*mermaid",
    r"import\s+[^;]*from\s+[\"']mermaid[\"']",
    r"from\s+[\"']mermaid[\"']\s+import",
    r"require\s*\(\s*[\"']mermaid[\"']\s*\)",
)

_FORBIDDEN_RES = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_MERMAID_PATTERNS]


class MermaidError(Exception):
    def __init__(self, message: str, *, rule: str = "DIAG-2",
                 path: str | Path | None = None,
                 hint: str = _FIX_MERMAID):
        self.rule = rule
        loc = str(path) if path is not None else "mermaid diagram"
        super().__init__(f"{loc}: [{rule}] {message}; {hint}")


def extract_mermaid_blocks(body_lines: list[str]):
    """Find mermaid fences fence-aware.

    Returns list of dicts {open, close|None, code, closed}. ``open`` is the
    opening fence index, ``close`` the closing fence index or None when
    unclosed, ``code`` the raw diagram source between fences.
    Markers inside other fenced blocks are ignored.
    """
    blocks: list[dict] = []
    in_generic = False
    i = 0
    n = len(body_lines)
    while i < n:
        line = body_lines[i]
        if in_generic:
            # Only a bare fence closes a generic block; info fences like
            # ```mermaid inside are content, not closers (CommonMark).
            if BARE_FENCE_RE.match(line):
                in_generic = False
            i += 1
            continue
        if MERMAID_OPEN_RE.match(line):
            open_idx = i
            code_lines: list[str] = []
            j = i + 1
            closed = False
            close_idx: int | None = None
            while j < n:
                # Mermaid closes on a bare fence; an info fence inside is
                # diagram content (defensive, diagrams never contain fences).
                if BARE_FENCE_RE.match(body_lines[j]):
                    closed = True
                    close_idx = j
                    break
                # A non-bare fence (e.g. ```python) inside a mermaid block
                # is also treated as closing for robustness? No: keep as
                # content to avoid swallowing following docs. Only bare
                # closes; otherwise keep scanning.
                if FENCE_RE.match(body_lines[j]) and not BARE_FENCE_RE.match(
                        body_lines[j]):
                    # Could be a stray opening; treat as content.
                    code_lines.append(body_lines[j])
                    j += 1
                    continue
                code_lines.append(body_lines[j])
                j += 1
            if closed:
                blocks.append({
                    "open": open_idx,
                    "close": close_idx,
                    "code": "\n".join(code_lines),
                    "closed": True,
                })
                i = close_idx  # type: ignore[assignment]
            else:
                blocks.append({
                    "open": open_idx,
                    "close": None,
                    "code": "\n".join(code_lines),
                    "closed": False,
                })
                i = n
        elif FENCE_RE.match(line):
            in_generic = not in_generic
        i += 1
    return blocks


def _first_code_line(code: str) -> str:
    for raw in code.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("%%"):
            continue
        return s
    return ""


def validate_diagram(code: str, *, source_path=None) -> None:
    """Validate diagram source; raise MermaidError (DIAG-2) when invalid."""
    loc = str(source_path) if source_path is not None else "mermaid diagram"
    if code.strip() == "":
        raise MermaidError(
            "Mermaid diagram cannot render: empty diagram (no content "
            "between fences)",
            path=loc)
    # Unclosed is reported by the extractor, but a direct call with None
    # handling lives in process_mermaid_blocks.
    first = _first_code_line(code)
    if not first:
        raise MermaidError(
            "Mermaid diagram cannot render: empty diagram (only blank lines "
            "or comments)",
            path=loc)
    for kw in KNOWN_DIAGRAM_KEYWORDS:
        if first == kw or first.startswith(kw + " ") \
                or first.startswith(kw + "\t") or first.startswith(kw + ";"):
            return
    raise MermaidError(
        f"Mermaid diagram cannot render: unknown diagram type in {first!r} "
        f"(expected one of: flowchart, graph, sequenceDiagram, "
        f"classDiagram, stateDiagram, erDiagram, gantt, pie, ...)",
        path=loc)


def normalize_svg(svg: str) -> str:
    """Normalize nondeterministic identifiers for repeatable tests (DIAG-4)."""
    # mermaid-xxx random/auto-increment ids -> stable token.
    out = re.sub(r"mermaid-[A-Za-z0-9_-]+", "mermaid-static", svg)
    # UUIDs -> stable token.
    out = re.sub(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "uuid-static", out)
    # Long hex hashes (>=7 hex chars as whole token) -> stable token.
    # Avoid touching short numbers or ordinary words.
    out = re.sub(r"\b[0-9a-fA-F]{7,}\b", "hash-static", out)
    # mermaid generated arrow/marker counters like "-12345" at end of ids?
    # Already covered by mermaid-xxx; keep other numbers intact (deterministic
    # layout coordinates must not be normalized away).
    return out


def deterministic_svg(code: str, *, diagram_index: int = 0,
                      slug: str = "") -> str:
    """Build a deterministic placeholder SVG (offline fallback)."""
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()[:12]
    escaped = html.escape(code, quote=True)
    label = f"Mermaid diagram {diagram_index + 1}"
    # Keep the SVG free of forbidden client-JS tokens (no <script>, no
    # mermaid.initialize/run). The data-* attributes use "mermaid" only as
    # a static marker, never as code.
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'data-diagram-index="{diagram_index}" '
        f'data-diagram-digest="{digest}" role="img" '
        f'aria-label="{html.escape(label, quote=True)}">\n'
        f"<title>{html.escape(label, quote=True)}</title>\n"
        f"<desc>Static rendering of mermaid source "
        f"(deterministic fallback; real Chromium rendering via pinned "
        f"Playwright when available). Slug: "
        f"{html.escape(slug, quote=True)}</desc>\n"
        f'<text x="10" y="20" font-family="monospace" font-size="12">'
        f"{escaped}</text>\n"
        f"</svg>"
    )
    return normalize_svg(svg)


def _renderer_script() -> Path:
    return Path(__file__).resolve().parent.parent / "renderer" / "render-mermaid.mjs"


def render_via_toolchain(code: str, *, diagram_index: int = 0):
    """Try the pinned Node/Playwright/Chromium toolchain.

    Returns SVG string on success, None when the toolchain is unavailable
    (missing node/script) so callers fall back deterministically. Raises
    MermaidError when the toolchain reports a diagram syntax failure.
    Mockable in unit tests (no network required).
    """
    script = _renderer_script()
    if not script.is_file():
        return None
    try:
        proc = subprocess.run(
            ["node", str(script), str(diagram_index)],
            input=code, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 0 and "<svg" in proc.stdout:
        return normalize_svg(proc.stdout)
    if proc.returncode == 2:
        diag = (proc.stderr or proc.stdout or "unknown Mermaid error").strip()
        raise MermaidError(f"Mermaid diagram cannot render: {diag}")
    return None


def render_diagram(code: str, *, source_path=None, diagram_index: int = 0,
                   slug: str = "") -> str:
    """Validate + render one diagram to deterministic SVG (DIAG-1/2/4)."""
    validate_diagram(code, source_path=source_path)
    try:
        via_tool = render_via_toolchain(code, diagram_index=diagram_index)
    except MermaidError as exc:
        # Attach source path when the toolchain omitted it.
        msg = str(exc)
        loc = str(source_path) if source_path is not None else ""
        if loc and loc not in msg:
            raise MermaidError(
                f"Mermaid diagram {diagram_index + 1} cannot render: {exc}",
                path=loc) from exc
        raise
    if via_tool is not None:
        # Normalize even mocked toolchain output (DIAG-4 repeatability).
        return normalize_svg(via_tool)
    return deterministic_svg(code, diagram_index=diagram_index, slug=slug)


def svg_rel_for_slug(slug: str, diagram_index: int) -> str:
    flat = slug.strip("/").replace("/", "-")
    if not flat:
        flat = "diagram"
    return f"mermaid/{flat}-{diagram_index}.svg"


def process_mermaid_blocks(body_lines: list[str], *, source_path,
                           slug: str):
    """Replace mermaid fences with inline static SVGs (DIAG-1).

    Returns (new_lines, svg_files, errors) where svg_files is a list of
    (svg_rel, svg_content) for the disposable output and errors are DIAG-2
    diagnostics with source path.
    """
    loc = str(source_path)
    blocks = extract_mermaid_blocks(body_lines)
    if not blocks:
        return list(body_lines), [], []
    svg_files: list[tuple[str, str]] = []
    errors: list[str] = []
    for diagram_index, blk in enumerate(blocks):
        if not blk["closed"]:
            errors.append(
                f"{loc}: [DIAG-2] Mermaid diagram {diagram_index + 1} "
                f"cannot render: unclosed ```mermaid fence "
                f"(missing closing fence); {_FIX_MERMAID}")
            continue
        code = blk["code"]
        try:
            svg = render_diagram(
                code, source_path=loc,
                diagram_index=diagram_index, slug=slug)
        except MermaidError as exc:
            # Ensure message carries source path + rule + fix.
            msg = str(exc)
            if "[DIAG-2]" not in msg:
                msg = f"{loc}: [DIAG-2] {exc}; {_FIX_MERMAID}"
            elif _FIX_MERMAID not in msg and "operation:" not in msg:
                msg = f"{msg}; {_FIX_MERMAID}"
            errors.append(msg)
            continue
        svg_rel = svg_rel_for_slug(slug, diagram_index)
        svg_files.append((svg_rel, svg))
        label = f"Mermaid diagram {diagram_index + 1}"
        replacement = [
            f'<div class="mermaid-static" data-diagram-index="{diagram_index}">',
            svg,
            "</div>",
        ]
        # Splice: replace open..close inclusive with replacement.
        # Since we iterate in order, track offset.
        # Instead collect splices and apply at end in reverse.
        blk["_replacement"] = replacement
        blk["_svg_rel"] = svg_rel
        _ = label
    if errors:
        return list(body_lines), [], errors
    # Apply replacements in reverse order.
    out = list(body_lines)
    for blk in reversed(blocks):
        rep = blk.get("_replacement")
        if rep is None:
            continue
        o = blk["open"]
        c = blk["close"]
        assert c is not None
        out[o:c + 1] = rep
    # svg_files already in document order.
    ordered_svg: list[tuple[str, str]] = []
    for blk in blocks:
        rel = blk.get("_svg_rel")
        if rel is None:
            continue
        # Find matching content.
        for r, content in svg_files:
            if r == rel:
                ordered_svg.append((r, content))
                break
    return out, ordered_svg, []


def check_no_mermaid_client_js(out_dir: Path) -> list[str]:
    """Inspect built output for forbidden Mermaid client code (DIAG-3).

    Scans all text files below out_dir (excluding .git). Returns error
    strings (empty when clean). Binary files are skipped.
    """
    problems: list[str] = []
    root = Path(out_dir)
    if not root.is_dir():
        return [f"{root}: [DIAG-3] built output directory missing"]
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts:
            continue
        if not path.is_file():
            continue
        # Skip known binary extensions quickly.
        if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif",
                                   ".webp", ".ico", ".woff", ".woff2",
                                   ".ttf", ".eot", ".pdf", ".zip"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for rx in _FORBIDDEN_RES:
            m = rx.search(text)
            if m:
                rel = path.relative_to(root).as_posix()
                problems.append(
                    f"{rel}: [DIAG-3] forbidden Mermaid client JavaScript "
                    f"({m.group(0)[:80]!r}); remove client bundle, keep "
                    f"static SVGs only")
                break
    return sorted(problems)


def contains_forbidden_js(text: str) -> str | None:
    """Return the matched forbidden pattern or None (unit-test seam)."""
    for rx in _FORBIDDEN_RES:
        m = rx.search(text)
        if m:
            return m.group(0)
    return None
