"""Deterministic course navigation and lab pagination.

Course policy (group translations, subject order, lab route prefixes,
last lessons, and UI labels) comes from config.navigation. Unconfigured
routes use humanized labels and the generic subject/labs or labs/section
conventions. Numbered lab sections follow their source-directory order.

Sidebar construction and group redirects share child ordering so their
first-lesson targets agree. Index titles take precedence over configured
group labels. Lab sequences cross sidebar groups; only lab pages receive
explicit prev/next links. Starlight merges per-locale trees with translated
labels while preserving locale-only lessons.

Logical redirects omit the configured site base; the renderer adds it.
Root redirects require the configured root lesson's committed slug.
"""

from __future__ import annotations

import urllib.parse

from .options import NavigationOptions


def navigation_options(config=None):
    return getattr(config, "navigation", NavigationOptions())


def index_label(lang, config=None):
    return navigation_options(config).index_labels.get(
        lang, INDEX_LINK_LABELS.get(lang, "Overview"))


def source_label(lang, config=None):
    return navigation_options(config).source_labels.get(
        lang, VIEW_ON_GITHUB_LABELS.get(lang, "View on GitHub"))

INDEX_LINK_LABELS: dict[str, str] = {"en": "Overview", "ru": "Обзор"}

VIEW_ON_GITHUB_LABELS: dict[str, str] = {
    "en": "View on GitHub",
    "ru": "Посмотреть на GitHub",
}


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


def is_lab_slug(slug: str, config=None) -> bool:
    """A lab page matches ``/{lang}/{subject}/labs/...`` or
    ``/{lang}/labs/{section}/...`` (SITE-11)."""
    prefixes = navigation_options(config).lab_prefixes
    if prefixes:
        rest = strip_lang(slug)
        return any(rest.startswith(prefix + "/") for prefix in prefixes)
    parts = slug.strip("/").split("/")
    return len(parts) >= 4 and (parts[2] == "labs" or parts[1] == "labs")


def lab_subject(slug: str, config=None) -> str | None:
    """Subject/section segment of a lab slug (SITE-11).

    Subject-first layout returns parts[1]; labs-first layout returns
    the section right after ``labs`` (parts[2]).
    """
    if not is_lab_slug(slug, config):
        return None
    prefixes = navigation_options(config).lab_prefixes
    if prefixes:
        rest = strip_lang(slug)
        prefix = max((p for p in prefixes if rest.startswith(p + "/")), key=len)
        parts = prefix.split("/")
        return parts[-2] if parts[-1] == "labs" and len(parts) > 1 else parts[-1]
    parts = slug.strip("/").split("/")
    if parts[2] == "labs":
        return parts[1]
    return parts[2]


def _entries_section_number(entries: list[dict], config=None) -> int | None:
    """Repo-order number shared by lab entries, else None.

    When every entry is a lab page whose source file lives directly in
    a numbered directory (e.g. ``1_basic/``), return the smallest such
    number so lab sections follow repo order. Otherwise return None
    and the caller falls back to alphabetical order (historical
    behavior for unnumbered layouts such as DSA's ``labs/cpp/``).
    """
    try:
        from maintenance.rename import parse_ordered
    except ImportError:  # pragma: no cover - same checkout always has it
        return None
    numbers = []
    for e in entries:
        if not is_lab_slug(e.get("slug", ""), config):
            return None
        parent = e.get("source", "").rpartition("/")[0].rpartition("/")[2]
        parsed = parse_ordered(parent) if parent else None
        if parsed is None:
            return None
        numbers.append(parsed[0])
    if not numbers:
        return None
    return min(numbers)


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


def lab_display_label(slug: str, source: str, title: str, config=None) -> str:
    """Display label for SITE-16: numbered labs prefixed, else plain.

    Only lab pages (SITE-11 slugs) whose source filename carries an
    ordering prefix get ``"{n}. {title}"``; unnumbered labs and all
    non-lab lessons keep their plain title. Overview index links are
    handled by the caller (never passed here).
    """
    if not is_lab_slug(slug, config):
        return title
    prefix = lab_number_prefix(source)
    if prefix is None:
        return title
    return f"{prefix}. {title}"


def get_base(identity) -> str:
    """GitHub Pages project base, e.g. ``/my-repo/`` (SITE-2)."""
    path = urllib.parse.urlsplit(identity.pages_url).path
    return path.rstrip("/") + "/"


def get_site_and_base(identity) -> tuple[str, str]:
    """Return (site, base) for Astro config (SITE-2)."""
    parsed = urllib.parse.urlsplit(identity.pages_url)
    site = f"{parsed.scheme}://{parsed.netloc}"
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
        raise ValueError(f"{config.root_lesson}: missing root lesson slug; operation: metadata generate")
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
                group_rest, rest_to_entry, lang, all_groups, config)
            if target is not None:
                out[f"/{lang}/{group_rest}/"] = f"/{target}/"
    return dict(sorted(out.items()))


def get_playground_redirects(config) -> dict[str, str]:
    """Per-locale redirects from ``/{lang}/{route}/`` to ``/{route}/?lang={lang}``.

    Starlight localizes sidebar internal links (``/playground/`` -> ``/<base>/<lang>/playground/``);
    when playground-site.js is present it rewrites the link directly to ``/<base>/playground/?lang=<lang>&theme=...``,
    and these redirects provide a working no-JS fallback.
    """
    pg = getattr(config, "playground", None)
    if pg is None:
        return {}
    route = pg.route.strip("/")
    out: dict[str, str] = {}
    for lang in config.languages:
        code = lang.code
        out[f"/{code}/{route}/"] = f"/{route}/?lang={code}"
    return dict(sorted(out.items()))


def _first_descendant_slug(group_rest: str, rest_to_entry: dict,
                           lang: str, all_groups: set[str], config=None) -> str | None:
    """First lesson slug below a group in sidebar order (SITE-15)."""
    lessons, subgroups = _ordered_children(
        group_rest, rest_to_entry, lang, all_groups, config)
    if lessons:
        return lessons[0]["slug"]
    for sub in subgroups:
        hit = _first_descendant_slug(sub, rest_to_entry, lang, all_groups, config)
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
                      all_groups: set[str], config=None
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
    # Order subgroups: lab-only sections in numbered source dirs follow
    # repo order first; everything else by label for determinism.
    numbered: list = []
    plain: list = []
    for g in sub_paths:
        label = group_label(g, rest_to_entry, lang, config)
        members = [e for r, e in rest_to_entry.items()
                   if r == g or r.startswith(g + "/")]
        num = _entries_section_number(members, config)
        if num is None:
            plain.append((label.casefold(), label, g))
        else:
            numbered.append((num, label.casefold(), label, g))
    numbered.sort()
    plain.sort()
    subgroups = [g for _, _, _, g in numbered] + [g for _, _, g in plain]
    return lessons, subgroups


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
        out[lang] = _build_one_locale(by_lang[lang], lang, config)
    return out


def _build_one_locale(entries: list[dict], lang: str, config=None) -> list:
    rest_to_entry, all_groups = _locale_rest_map(entries)

    def build_group(group_rest: str) -> list:
        # Index lesson for this group.
        index_entry = rest_to_entry.get(group_rest) if group_rest else None
        # Direct lessons + subgroups in shared sidebar order (SITE-7/9;
        # same order SITE-15 redirect targets use).
        lessons, sub_paths = _ordered_children(
            group_rest, rest_to_entry, lang, all_groups, config)
        labelled = [(group_label(g, rest_to_entry, lang, config), g)
                    for g in sub_paths]
        items: list = []
        if index_entry is not None:
            items.append({
                "label": index_label(lang, config),
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
                    e["slug"], e.get("source", ""), e.get("title", ""), config),
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
    subject_order = navigation_options(config).subject_order
    top_subs = sorted(
        {g.split("/")[0] for g in all_groups if g},
        key=lambda s: (0, subject_order.index(s))
        if s in subject_order else (1, s.casefold(), s),
    )
    # Ensure fixed subjects appear even when empty? Only include groups
    # that actually exist (no synthetic listing, SITE-10).
    sidebar: list = []
    for sub in top_subs:
        if sub not in all_groups:
            continue
        sidebar.append({
            "label": group_label(sub, rest_to_entry, lang, config),
            "collapsed": True,
            "items": build_group(sub),
        })
    return sidebar


def group_label(group_rest: str, rest_to_entry: dict, lang: str, config=None) -> str:
    """Label for a group path (SITE-6/SITE-7)."""
    index = rest_to_entry.get(group_rest)
    if index is not None and index.get("title"):
        return index["title"]
    seg = group_rest.split("/")[-1] if group_rest else ""
    labels = navigation_options(config).group_labels
    translated = labels.get(group_rest, labels.get(seg, {}))
    if lang in translated:
        return translated[lang]
    return humanize_segment(seg)


def build_lab_sequences(nav: list[dict], config=None) -> dict[str, list[str]]:
    """One lab slug sequence per locale (SITE-11).

    Configured subjects first, then source-numbered/name order; configured
    last_lessons follow the other lessons within their subject.
    """
    by_lang: dict[str, list[dict]] = {}
    for e in nav:
        if is_lab_slug(e.get("slug", ""), config):
            by_lang.setdefault(e["lang"], []).append(e)
    out: dict[str, list[str]] = {}
    for lang, entries in by_lang.items():
        by_subject: dict[str, list[dict]] = {}
        for e in entries:
            by_subject.setdefault(lab_subject(e["slug"], config) or "", []).append(e)

        def sort_key(e: dict):
            slug = e["slug"]
            is_last = strip_lang(slug) in navigation_options(config).last_lessons
            return (1 if is_last else 0,
                    e.get("order", 0), slug)

        subject_order = navigation_options(config).subject_order
        seq: list[str] = []
        for subj in subject_order:
            members = sorted(by_subject.get(subj, []), key=sort_key)
            seq.extend(m["slug"] for m in members)

        def others_key(s: str):
            num = _entries_section_number(by_subject[s], config)
            if num is None:
                return (1, 0, s.casefold())
            return (0, num, s.casefold())

        others = sorted(
            (s for s in by_subject if s not in subject_order),
            key=others_key)
        for subj in others:
            members = sorted(by_subject[subj], key=sort_key)
            seq.extend(m["slug"] for m in members)
        out[lang] = seq
    return out


def lab_pagination(nav: list[dict], config=None) -> dict[str, dict]:
    """Explicit prev/next slugs for lab pages (SITE-11).

    Returns ``{slug: {"prev": slug|None, "next": slug|None}}``. Non-lab
    slugs are absent (sidebar-order pagination).
    """
    seqs = build_lab_sequences(nav, config)
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
                if n.get("label") in (index_label(default, config),
                                      "Overview"):
                    item: dict = {"slug": rest, "label": n["label"]}
                    trans = {}
                    for lang, tree in zip(others, other_trees):
                        c = find_link(tree, rest)
                        if c is not None:
                            trans[lang] = c.get(
                                "label",
                                index_label(lang, config))
                    if trans:
                        item["translations"] = trans
                    result.append(item)
                elif is_lab_slug(n["slug"], config):
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
            elif "link" in n:
                item = {"label": n["label"], "link": n["link"]}
                if "translations" in n and n["translations"]:
                    item["translations"] = dict(n["translations"])
                if "attrs" in n and n["attrs"]:
                    item["attrs"] = dict(n["attrs"])
                result.append(item)
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
        if is_lab_slug(f"{default}/{rest}", config):
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

    pg = getattr(config, "playground", None)
    if pg is not None:
        group_name = pg.sidebar_group.strip("/")
        prefix = group_name + "/"
        group_labels = navigation_options(config).group_labels.get(
            group_name, {})
        fallback_labels = {
            group_labels.get(default),
            humanize_segment(group_name),
        } - {None}

        def has_group_descendant(node: dict) -> bool:
            s = node.get("slug")
            if s and (s == group_name or s.startswith(prefix)):
                return True
            return any(has_group_descendant(c) for c in node.get("items", []))

        def insert_playground(nodes: list) -> bool:
            for node in nodes:
                if "items" not in node:
                    continue
                if has_group_descendant(node) or node.get("label") in fallback_labels:
                    pg_item: dict = {
                        "label": pg.label,
                        "link": f"/{pg.route.strip('/')}/",
                        "attrs": {
                            "class": "cv-rainbow-link cv-rainbow-sidebar",
                            "data-astro-reload": "",
                        },
                    }
                    if pg.translations:
                        pg_item["translations"] = dict(pg.translations)
                    node["items"].insert(0, pg_item)
                    return True
                if insert_playground(node["items"]):
                    return True
            return False

        insert_playground(merged)

    return merged
