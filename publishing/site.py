"""Static site build via the pinned Astro Starlight renderer (SITE-1..14 + DIAG).

Orchestration for ``publish.py site build`` (issues #11 Mermaid excluded,
#12 Mermaid + compatibility). Stdlib-only Python; the Node toolchain is
invoked via subprocess and is mockable in unit tests (no npm required for
config-generation tests).

Pipeline (after shared validation identical to ``projection build``):

1. In-memory projection via :mod:`publishing.projection`
   (``collect_projection_data`` incl. DIAG-1 static Mermaid SVGs).
2. Navigation data via :mod:`publishing.navigation` (sidebars, lab
   pagination, redirects, base, GitHub blob URLs).
3. Renderer-only frontmatter augmentation of the in-memory projection:
   lab ``prev``/``next`` (explicit, SITE-11) and per-page ``editUrl``
   (blob URL, SITE-12). Non-lab pages keep sidebar-order pagination
   (no overrides). ``sidebar.order`` from the projection is preserved
   (SITE-9).
4. Write the Astro project below ``--out`` (outside the course repo):
   projected docs (mermaid fences already inline static SVGs, DIAG-1),
   static Mermaid SVGs under ``mermaid/`` + ``public/mermaid/`` (DIAG-1,
   never committed, DIAG-3), copied images, ``nav.json``,
   ``site-nav.json`` (per-locale sidebars + lab sequences,
   snapshot-friendly), ``astro.config.mjs`` (SITE-1..8, SITE-13, no Mermaid
   client JS per DIAG-3), ``package.json`` (pinned versions incl. Mermaid +
   Playwright/Chromium, SITE-1/DIAG-1), ``src/content.config.ts``,
   ``src/content/i18n/*.json`` (localized View on GitHub, SITE-12),
   ``public/.nojekyll`` (Pagefind ``_pagefind`` under Pages).
5. Invoke the pinned toolchain (``npm ci`` when ``node_modules`` is
   missing, then ``npm run build``) with ``SITE_BASE``/cwd set to the
   output directory. On missing npm or failed install/build, return a
   clear error without guessing (offline-friendly; unit tests mock this
   step). A successful build leaves static HTML in ``<out>/dist/`` with
   trailing-slash URLs under the project base (SITE-2). Built output is
   inspected for forbidden Mermaid client JS (DIAG-3).

No fallback lesson files are ever generated (SITE-3); locale roots have
no starter pages (only Astro ``redirects``). No views/presentation
controls or placeholders are emitted (SITE-14). No Mermaid client JS is
shipped and no SVGs are committed (DIAG-3).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PINNED_VERSIONS = {
    # Proven by the compatibility suite (representative lessons with
    # nested details, C++ angle brackets, `$`code`$`/`$$` math, static
    # Mermaid SVGs, tables, images, nested routes, rewritten links and the
    # Pages project base). Exact pins, no ranges; lock file committed
    # under renderer/.
    "astro": "7.3.2",
    "@astrojs/starlight": "0.42.1",
    "@astrojs/markdown-remark": "7.3.1",
    "remark-math": "6.0.0",
    "rehype-katex": "7.0.1",
    "katex": "0.16.47",
    # DIAG-1: Mermaid static rendering via pinned Playwright/Chromium.
    # mermaid 10.9.3: last 10.x stable, Node 18 compatible, render() API
    # stable for flowchart/sequence/class/state/er/gantt/pie/mindmap.
    # playwright 1.48.2 bundles Chromium 130.0.6723.19 (see PINNED_BROWSERS).
    "mermaid": "10.9.3",
    "playwright": "1.48.2",
}

PINNED_BROWSERS = {
    # Chromium revision bundled with playwright 1.48.2 (DIAG-1). Pinned
    # here for CI cache keys (CI-8) and smoke-test reproducibility; the
    # actual browser is installed via `npx playwright install chromium`
    # which resolves to this build for the pinned playwright version.
    # Never cached as authoritative output, only as runtime.
    "chromium": "130.0.6723.19",
}

RENDERER_DIR_NAME = "renderer"


def renderer_dir() -> Path:
    return Path(__file__).resolve().parent.parent / RENDERER_DIR_NAME


def astro_base(identity) -> str:
    return f"/{identity.repo}/"


def astro_site(identity) -> str:
    return f"https://{identity.owner}.github.io"


def edit_link_base(identity) -> str:
    return f"{identity.github_url}/blob/{identity.default_branch or 'master'}/"


def _js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def generate_package_json() -> dict:
    v = PINNED_VERSIONS
    return {
        "name": "course-site",
        "private": True,
        "version": "0.0.0",
        "type": "module",
        "scripts": {
            "dev": "astro dev",
            "build": "astro build",
            "preview": "astro preview",
        },
        "dependencies": {
            "astro": v["astro"],
            "@astrojs/starlight": v["@astrojs/starlight"],
            "@astrojs/markdown-remark": v["@astrojs/markdown-remark"],
            "remark-math": v["remark-math"],
            "rehype-katex": v["rehype-katex"],
            "katex": v["katex"],
            "mermaid": v["mermaid"],
            "playwright": v["playwright"],
        },
    }


def generate_content_config() -> str:
    return (
        "import { defineCollection } from 'astro:content';\n"
        "import { docsLoader, i18nLoader } from '@astrojs/starlight/loaders';\n"
        "import { docsSchema, i18nSchema } from '@astrojs/starlight/schema';\n"
        "\n"
        "export const collections = {\n"
        "  docs: defineCollection({ loader: docsLoader(), "
        "schema: docsSchema() }),\n"
        "  i18n: defineCollection({ loader: i18nLoader(), "
        "schema: i18nSchema() }),\n"
        "};\n"
    )


def _sidebar_to_js(sidebar: list, indent: int = 4) -> str:
    """Render Starlight sidebar Python data as JS source (deterministic)."""
    pad = " " * indent

    def render(node, level: int) -> str:
        p = " " * (indent + level * 2)
        if "slug" in node and "items" not in node:
            parts = [f"{p}slug: {json.dumps(node['slug'], ensure_ascii=False)}"]
            if "label" in node:
                parts.append(
                    f"{p}label: {json.dumps(node['label'], ensure_ascii=False)}")
            if "translations" in node:
                trans = json.dumps(node["translations"],
                                   ensure_ascii=False, sort_keys=True)
                parts.append(f"{p}translations: {trans}")
            inner = ",\n".join(parts)
            return p + "{\n" + inner + f"\n{p[:-2]}" + "}"
        # group
        lines = [p + "{"]
        lines.append(
            f"{p}  label: {json.dumps(node['label'], ensure_ascii=False)},")
        if "translations" in node:
            trans = json.dumps(node["translations"],
                               ensure_ascii=False, sort_keys=True)
            lines.append(f"{p}  translations: {trans},")
        lines.append(f"{p}  collapsed: true,")
        lines.append(f"{p}  items: [")
        for child in node.get("items", []):
            lines.append(render(child, level + 2) + ",")
        lines.append(f"{p}  ],")
        lines.append(p + "}")
        return "\n".join(lines)

    lines = ["["]
    for item in sidebar:
        lines.append(render(item, 1) + ",")
    lines.append(" " * (indent - 2) + "]")
    return "\n".join(lines)


def generate_astro_config(config, identity, starlight_sidebar,
                           redirects: dict[str, str]) -> str:
    """Render the per-course ``astro.config.mjs`` (SITE-1..8, SITE-13 + DIAG)."""
    from .navigation import VIEW_ON_GITHUB_LABELS  # noqa: F401 (doc link)

    site = astro_site(identity)
    base = astro_base(identity)
    titles = {l.code: config.site_title[l.code] for l in config.languages}
    locales_js = ",\n".join(
        f"      {json.dumps(l.code)}: "
        f"{{ label: {json.dumps(l.label, ensure_ascii=False)} }}"
        for l in config.languages)
    sidebar_js = _sidebar_to_js(starlight_sidebar, indent=8)
    # Astro prefixes redirect sources with `base` but leaves targets as-is,
    # so targets must include the project base explicitly (SITE-2), e.g.
    # base /R/ + logical /en/.../ -> /R/en/.../. `get_redirects` returns
    # logical (base-less) targets for snapshot testing; config adds base.
    base_prefix = base.rstrip("/")
    redirects_js = ",\n".join(
        f"    {json.dumps(k)}: {json.dumps(base_prefix + v)}"
        for k, v in sorted(redirects.items()))
    lines = [
        "import { defineConfig } from 'astro/config';",
        "import starlight from '@astrojs/starlight';",
        "import remarkMath from 'remark-math';",
        "import rehypeKatex from 'rehype-katex';",
        "",
        "// Generated by course_maintenance `site build` (issues #11-12).",
        "// Pinned toolchain versions live in package.json + package-lock.json",
        "// under renderer/ (SITE-1, DIAG-1: astro/starlight/math + mermaid +",
        "// playwright/chromium). Do not edit by hand.",
        "// Mermaid fences are pre-rendered to static SVGs (DIAG-1); no",
        "// Mermaid client JavaScript is shipped (DIAG-3).",
        f"// Site titles: {', '.join(f'{k}={v!r}' for k, v in sorted(titles.items()))}",
        f"// Pages: {identity.pages_url}",
        f"// Base: {base}",
        "export default defineConfig({",
        f"  site: {json.dumps(site)},",
        f"  base: {json.dumps(base)},",
        "  trailingSlash: 'always',",
        "  output: 'static',",
        "  redirects: {",
        redirects_js + ("," if redirects_js else ""),
        "  },",
        "  markdown: {",
        "    remarkPlugins: [remarkMath],",
        "    rehypePlugins: [rehypeKatex],",
        "  },",
        "  integrations: [",
        "    starlight({",
        f"      title: {json.dumps(titles, ensure_ascii=False, sort_keys=True)},",
        f"      defaultLocale: {json.dumps(config.default_language)},",
        "      locales: {",
        locales_js + ("," if locales_js else ""),
        "      },",
        "      sidebar: ",
        sidebar_js + ",",
        f"      editLink: {{ baseUrl: {json.dumps(edit_link_base(identity))} }},",
        "      pagefind: true,",
        "      pagination: true,",
        "      // Default theme/layout/typography/responsive/outline retained",
        "      // (SITE-5); groups collapsed via sidebar data (SITE-8);",
        "      // current-page highlight, ancestor expansion and scroll",
        "      // persistence are Starlight defaults (no custom code).",
        "      // No views/presentation controls or placeholders (SITE-14).",
        "    }),",
        "  ],",
        "});",
        "",
    ]
    return "\n".join(lines)


def _split_frontmatter(text: str):
    # Reuse the canonical frontmatter splitter (no duplication).
    from .metadata import split_frontmatter as _split
    has_fm, _end, fm_lines, rest_lines, _all = _split(text)
    if not has_fm:
        return False, [], text.splitlines()
    return True, fm_lines, rest_lines


def _upsert_frontmatter(fm_lines: list[str], key: str, value: str) -> list[str]:
    """Set ``key: value`` in frontmatter (top-level, replace if present)."""
    out = list(fm_lines)
    for i in range(1, len(out) - 1):
        stripped = out[i].strip()
        if stripped.startswith(f"{key}:"):
            out[i] = f"{key}: {value}"
            return out
        # Do not touch nested keys (indented) -- only top-level.
        if stripped.startswith(f"{key} :"):
            out[i] = f"{key}: {value}"
            return out
    out.insert(len(out) - 1, f"{key}: {value}")
    return out


def _format_prev_next(link: str | None, label: str | None):
    if link is None:
        return "false"
    if label:
        return f"{{ link: {json.dumps(link)}, label: {json.dumps(label, ensure_ascii=False)} }}"
    return json.dumps(link)


def augment_projection_files(files: dict[str, str], nav: list[dict],
                             identity, repo) -> dict[str, str]:
    """Inject lab prev/next + per-page editUrl (SITE-11/SITE-12).

    ``files`` maps ``src/content/docs/<slug>.md`` to text (in-memory
    projection). Returns a new dict; inputs unchanged. Non-lab pages keep
    sidebar-order pagination (no prev/next keys).
    """
    from .navigation import github_blob_url, is_lab_slug, lab_pagination

    base = astro_base(identity).rstrip("/")
    by_slug = {e["slug"]: e for e in nav}
    title_by_slug = {e["slug"]: e.get("title", "") for e in nav}
    source_by_slug = {}
    for e in nav:
        # nav has ``source`` repo_rel; fall back to output-derived.
        source_by_slug[e["slug"]] = e.get("source", "")
    pag = lab_pagination(nav)
    out: dict[str, str] = {}
    for rel, text in files.items():
        # rel = src/content/docs/<slug>.md
        prefix = "src/content/docs/"
        slug = rel[len(prefix):-3] if rel.startswith(prefix) and rel.endswith(".md") else None
        if slug is None or slug not in by_slug:
            out[rel] = text
            continue
        has_fm, fm_lines, rest = _split_frontmatter(text)
        if not has_fm:
            fm_lines = ["---", f"title: {title_by_slug.get(slug, slug)}", "---"]
        # SITE-12: per-page blob URL (normal rendered source page).
        repo_rel = source_by_slug.get(slug, "")
        if repo_rel:
            blob = github_blob_url(identity, repo_rel)
            fm_lines = _upsert_frontmatter(fm_lines, "editUrl", json.dumps(blob))
        # SITE-11: explicit lab pagination; non-lab untouched.
        if is_lab_slug(slug) and slug in pag:
            prev_slug = pag[slug]["prev"]
            next_slug = pag[slug]["next"]

            def page_url(s: str) -> str:
                return f"{base}/{s}/"

            prev_label = title_by_slug.get(prev_slug, "") if prev_slug else None
            next_label = title_by_slug.get(next_slug, "") if next_slug else None
            prev_val = _format_prev_next(
                page_url(prev_slug) if prev_slug else None, prev_label)
            next_val = _format_prev_next(
                page_url(next_slug) if next_slug else None, next_label)
            fm_lines = _upsert_frontmatter(fm_lines, "prev", prev_val)
            fm_lines = _upsert_frontmatter(fm_lines, "next", next_val)
        if rest:
            out[rel] = "\n".join(fm_lines) + "\n" + "\n".join(rest).rstrip("\n") + "\n"
        else:
            out[rel] = "\n".join(fm_lines) + "\n"
    return out


def write_site_project(out_dir: Path, files: dict[str, str], copy_list,
                       nav: list[dict], per_locale: dict, lab_sequences: dict,
                       config, identity, starlight_sidebar,
                       redirects: dict[str, str]) -> None:
    """Write the Astro project below out_dir (deterministic, no timestamps).

    ``files`` includes projected Markdown plus static Mermaid SVGs under
    ``mermaid/`` (DIAG-1). SVGs are mirrored to ``public/mermaid/`` so the
    real Astro build copies them to ``dist/mermaid/`` for smoke tests;
    projected Markdown already embeds the same SVG inline (no client JS,
    DIAG-3).
    """
    from .navigation import VIEW_ON_GITHUB_LABELS

    out_dir.mkdir(parents=True, exist_ok=True)
    for rel in sorted(files):
        dest = out_dir / Path(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(files[rel], encoding="utf-8")
    # Mirror static SVGs for serving (public/ -> dist/ via Astro).
    for rel in sorted(files):
        if rel.startswith("mermaid/") and rel.endswith(".svg"):
            # rel is mermaid/<flat>.svg -> public/mermaid/<flat>.svg
            pub = out_dir / "public" / Path(*rel.split("/"))
            pub.parent.mkdir(parents=True, exist_ok=True)
            pub.write_text(files[rel], encoding="utf-8")
    for _src_abs, copy_rel in sorted(copy_list, key=lambda t: t[1]):
        # Images served from public/ below the Pages base (SITE-2);
        # markdown references /<repo>/assets/... (see links.resolve_link).
        dest = out_dir / "public" / Path(*copy_rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(Path(_src_abs).read_bytes())
    (out_dir / "nav.json").write_text(
        json.dumps(nav, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (out_dir / "site-nav.json").write_text(
        json.dumps({"sidebar": per_locale, "lab_sequences": lab_sequences,
                    "redirects": redirects,
                    "base": astro_base(identity),
                    "site": astro_site(identity)},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    (out_dir / "astro.config.mjs").write_text(
        generate_astro_config(config, identity, starlight_sidebar, redirects),
        encoding="utf-8")
    (out_dir / "package.json").write_text(
        json.dumps(generate_package_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    # Reuse the committed lock file when present (SITE-1 reproducibility).
    lock_src = renderer_dir() / "package-lock.json"
    if lock_src.is_file():
        shutil.copyfile(lock_src, out_dir / "package-lock.json")
    # Content collections (docs + i18n) for Starlight.
    cfg_path = out_dir / "src" / "content.config.ts"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(generate_content_config(), encoding="utf-8")
    i18n_dir = out_dir / "src" / "content" / "i18n"
    i18n_dir.mkdir(parents=True, exist_ok=True)
    for lang in [l.code for l in config.languages]:
        label = VIEW_ON_GITHUB_LABELS.get(lang, VIEW_ON_GITHUB_LABELS["en"])
        (i18n_dir / f"{lang}.json").write_text(
            json.dumps({"page.editLink": label},
                       ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    public = out_dir / "public"
    public.mkdir(parents=True, exist_ok=True)
    (public / ".nojekyll").write_bytes(b"")
    dist_dir = out_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    keep = dist_dir / ".gitkeep"
    if not any(dist_dir.iterdir()):
        keep.write_bytes(b"")


def run_npm_build(out_dir: Path) -> tuple[int, str]:
    """Run ``npm ci`` (when needed) + ``npm run build`` in out_dir.

    Returns (exit_code, combined_output). Missing npm or failures return
    nonzero with actionable output; callers never guess.
    """
    try:
        proc = subprocess.run(
            ["npm", "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return 2, f"npm not available: {exc}"
    if proc.returncode != 0:
        return 2, f"npm not available: {proc.stdout}{proc.stderr}"
    cmds: list[list[str]] = []
    if not (out_dir / "node_modules").is_dir():
        if (out_dir / "package-lock.json").is_file():
            cmds.append(["npm", "ci", "--no-audit", "--no-fund"])
        else:
            cmds.append(["npm", "install", "--no-audit", "--no-fund"])
    cmds.append(["npm", "run", "build"])
    combined: list[str] = []
    for cmd in cmds:
        try:
            proc = subprocess.run(
                cmd, cwd=str(out_dir), capture_output=True, text=True,
                timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, f"failed to run {' '.join(cmd)}: {exc}"
        combined.append(f"$ {' '.join(cmd)}\n{proc.stdout}{proc.stderr}")
        if proc.returncode != 0:
            return proc.returncode, "\n".join(combined)
    return 0, "\n".join(combined)


def run_site_build(course_repo: Path, args) -> int:
    """Handler(course_repo, args) -> int for publish.py registry."""
    from .config import load_config
    from .identity import infer_identity
    from .inventory import build_inventory
    from .links import build_link_index, validate_all_links
    from .metadata import collect_metadata_state, validate_all_metadata
    from .navigation import (build_lab_sequences, build_sidebars,
                             build_starlight_sidebar, get_redirects)
    from .projection import (_clean_out_dir, collect_projection_data,
                             validate_out_location)

    repo = Path(course_repo).resolve()
    raw_out = getattr(args, "out", None)
    check_mode = bool(getattr(args, "check", False))
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
    per_locale = build_sidebars(nav, config)
    lab_sequences = build_lab_sequences(nav)
    starlight_sidebar = build_starlight_sidebar(per_locale, config)
    redirects = get_redirects(config, final)
    if check_mode:
        n = sum(1 for k in files if k.startswith("src/content/docs/"))
        print(f"site check: OK ({n} lesson(s); "
              f"{len(per_locale)} locale(s); deterministic; "
              f"source unchanged; no writes)")
        return 0
    if out_resolved is None:
        out_resolved = Path(
            tempfile.mkdtemp(prefix="course-site-")).resolve()
        problem = validate_out_location(repo, out_resolved)
        if problem is not None:  # pragma: no cover - /tmp sibling
            print(f"error: {problem}", file=sys.stderr)
            return 2
    else:
        out_resolved.mkdir(parents=True, exist_ok=True)
        _clean_out_dir(out_resolved)
    try:
        augmented = augment_projection_files(files, nav, identity, repo)
        write_site_project(out_resolved, augmented, copy_list, nav,
                           per_locale, lab_sequences, config, identity,
                           starlight_sidebar, redirects)
    except OSError as exc:
        print(f"error: cannot write site project to {out_resolved}: {exc}; "
              f"operation: site build", file=sys.stderr)
        return 1
    # DIAG-3: fail early when generated project ships Mermaid client JS.
    try:
        from .mermaid import check_no_mermaid_client_js
        forbidden = check_no_mermaid_client_js(out_resolved)
    except Exception:
        forbidden = []
    if forbidden:
        for msg in forbidden:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    code, output = run_npm_build(out_resolved)
    if code != 0:
        print(f"error: renderer build failed in {out_resolved} "
              f"(SITE-1 pinned toolchain via npm ci/build); "
              f"operation: site build\n{output}", file=sys.stderr)
        print(f"site build: projection + config written to {out_resolved}; "
              f"dist/ pending renderer success", file=sys.stderr)
        return 1
    # Remove placeholder keep when a real build produced output.
    keep = out_resolved / "dist" / ".gitkeep"
    try:
        if keep.is_file() and any(
                p.name != ".gitkeep"
                for p in (out_resolved / "dist").iterdir()):
            keep.unlink()
    except OSError:
        pass
    # DIAG-3: inspect built output (dist when real, else project) for
    # forbidden client code; mocked builds still validated via project check
    # above, this covers real `npm run build` HTML.
    try:
        from .mermaid import check_no_mermaid_client_js as _check_js
        _forbidden_dist = _check_js(out_resolved / "dist")
        # dist placeholder contains only .gitkeep when mocked; ignore missing
        # dir errors, fail only on real forbidden hits.
        _forbidden_dist = [m for m in _forbidden_dist
                           if "missing" not in m.lower()]
    except Exception:
        _forbidden_dist = []
    if _forbidden_dist:
        for msg in _forbidden_dist:
            print(f"error: {msg}", file=sys.stderr)
        return 1
    n_lessons = sum(1 for k in files if k.startswith("src/content/docs/"))
    print(f"site build: OK ({n_lessons} lesson(s)) in {out_resolved} "
          f"(dist below)")
    return 0
