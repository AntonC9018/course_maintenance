"""Starlight navigation data (SITE-2..SITE-16, issue #11).

Pure, stdlib-only helpers for locale-prefixed routes, redirects, sidebar
generation, lab pagination, GitHub source links, Pagefind and base path.
No filesystem writes and no npm invocation here; orchestration lives in
:mod:`publishing.site`.

Sidebar model (per locale, snapshot-friendly):

- link: ``{"label": str, "slug": full_slug}`` where full_slug includes the
  language prefix (``en/...``), matching ``nav.json`` slugs and
  ``src/content/docs/<slug>.md`` projection paths. Numbered lab lessons
  (SITE-16) carry a prefixed label ``"{n}. {title}"``; all other lessons
  carry their plain title.
- group: ``{"label": str, "collapsed": True, "items": [...]}`` (never
  clickable, never synthetic; SITE-10). Indexless groups additionally get
  an Astro redirect to their first descendant lesson (SITE-15;
  :func:`get_group_redirects`); a redirect is not a listing page and
  generates no content.

Starlight conversion (``to_starlight_sidebar``) strips the language prefix
(Starlight slugs exclude the locale directory) and adds ``translations``
for group labels, index Overview links and lab lesson links (SITE-16).
Lab links use explicit ``{"slug": rest, "label": ...}`` so the
source-number prefix shows to the left of the label using only the label
string (no badge/CSS, SITE-5); ordinary non-lab lesson links use
``{"slug": rest}`` without an explicit label so Starlight renders the
per-locale frontmatter title automatically.

Ordering (SITE-9): direct child lessons reuse projection ``order``
(numeric incl lettered ``21a`` first, unnumbered alphabetical last).
Unelected ``index/README/doc`` lessons follow the index link in precedence
``index > README > doc`` (SITE-7). Subgroups follow lessons, sorted by
label (fixed/humanized/index-title) for determinism. Top-level subject
groups use the fixed order Common, C++, DSA; other top-level segments
follow alphabetically.

Groups (SITE-7/10): a group whose rest path equals an index lesson slug
uses that lesson title as its label; its lesson appears first as
``Overview``/``Обзор``. Other groups use fixed SITE-6 labels for
``common/cpp/dsa/labs`` or humanized segments otherwise. All groups are
``collapsed: True`` (SITE-8); highlighting/expansion/scroll remain
Starlight defaults (no custom code).

Labs (SITE-11): ``is_lab_slug`` matches ``/{lang}/{subject}/labs/...``.
Per-locale lab sequences order Common, C++, DSA subjects; within a lab
group numbered labs use projection order and unnumbered follow
alphabetically; ``assessment-1`` is last among C++ labs. Lab pages get
explicit prev/next; non-lab pages use sidebar-order pagination (no
frontmatter overrides).

Lab numbers (SITE-16): numbered lab lessons display their source-file
ordering number to the left of the sidebar label as ``"{n}. {title}"``
(plain integer, no zero-padding, lettered ``21a`` kept as-is, single
space after the dot; number parsed from the source filename via
``maintenance.rename.parse_ordered``, display uses the author's source
number even with gaps, never the global sequence position).
Unnumbered labs and non-labs keep their plain title; Overview index links
keep ``Overview``/``Обзор``; group labels unchanged.
"""

from __future__ import annotations

import urllib.parse

FIXED_LABELS: dict[str, dict[str, str]] = {
    "common": {"en": "Common", "ru": "Общие темы"},
    "cpp": {"en": "C++", "ru": "C++"},
    "dsa": {"en": "Data Structures and Algorithms",
            "ru": "Структуры данных и алгоритмы"},
    "labs": {"en": "Labs", "ru": "Лабораторные работы"},
}

INDEX_LINK_LABELS: dict[str, str] = {"en": "Overview", "ru": "Обзор"}

VIEW_ON_GITHUB_LABELS: dict[str, str] = {
    "en": "View on GitHub",
    "ru": "Посмотреть на GitHub",
}

LAB_SUBJECT_ORDER = ("common", "cpp", "dsa")
TOP_SUBJECT_ORDER = ("common", "cpp", "dsa")

_UNELECTED_PRECEDENCE = {"index.md": 0, "readme.md": 1, "doc.md": 2}


def humanize_segment(seg: str) -> str:
    """Humanize a route segment (SITE-7).

    Replace each hyphen with a space and uppercase the first cased
    character without otherwise changing the segment.
    """
    s = seg.replace("-", " ")
    for i, ch in enumerate(s):
        # "cased" = has distinct upper/lower forms.
        if ch.lower() != ch.upper():
            return s[:i] + ch.upper() + s[i + 1:]
    return s


def strip_lang(slug: str) -> str:
    """Return slug without its leading language component."""
    parts = slug.strip("/").split("/")
    if len(parts) <= 1:
        return ""
    return "/".join(parts[1:])


def lang_of_slug(slug: str) -> str:
    return slug.strip("/").split("/")[0] if slug.strip("/") else ""


def is_lab_slug(slug: str) -> bool:
    """A lab page matches /{lang}/{subject}/labs/... (SITE-11)."""
    parts = slug.strip("/").split("/")
    return len(parts) >= 4 and parts[2] == "labs"


def lab_subject(slug: str) -> str | None:
    if not is_lab_slug(slug):
        return None
    return slug.strip("/").split("/")[1]


def lab_number_prefix(source: str) -> str | None:
    """Source-file ordering number for SITE-16 (e.g. "1", "21a").

    Parses the numeric prefix from the lesson's source filename via
    ``maintenance.rename.parse_ordered`` (no divergent regex). Returns
    the plain integer without zero-padding with any letter kept as-is
    (``01_`` -> ``"1"``, ``21a_`` -> ``"21a"``), including an optional
    ``_N`` sub-number when present, or None when the source is
    unnumbered. Deterministic and locale-independent.
    """
    if not source:
        return None
    try:
        from maintenance.rename import parse_ordered
    except ImportError:  # pragma: no cover - same checkout always has it
        return None
    parsed = parse_ordered(source)
    if parsed is None:
        return None
    n1, letter, n2, _rest, _suffix = parsed
    prefix = str(n1) + (letter or "")
    if n2 is not None:
        prefix += f"_{n2}"
    return prefix


def lab_display_label(slug: str, source: str, title: str) -> str:
    """Display label for SITE-16: numbered labs prefixed, else plain.

    Only lab pages (SITE-11 slugs) whose source filename carries an
    ordering prefix get ``"{n}. {title}"``; unnumbered labs and all
    non-lab lessons keep their plain title. Overview index links are
    handled by the caller (never passed here).
    """
    if not is_lab_slug(slug):
        return title
    prefix = lab_number_prefix(source)
    if prefix is None:
        return title
    return f"{prefix}. {title}"


def get_base(identity) -> str:
    """GitHub Pages project base, e.g. ``/my-repo/`` (SITE-2)."""
    return f"/{identity.repo}/"


def get_site_and_base(identity) -> tuple[str, str]:
    """Return (site, base) for Astro config (SITE-2)."""
    site = f"https://{identity.owner}.github.io"
    return site, get_base(identity)


def quote_repo_rel(repo_rel: str) -> str:
    return "/".join(urllib.parse.quote(p, safe="") for p in repo_rel.split("/"))


def github_blob_url(identity, repo_rel: str) -> str:
    """Normal rendered source-document URL (blob, master) (SITE-12)."""
    base = f"{identity.github_url}/blob/{identity.default_branch or 'master'}"
    quoted = quote_repo_rel(repo_rel)
    return f"{base}/{quoted}" if quoted else base


def get_redirects(config, final_slugs: dict[str, str]) -> dict[str, str]:
    """Root + locale-root redirects (SITE-3/SITE-4).

    Derives the English target from ``config.root_lesson``'s final slug
    and swaps the language prefix for other locales. ``/`` targets the
    default language.
    """
    root_rel = config.root_lesson
    root_slug = final_slugs.get(root_rel)
    if root_slug is None:
        # Fall back to the spec default when the root lesson has no slug
        # (callers validate metadata first; this keeps --check messages
        # actionable rather than crashing).
        default = getattr(config, "default_language", "en")
        rest = "common/labs/computer-architecture"
        out = {"/": f"/{default}/{rest}/"}
        for lang in [l.code for l in config.languages]:
            out[f"/{lang}/"] = f"/{lang}/{rest}/"
        return out
    parts = root_slug.strip("/").split("/")
    rest = "/".join(parts[1:]) if len(parts) > 1 else ""
    out: dict[str, str] = {}
    for lang in [l.code for l in config.languages]:
        out[f"/{lang}/"] = f"/{lang}/{rest}/"
    default = getattr(config, "default_language", "en")
    out["/"] = f"/{default}/{rest}/"
    return out


def get_group_redirects(nav: list[dict], config) -> dict[str, str]:
    """Indexless-group redirects (SITE-15).

    Every sidebar group route ``/{lang}/{group...}/`` without an index
    lesson redirects to the first descendant lesson in that group's
    sidebar order (same ordering as :func:`build_sidebars`: direct
    lessons before subgroups, SITE-9 numeric incl ``21a`` then
    alphabetical, unelected index/README/doc right after the index link
    per SITE-7; recurse into the first subgroup when a group has no
    direct lesson children). Groups with an index lesson serve that
    lesson and get no redirect. Root/``/{lang}/`` are SITE-3/4
    (:func:`get_redirects`) and are never emitted here.

    Keys/values are logical (base-less) trailing-slash URLs, the same
    form as :func:`get_redirects` output; :mod:`publishing.site` adds
    the Pages base when rendering Astro ``redirects``. Sorted by key;
    deterministic.
    """
    langs = [l.code for l in config.languages]
    by_lang: dict[str, list[dict]] = {l: [] for l in langs}
    for entry in nav:
        if entry.get("lang") in by_lang:
            by_lang[entry["lang"]].append(entry)
    out: dict[str, str] = {}
    for lang in langs:
        rest_to_entry, all_groups = _locale_rest_map(by_lang[lang])
        for group_rest in sorted(all_groups):
            if not group_rest:
                continue  # site/locale roots: SITE-3/4, not SITE-15.
            if group_rest in rest_to_entry:
                continue  # indexed group serves its lesson.
            target = _first_descendant_slug(
                group_rest, rest_to_entry, lang, all_groups)
            if target is not None:
                out[f"/{lang}/{group_rest}/"] = f"/{target}/"
    return dict(sorted(out.items()))


def _first_descendant_slug(group_rest: str, rest_to_entry: dict,
                           lang: str, all_groups: set[str]) -> str | None:
    """First lesson slug below a group in sidebar order (SITE-15)."""
    lessons, subgroups = _ordered_children(
        group_rest, rest_to_entry, lang, all_groups)
    if lessons:
        return lessons[0]["slug"]
    for sub in subgroups:
        hit = _first_descendant_slug(sub, rest_to_entry, lang, all_groups)
        if hit is not None:
            return hit
    return None


def _locale_rest_map(entries: list[dict]
                     ) -> tuple[dict[str, dict], set[str]]:
    """Per-locale rest index + group paths (shared sidebar/redirect base).

    ``rest_to_entry`` maps language-less rests to nav entries (bare
    language roots skipped: no starter pages, SITE-3). ``all_groups``
    holds every parent prefix plus every index rest with children.
    """
    rest_to_entry: dict[str, dict] = {}
    for e in entries:
        rest = strip_lang(e["slug"])
        # Skip bare language roots (should not occur; no starter pages).
        if not rest:
            continue
        rest_to_entry[rest] = e
    rests = sorted(rest_to_entry)
    # Index rests: entry rest equals a group path. Every entry rest is a
    # potential group path if other entries live below it.
    all_groups: set[str] = set([""])
    for rest in rests:
        cur = rest
        while "/" in cur:
            cur = cur.rpartition("/")[0]
            all_groups.add(cur)
        # Top-level single-segment rests (e.g. "common") have parent ""
        # already; single-segment index rests are groups themselves.
    for rest in rests:
        # An index rest is itself a group when it has children.
        prefix = rest + "/"
        if any(r.startswith(prefix) for r in rests):
            all_groups.add(rest)
    return rest_to_entry, all_groups


def _split_direct_lessons(group_rest: str, rest_to_entry: dict
                        ) -> tuple[list[dict], list[dict]]:
    """(unelected, ordinary) direct child lessons in sidebar order."""
    child_lessons = [
        e for r, e in rest_to_entry.items()
        if _group_parent(r) == group_rest and r != group_rest
    ]
    unelected: list[dict] = []
    ordinary: list[dict] = []
    for e in child_lessons:
        base = e.get("source", "").rpartition("/")[2].lower()
        last = e["slug"].strip("/").split("/")[-1]
        if base in _UNELECTED_PRECEDENCE and last in (
                "index", "readme", "doc"):
            unelected.append(e)
        else:
            ordinary.append(e)
    unelected.sort(key=lambda e: (
        _UNELECTED_PRECEDENCE.get(
            e.get("source", "").rpartition("/")[2].lower(), 9),
        e["slug"]))
    ordinary.sort(key=lambda e: (e.get("order", 0), e["slug"]))
    return unelected, ordinary


def _ordered_children(group_rest: str, rest_to_entry: dict, lang: str,
                      all_groups: set[str]
                      ) -> tuple[list[dict], list[str]]:
    """Direct lessons + subgroups of a group in sidebar order (SITE-7/9).

    Lessons (unelected index/README/doc in precedence order, then
    ordinary by projection order) come before subgroups (sorted by
    label for determinism). Shared by sidebar construction and SITE-15
    redirect targets so the two can never order divergently.
    """
    unelected, ordinary = _split_direct_lessons(
        group_rest, rest_to_entry)
    lessons = unelected + ordinary
    # Direct child subgroups.
    sub_paths = sorted(
        g for g in all_groups
        if g and _group_parent(g) == group_rest and g != group_rest)
    # Order subgroups by label for determinism.
    labelled = [(group_label(g, rest_to_entry, lang), g)
                for g in sub_paths]
    labelled.sort(key=lambda t: (t[0].casefold(), t[1]))
    return lessons, [g for _label, g in labelled]


def _group_parent(rest: str) -> str:
    if "/" not in rest:
        return ""
    return rest.rpartition("/")[0]


def _all_group_paths(rests: list[str]) -> set[str]:
    groups: set[str] = set([""])
    for rest in rests:
        # Every parent prefix is a group; index rests are groups too.
        cur = rest
        # Add the rest itself only if it is an index (handled by caller
        # via index map); parents always groups.
        while "/" in cur:
            cur = cur.rpartition("/")[0]
            groups.add(cur)
        # Top-level single-segment rests (e.g. "common") have parent ""
        # already; single-segment index rests are groups themselves.
    return groups


def build_sidebars(nav: list[dict], config) -> dict[str, list]:
    """Build one sidebar tree per locale (SITE-6..SITE-10, SITE-16).

    ``nav`` entries need ``slug/title/lang/source/order``. Returns
    ``{lang: [items]}`` where items are link/group dicts (see module
    docstring). Numbered lab lessons carry SITE-16 prefixed labels;
    Overview index links keep ``Overview``/``Обзор``. Deterministic;
    sorted as documented.
    """
    langs = [l.code for l in config.languages]
    by_lang: dict[str, list[dict]] = {l: [] for l in langs}
    for entry in nav:
        if entry.get("lang") in by_lang:
            by_lang[entry["lang"]].append(entry)

    out: dict[str, list] = {}
    for lang in langs:
        out[lang] = _build_one_locale(by_lang[lang], lang)
    return out


def _build_one_locale(entries: list[dict], lang: str) -> list:
    rest_to_entry, all_groups = _locale_rest_map(entries)

    def build_group(group_rest: str) -> list:
        # Index lesson for this group.
        index_entry = rest_to_entry.get(group_rest) if group_rest else None
        # Direct lessons + subgroups in shared sidebar order (SITE-7/9;
        # same order SITE-15 redirect targets use).
        lessons, sub_paths = _ordered_children(
            group_rest, rest_to_entry, lang, all_groups)
        labelled = [(group_label(g, rest_to_entry, lang), g)
                    for g in sub_paths]
        items: list = []
        if index_entry is not None:
            items.append({
                "label": INDEX_LINK_LABELS.get(lang, "Overview"),
                "slug": index_entry["slug"],
            })
        for e in lessons:
            # Skip entries that are themselves groups with children?
            # An ordinary lesson rest could also be a group path (index
            # with children) -- but then it would be the index (rest ==
            # group). Since r != group_rest here, and rest_to_entry has
            # this rest, if it also has children it is both lesson and
            # group; that only happens for index rests, which are handled
            # as index, not ordinary. So ordinary rests never equal a
            # group with children except via unelected edge (already
            # separated). Safe to emit as link.
            # SITE-16: numbered labs prefixed, all others plain; Overview
            # index links above keep Overview/Обзор with no number.
            items.append({
                "label": lab_display_label(
                    e["slug"], e.get("source", ""), e.get("title", "")),
                "slug": e["slug"],
            })
        for label, g in labelled:
            items.append({
                "label": label,
                "collapsed": True,
                "items": build_group(g),
            })
        return items

    # Top-level: fixed subject order, then others alphabetically.
    top_subs = sorted(
        {g.split("/")[0] for g in all_groups if g},
        key=lambda s: (0, TOP_SUBJECT_ORDER.index(s))
        if s in TOP_SUBJECT_ORDER else (1, s.casefold(), s),
    )
    # Ensure fixed subjects appear even when empty? Only include groups
    # that actually exist (no synthetic listing, SITE-10).
    sidebar: list = []
    for sub in top_subs:
        if sub not in all_groups:
            continue
        sidebar.append({
            "label": group_label(sub, rest_to_entry, lang),
            "collapsed": True,
            "items": build_group(sub),
        })
    return sidebar


def group_label(group_rest: str, rest_to_entry: dict, lang: str) -> str:
    """Label for a group path (SITE-6/SITE-7)."""
    index = rest_to_entry.get(group_rest)
    if index is not None and index.get("title"):
        return index["title"]
    seg = group_rest.split("/")[-1] if group_rest else ""
    if seg in FIXED_LABELS:
        return FIXED_LABELS[seg].get(lang, FIXED_LABELS[seg].get("en", seg))
    return humanize_segment(seg)


def build_lab_sequences(nav: list[dict]) -> dict[str, list[str]]:
    """One lab slug sequence per locale (SITE-11).

    Common, C++, DSA subjects in order; numbered by projection order,
    unnumbered after alphabetically (projection order already encodes
    this); Assessment 1 last among C++ labs.
    """
    by_lang: dict[str, list[dict]] = {}
    for e in nav:
        if is_lab_slug(e.get("slug", "")):
            by_lang.setdefault(e["lang"], []).append(e)
    out: dict[str, list[str]] = {}
    for lang, entries in by_lang.items():
        by_subject: dict[str, list[dict]] = {}
        for e in entries:
            by_subject.setdefault(lab_subject(e["slug"]) or "", []).append(e)

        def sort_key(e: dict):
            slug = e["slug"]
            last = slug.strip("/").split("/")[-1]
            is_assessment = (
                lab_subject(slug) == "cpp" and last == "assessment-1")
            return (1 if is_assessment else 0,
                    e.get("order", 0), slug)

        seq: list[str] = []
        for subj in LAB_SUBJECT_ORDER:
            members = sorted(by_subject.get(subj, []), key=sort_key)
            seq.extend(m["slug"] for m in members)
        others = sorted(
            (s for s in by_subject if s not in LAB_SUBJECT_ORDER),
            key=lambda s: s.casefold())
        for subj in others:
            members = sorted(by_subject[subj], key=sort_key)
            seq.extend(m["slug"] for m in members)
        out[lang] = seq
    return out


def lab_pagination(nav: list[dict]) -> dict[str, dict]:
    """Explicit prev/next slugs for lab pages (SITE-11).

    Returns ``{slug: {"prev": slug|None, "next": slug|None}}``. Non-lab
    slugs are absent (sidebar-order pagination).
    """
    seqs = build_lab_sequences(nav)
    out: dict[str, dict] = {}
    for _lang, seq in seqs.items():
        for i, slug in enumerate(seq):
            prev_slug = seq[i - 1] if i > 0 else None
            next_slug = seq[i + 1] if i + 1 < len(seq) else None
            out[slug] = {"prev": prev_slug, "next": next_slug}
    return out


def to_starlight_slug(full_slug: str) -> str:
    """Starlight sidebar slug (no language prefix)."""
    return strip_lang(full_slug)


def build_starlight_sidebar(per_locale: dict[str, list],
                            config) -> list:
    """Merge per-locale trees into one Starlight sidebar (translations).

    Uses the default locale structure as canonical and attaches
    translations for group labels, index Overview links and lab lesson
    links (SITE-16). Lab links use explicit ``{"slug": rest, "label": ...}``
    so the source-number prefix shows; ordinary non-lab lesson links use
    ``{"slug": rest}`` so Starlight renders per-locale titles
    automatically. Groups are ``collapsed: True`` (SITE-8).
    Union: ``ru``-only branches missing from the default locale are
    appended deterministically so no lesson is hidden.
    """
    langs = [l.code for l in config.languages]
    default = getattr(config, "default_language", "en")
    others = [l for l in langs if l != default]
    canonical = per_locale.get(default)
    if canonical is None:
        canonical = next(iter(per_locale.values()))

    def find_link(tree: list, rest: str):
        for x in tree:
            if "slug" in x and strip_lang(x["slug"]) == rest:
                return x
            if "items" in x:
                r = find_link(x["items"], rest)
                if r is not None:
                    return r
        return None

    def descendant_rests(node) -> set[str]:
        found: set[str] = set()
        if "slug" in node:
            found.add(strip_lang(node["slug"]))
        if "items" in node:
            for c in node["items"]:
                found |= descendant_rests(c)
        return found

    def find_group(tree: list, want: set[str]):
        # Phase 1: exact match at any depth (DFS).
        def exact(ns: list):
            for n in ns:
                if "items" in n:
                    if descendant_rests(n) == want:
                        return n
                    sub = exact(n["items"])
                    if sub is not None:
                        return sub
            return None
        hit = exact(tree)
        if hit is not None:
            return hit
        # Phase 2: shallowest overlapping group (BFS) so top-level
        # counterparts win over nested Labs subgroups.
        queue: list[list] = [tree]
        while queue:
            level = queue.pop(0)
            for n in level:
                if "items" in n and (descendant_rests(n) & want):
                    return n
            for n in level:
                if "items" in n:
                    queue.append(n["items"])
        return None

    def convert(nodes, other_trees: list[list]) -> list:
        result = []
        for n in nodes:
            if "slug" in n:
                rest = strip_lang(n["slug"])
                if n.get("label") in (INDEX_LINK_LABELS.get(default),
                                      "Overview"):
                    item: dict = {"slug": rest, "label": n["label"]}
                    trans = {}
                    for lang, tree in zip(others, other_trees):
                        c = find_link(tree, rest)
                        if c is not None:
                            trans[lang] = c.get(
                                "label",
                                INDEX_LINK_LABELS.get(lang, "Обзор"))
                    if trans:
                        item["translations"] = trans
                    result.append(item)
                elif is_lab_slug(n["slug"]):
                    # SITE-16: explicit lab labels (numbered prefixed,
                    # unnumbered plain) with per-locale translations.
                    item = {"slug": rest, "label": n["label"]}
                    trans = {}
                    for lang, tree in zip(others, other_trees):
                        c = find_link(tree, rest)
                        if c is not None:
                            trans[lang] = c.get("label", n["label"])
                    if trans:
                        item["translations"] = trans
                    result.append(item)
                else:
                    result.append({"slug": rest})
            elif "items" in n:
                want = descendant_rests(n)
                trans = {}
                for lang, tree in zip(others, other_trees):
                    c = find_group(tree, want)
                    if c is not None:
                        trans[lang] = c.get("label", n["label"])
                item = {"label": n["label"], "collapsed": True,
                        "items": convert(n["items"], other_trees)}
                if trans:
                    item["translations"] = trans
                result.append(item)
        return result

    other_lists = [per_locale.get(l, []) for l in others]
    merged = convert(canonical, other_lists)
    # Union: append other-locale-only link rests deterministically.
    have: set[str] = set()

    def collect(ns):
        for x in ns:
            if "slug" in x:
                have.add(x["slug"])
            if "items" in x:
                collect(x["items"])
    collect(merged)
    # rest -> {lang: label} for other-locale-only links (SITE-16 needs
    # explicit lab labels; non-labs keep the historical slug-only shape).
    extras: dict[str, dict[str, str]] = {}
    for lang in others:
        def walk(ns, _lang=lang):
            for x in ns:
                if "slug" in x:
                    rest = strip_lang(x["slug"])
                    if rest not in have:
                        have.add(rest)
                        extras.setdefault(rest, {})[_lang] = x.get(
                            "label", "")
                    elif rest in extras and _lang not in extras[rest]:
                        # Same rest appears in several other locales:
                        # keep each locale's label for translations.
                        extras[rest][_lang] = x.get("label", "")
                if "items" in x:
                    walk(x["items"], _lang)
        walk(per_locale.get(lang, []))
    for rest in sorted(extras):
        labels = extras[rest]
        # Lab rest check via a dummy language prefix (SITE-11 shape).
        if is_lab_slug(f"{default}/{rest}"):
            # Deterministic label: first other locale in config order.
            ordered_langs = [l for l in others if l in labels]
            first_lang = ordered_langs[0] if ordered_langs else sorted(
                labels)[0]
            item = {"slug": rest, "label": labels[first_lang]}
            trans = {l: labels[l] for l in ordered_langs[1:]}
            if trans:
                item["translations"] = trans
            merged.append(item)
        else:
            merged.append({"slug": rest})
    return merged
