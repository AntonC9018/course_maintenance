"""Starlight navigation + site build (issue #11, SITE-1..15 excl Mermaid).

TDD seam: publishing.navigation (pure) + publishing.site (config
generation + `site build` handler with mocked npm). All repos live in
TemporaryDirectory; never mutates live checkouts. Stdlib-only; npm is
mocked (no network/toolchain required for unit tests).
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import run_publish, write


def git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True)


def init_repo_with_origin(root: Path, origin_url="https://github.com/O/R.git"):
    root.mkdir(parents=True, exist_ok=True)
    r = git("init", "-b", "master", cwd=root)
    assert r.returncode == 0, r.stderr
    git("config", "user.email", "t@t.t", cwd=root)
    git("config", "user.name", "t", cwd=root)
    write(root / "placeholder.txt", "x\n")
    git("add", "-A", cwd=root)
    git("commit", "-m", "init", cwd=root)
    if origin_url is not None:
        r = git("remote", "add", "origin", origin_url, cwd=root)
        assert r.returncode == 0, r.stderr
    return root


BASE_CONFIG = {
    "version": 1,
    "default_language": "en",
    "languages": [
        {"code": "en", "root": "en", "label": "English"},
        {"code": "ru", "root": "ru", "label": "Русский"},
    ],
    "exclude": [],
    "route_sections": [
        {"source": "00_intro", "destination": "common"},
        {"source": "04_cpp", "destination": "cpp"},
        {"source": "05a_programming_fundamentals",
         "destination": "cpp/advanced-programming-fundamentals"},
        {"source": "08_dsa", "destination": "dsa"},
        {"source": "labs/common", "destination": "common/labs"},
        {"source": "labs/cpp", "destination": "cpp/labs"},
        {"source": "labs/algorithms", "destination": "dsa/labs"},
    ],
    "site_title": {"en": "EN Title", "ru": "RU Title"},
    "root_lesson": "en/labs/common/01_computer_architecture.md",
    "peer_repositories": [],
}


def write_config(root: Path, cfg=None):
    cfg = BASE_CONFIG if cfg is None else cfg
    write(root / "course-publishing.json",
          json.dumps(cfg, ensure_ascii=False, indent=2))
    return root / "course-publishing.json"


def make_repo(root: Path, files: dict, cfg=None,
              origin="https://github.com/O/R.git"):
    init_repo_with_origin(root, origin)
    write_config(root, BASE_CONFIG if cfg is None else cfg)
    for rel, content in files.items():
        p = root / rel
        if isinstance(content, bytes):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        else:
            write(p, content)
    gen = run_publish("metadata", "generate", "--course-repo", str(root))
    assert gen.returncode == 0, gen.stdout + gen.stderr
    check = run_publish("publishing", "check", "--course-repo", str(root))
    assert check.returncode == 0, check.stdout + check.stderr
    return root


def load_nav(root: Path):
    from publishing.config import load_config
    from publishing.identity import infer_identity
    from publishing.inventory import build_inventory
    from publishing.links import build_link_index
    from publishing.metadata import collect_metadata_state
    from publishing.projection import collect_projection_data
    repo = root.resolve()
    config = load_config(repo)
    identity = infer_identity(repo)
    inventory = build_inventory(repo, config)
    final, errors, _m = collect_metadata_state(
        repo, config, inventory, identity.pages_url)
    assert not errors, errors
    index = build_link_index(repo, config, identity, inventory, final)
    files, copies, nav, proj_errors = collect_projection_data(
        repo, config, identity, inventory, final, index)
    assert not proj_errors, proj_errors
    return config, identity, final, files, copies, nav


RICH_FILES = {
    # Common labs: numeric incl lettered + unnumbered (SITE-9).
    "en/labs/common/01_computer_architecture.md": "---\ntitle: Arch\n---\n# A\n",
    "en/labs/common/02_second.md": "---\ntitle: Second\n---\n# S\n",
    "en/labs/common/21a_appendix.md": "---\ntitle: Appendix\n---\n# X\n",
    "en/labs/common/notes.md": "---\ntitle: Notes\n---\n# N\n",
    # C++ labs incl Assessment 1 (test1 -> assessment-1, last).
    "en/labs/cpp/01_first.md": "---\ntitle: First\n---\n# F\n",
    "en/labs/cpp/02_second.md": "---\ntitle: Cpp Second\n---\n# S\n",
    "en/labs/cpp/test1.md": "---\ntitle: Assessment 1\n---\n# A1\n",
    "en/labs/cpp/notes.md": "---\ntitle: Zeta\n---\n# Z\n",
    # DSA labs.
    "en/labs/algorithms/01_sorting.md": "---\ntitle: Sorting\n---\n# S\n",
    # Common ordinary + index (Common group index).
    "en/00_intro/index.md": "---\ntitle: Common Index Title\n---\n# C\n",
    "en/00_intro/01_intro.md": "---\ntitle: Intro\n---\n# I\n",
    "en/00_intro/02_basics.md": "---\ntitle: Basics\n---\n# B\n",
    # Unelected: guide dir with index (elected) + README + doc.
    "en/00_intro/guide/index.md": "---\ntitle: Guide Index\n---\n# G\n",
    "en/00_intro/guide/README.md": "---\ntitle: Guide Readme\n---\n# R\n",
    "en/00_intro/guide/doc.md": "---\ntitle: Guide Doc\n---\n# D\n",
    # Humanize: sub-topic without index/fixed.
    "en/00_intro/sub-topic/01_foo.md": "---\ntitle: Foo\n---\n# F\n",
    # CPP advanced subgroup with index.
    "en/05a_programming_fundamentals/index.md":
        "---\ntitle: Advanced Index\n---\n# A\n",
    "en/05a_programming_fundamentals/01_deep.md":
        "---\ntitle: Deep\n---\n# D\n",
    # CPP ordinary + DSA ordinary (indexless groups).
    "en/04_cpp/01_intro.md": "---\ntitle: Cpp Intro\n---\n# C\n",
    "en/08_dsa/01_arrays.md": "---\ntitle: Arrays\n---\n# A\n",
    # Russian counterparts (subset: missing some en lessons -> no fallback).
    "ru/labs/common/01_computer_architecture.md":
        "---\ntitle: Арх\n---\n# А\n",
    "ru/labs/cpp/test1.md": "---\ntitle: Оценка 1\n---\n# О\n",
    "ru/00_intro/index.md": "---\ntitle: Общий Индекс\n---\n# О\n",
    "ru/00_intro/01_intro.md": "---\ntitle: Введ\n---\n# В\n",
}


class TestHumanize(unittest.TestCase):
    def test_humanize_basic(self):
        from publishing.navigation import humanize_segment
        self.assertEqual(
            humanize_segment("advanced-programming-fundamentals"),
            "Advanced programming fundamentals")
        self.assertEqual(humanize_segment("labs"), "Labs")
        self.assertEqual(humanize_segment("cpp"), "Cpp")
        self.assertEqual(humanize_segment("123"), "123")
        self.assertEqual(humanize_segment(""), "")

    def test_humanize_first_cased_only(self):
        from publishing.navigation import humanize_segment
        # Digits/hyphens skipped; first cased char uppercased, rest kept.
        self.assertEqual(humanize_segment("21a-foo-bar"), "21A foo bar")
        self.assertEqual(humanize_segment("-foo"), " Foo")


class TestFixedLabels(unittest.TestCase):
    def test_fixed_labels_both_locales(self):
        from publishing.navigation import FIXED_LABELS
        self.assertEqual(FIXED_LABELS["common"]["en"], "Common")
        self.assertEqual(FIXED_LABELS["common"]["ru"], "Общие темы")
        self.assertEqual(FIXED_LABELS["cpp"]["en"], "C++")
        self.assertEqual(FIXED_LABELS["dsa"]["en"],
                         "Data Structures and Algorithms")
        self.assertEqual(FIXED_LABELS["dsa"]["ru"],
                         "Структуры данных и алгоритмы")
        self.assertEqual(FIXED_LABELS["labs"]["ru"], "Лабораторные работы")


class TestSidebarGeneration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, dict(RICH_FILES))
        self.config, self.identity, self.final, self.files, \
            self.copies, self.nav = load_nav(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_top_level_fixed_order_common_cpp_dsa(self):
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)
        for lang in ("en", "ru"):
            labels = [g["label"] for g in sidebars[lang]]
            # Fixed subjects first in Common, C++, DSA order when present.
            # ru has no dsa lessons in this fixture -> only Common/C++.
            if lang == "en":
                self.assertEqual(labels[:3], [
                    "Common Index Title",  # index title overrides fixed
                    "C++", "Data Structures and Algorithms"])
            self.assertTrue(all(g.get("collapsed") is True for g in sidebars[lang]))

    def test_index_group_label_and_overview_link(self):
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)
        en_common = next(
            g for g in sidebars["en"] if g["label"] == "Common Index Title")
        # First item is the Overview index link (SITE-7).
        first = en_common["items"][0]
        self.assertEqual(first["label"], "Overview")
        self.assertEqual(first["slug"], "en/common")
        ru_common = next(
            g for g in sidebars["ru"] if g["label"] == "Общий Индекс")
        self.assertEqual(ru_common["items"][0]["label"], "Обзор")
        self.assertEqual(ru_common["items"][0]["slug"], "ru/common")

    def test_unelected_after_index_in_precedence(self):
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)

        def find_group(items, label):
            for n in items:
                if n.get("label") == label and "items" in n:
                    return n
                if "items" in n:
                    r = find_group(n["items"], label)
                    if r is not None:
                        return r
            return None

        guide = find_group(sidebars["en"], "Guide Index")
        self.assertIsNotNone(guide, "guide subgroup missing")
        slugs = [x.get("slug", "") for x in guide["items"]]
        # Overview first, then README, then doc (precedence order).
        self.assertEqual(slugs[0], "en/common/guide")
        self.assertEqual(slugs[1], "en/common/guide/readme")
        self.assertEqual(slugs[2], "en/common/guide/doc")
        self.assertEqual(guide["items"][0]["label"], "Overview")

    def test_humanize_group_without_fixed_or_index(self):
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)

        def find_group(items, label):
            for n in items:
                if n.get("label") == label and "items" in n:
                    return n
                if "items" in n:
                    r = find_group(n["items"], label)
                    if r is not None:
                        return r
            return None

        sub = find_group(sidebars["en"], "Sub topic")
        self.assertIsNotNone(sub, "humanized sub-topic group missing")

    def test_numeric_lettered_alpha_order_reuses_projection(self):
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)
        # Common labs group: numeric 1,2,21a then unnumbered alpha.
        def find_group(items, label):
            for n in items:
                if n.get("label") == label and "items" in n:
                    return n
                if "items" in n:
                    r = find_group(n["items"], label)
                    if r is not None:
                        return r
            return None

        en_common = next(
            g for g in sidebars["en"] if g["label"] == "Common Index Title")
        labs = find_group([en_common], "Labs")
        self.assertIsNotNone(labs)
        slugs = [x["slug"] for x in labs["items"]]
        self.assertEqual(slugs, [
            "en/common/labs/computer-architecture",
            "en/common/labs/second",
            "en/common/labs/appendix",
            "en/common/labs/notes",
        ])

    def test_indexless_group_non_clickable_no_synthetic(self):
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)
        dsa = next(g for g in sidebars["en"]
                   if g["label"] == "Data Structures and Algorithms")
        self.assertNotIn("slug", dsa)
        self.assertNotIn("link", dsa)
        self.assertTrue(dsa["collapsed"])
        # No synthetic listing file for the indexless DSA group ...
        self.assertNotIn("src/content/docs/en/dsa.md", self.files)
        # ... while the indexed Common group does have its index file.
        self.assertIn("src/content/docs/en/common.md", self.files)

    def test_all_groups_collapsed_no_custom_scroll(self):
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)

        def walk(items):
            for n in items:
                if "items" in n:
                    self.assertTrue(n["collapsed"])
                    self.assertNotIn("slug", n)
                    self.assertNotIn("link", n)
                    walk(n["items"])
        for lang in ("en", "ru"):
            walk(sidebars[lang])

    def test_missing_translations_no_fallback_files(self):
        # en has dsa lessons; ru does not -> no ru fallback files generated.
        ru_slugs = {e["slug"] for e in self.nav if e["lang"] == "ru"}
        self.assertNotIn("ru/dsa/arrays", ru_slugs)
        self.assertNotIn("src/content/docs/ru/dsa/arrays.md", self.files)
        from publishing.navigation import build_sidebars
        sidebars = build_sidebars(self.nav, self.config)
        # Per-locale sidebars differ (no synthesized fallback entries).
        en_slugs = set()
        def collect(items, acc):
            for n in items:
                if "slug" in n:
                    acc.add(n["slug"])
                if "items" in n:
                    collect(n["items"], acc)
        collect(sidebars["en"], en_slugs)
        ru_collected: set[str] = set()
        collect(sidebars["ru"], ru_collected)
        self.assertIn("en/dsa/arrays", en_slugs)
        self.assertNotIn("ru/dsa/arrays", ru_collected)

    def test_sidebar_snapshot_deterministic(self):
        from publishing.navigation import build_sidebars
        first = build_sidebars(self.nav, self.config)
        second = build_sidebars(self.nav, self.config)
        self.assertEqual(first, second)
        snap = json.dumps(first, ensure_ascii=False, sort_keys=True)
        self.assertIn("Common Index Title", snap)
        self.assertIn("Обзор", snap)


class TestLabSequence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, dict(RICH_FILES))
        self.config, self.identity, self.final, self.files, \
            self.copies, self.nav = load_nav(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lab_order_common_cpp_dsa(self):
        from publishing.navigation import build_lab_sequences
        seqs = build_lab_sequences(self.nav)
        en = seqs["en"]
        # Common labs first (numeric then alpha), then C++, then DSA.
        self.assertEqual(en[:4], [
            "en/common/labs/computer-architecture",
            "en/common/labs/second",
            "en/common/labs/appendix",
            "en/common/labs/notes",
        ])
        # C++ labs: numbered, unnumbered alpha, Assessment 1 last.
        cpp = [s for s in en if "/cpp/labs/" in s]
        self.assertEqual(cpp, [
            "en/cpp/labs/first",
            "en/cpp/labs/second",
            "en/cpp/labs/notes",
            "en/cpp/labs/assessment-1",
        ])
        dsa = [s for s in en if "/dsa/labs/" in s]
        self.assertEqual(dsa, ["en/dsa/labs/sorting"])
        # Full order crosses groups: last Common -> first C++ -> ... -> DSA.
        self.assertLess(en.index("en/common/labs/notes"),
                        en.index("en/cpp/labs/first"))
        self.assertLess(en.index("en/cpp/labs/assessment-1"),
                        en.index("en/dsa/labs/sorting"))

    def test_assessment_last_despite_alpha(self):
        from publishing.navigation import build_lab_sequences
        seqs = build_lab_sequences(self.nav)
        cpp = [s for s in seqs["en"] if "/cpp/labs/" in s]
        # 'assessment-1' starts with 'a' (would sort first alphabetically
        # among unnumbered) but must be last.
        self.assertEqual(cpp[-1], "en/cpp/labs/assessment-1")

    def test_lab_pagination_crosses_groups(self):
        from publishing.navigation import lab_pagination
        pag = lab_pagination(self.nav)
        # Boundary Common->C++.
        self.assertEqual(pag["en/common/labs/notes"]["next"],
                         "en/cpp/labs/first")
        self.assertEqual(pag["en/cpp/labs/first"]["prev"],
                         "en/common/labs/notes")
        # Boundary C++->DSA.
        self.assertEqual(pag["en/cpp/labs/assessment-1"]["next"],
                         "en/dsa/labs/sorting")
        # Ends have None on the outer side.
        self.assertIsNone(
            pag["en/common/labs/computer-architecture"]["prev"])
        self.assertIsNone(pag["en/dsa/labs/sorting"]["next"])
        # Non-lab pages have no explicit pagination.
        self.assertNotIn("en/common/intro", pag)

    def test_augment_injects_lab_prev_next_and_editurl(self):
        from publishing.site import augment_projection_files
        augmented = augment_projection_files(
            self.files, self.nav, self.identity, self.root)
        lab_rel = "src/content/docs/en/common/labs/notes.md"
        self.assertIn("prev:", augmented[lab_rel])
        self.assertIn("next:", augmented[lab_rel])
        # notes follows appendix within Common labs; next crosses to C++.
        self.assertIn("/R/en/common/labs/appendix/", augmented[lab_rel])
        self.assertIn("/R/en/cpp/labs/first/", augmented[lab_rel])
        self.assertIn("editUrl:", augmented[lab_rel])
        self.assertIn("/blob/master/en/labs/common/notes.md",
                      augmented[lab_rel])
        # Non-lab keeps sidebar-order pagination (no prev/next).
        nonlab = "src/content/docs/en/common/intro.md"
        self.assertNotIn("\nprev:", augmented[nonlab])
        self.assertNotIn("\nnext:", augmented[nonlab])
        self.assertIn("editUrl:", augmented[nonlab])
        # First lab prev false, last lab next false.
        first = augmented[
            "src/content/docs/en/common/labs/computer-architecture.md"]
        self.assertIn("prev: false", first)
        last = augmented["src/content/docs/en/dsa/labs/sorting.md"]
        self.assertIn("next: false", last)


class TestRedirectsLocalesBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, dict(RICH_FILES))
        self.config, self.identity, self.final, self.files, \
            self.copies, self.nav = load_nav(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_redirects(self):
        from publishing.navigation import get_redirects
        redirects = get_redirects(self.config, self.final)
        self.assertEqual(
            redirects["/"], "/en/common/labs/computer-architecture/")
        self.assertEqual(
            redirects["/en/"], "/en/common/labs/computer-architecture/")
        self.assertEqual(
            redirects["/ru/"], "/ru/common/labs/computer-architecture/")

    def test_no_locale_root_starter_pages(self):
        self.assertNotIn("src/content/docs/en.md", self.files)
        self.assertNotIn("src/content/docs/ru.md", self.files)
        self.assertNotIn("src/content/docs/en/index.md", self.files)

    def test_base_and_site(self):
        from publishing.site import astro_base, astro_site
        self.assertEqual(astro_base(self.identity), "/R/")
        self.assertEqual(astro_site(self.identity),
                         "https://O.github.io")

    def test_astro_config_locales_titles_trailing_pagefind(self):
        from publishing.navigation import (
            build_sidebars, build_starlight_sidebar, get_redirects)
        from publishing.site import generate_astro_config
        per_locale = build_sidebars(self.nav, self.config)
        sidebar = build_starlight_sidebar(per_locale, self.config)
        redirects = get_redirects(self.config, self.final)
        text = generate_astro_config(
            self.config, self.identity, sidebar, redirects)
        self.assertIn("base: \"/R/\"", text)
        self.assertIn("trailingSlash: 'always'", text)
        self.assertIn("defaultLocale: \"en\"", text)
        self.assertIn("EN Title", text)
        self.assertIn("RU Title", text)
        self.assertIn("pagefind: true", text)
        self.assertIn("redirects", text)
        # Redirect targets include the project base (SITE-2).
        self.assertIn("/R/en/common/labs/computer-architecture/", text)
        self.assertIn("remarkMath", text)
        self.assertIn("rehypeKatex", text)
        self.assertIn("blob/master", text)
        # SITE-14: no placeholder routes/labels for deferred views or
        # Slidev presentations (documentation comments may name them to
        # state their absence; placeholders would be routes/links).
        low = text.lower()
        self.assertNotIn("/views/", low)
        self.assertNotIn("/presentations/", low)
        self.assertNotIn("autogenerate", low)
        for item in sidebar:
            self.assertNotIn("views", json.dumps(item).lower())
        # Sidebar slugs must all be existing published routes.
        slugs = {e["slug"] for e in self.nav}
        def walk(items):
            for n in items:
                if "slug" in n:
                    # Starlight slugs exclude the lang prefix.
                    self.assertTrue(
                        f"en/{n['slug']}" in slugs
                        or f"ru/{n['slug']}" in slugs,
                        f"sidebar slug without published route: {n['slug']}")
                if "items" in n:
                    walk(n["items"])
        walk(sidebar)

    def test_github_blob_urls(self):
        from publishing.navigation import github_blob_url
        url = github_blob_url(self.identity, "en/labs/common/notes.md")
        self.assertEqual(
            url, "https://github.com/O/R/blob/master/en/labs/common/notes.md")
        self.assertNotIn("/edit/", url)
        self.assertNotIn("raw", url)

    def test_view_on_github_i18n(self):
        from publishing.navigation import VIEW_ON_GITHUB_LABELS
        self.assertEqual(VIEW_ON_GITHUB_LABELS["en"], "View on GitHub")
        self.assertTrue(VIEW_ON_GITHUB_LABELS["ru"])


class TestGroupRedirects(unittest.TestCase):
    """Indexless sidebar groups redirect to first descendant (SITE-15)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, dict(RICH_FILES))
        self.config, self.identity, self.final, self.files, \
            self.copies, self.nav = load_nav(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_indexless_groups_redirect_to_first_descendant(self):
        from publishing.navigation import get_group_redirects
        redirects = get_group_redirects(self.nav, self.config)
        self.assertEqual(redirects, {
            "/en/common/labs/": "/en/common/labs/computer-architecture/",
            "/en/common/sub-topic/": "/en/common/sub-topic/foo/",
            "/en/cpp/": "/en/cpp/intro/",
            "/en/cpp/labs/": "/en/cpp/labs/first/",
            "/en/dsa/": "/en/dsa/arrays/",
            "/en/dsa/labs/": "/en/dsa/labs/sorting/",
            "/ru/common/labs/": "/ru/common/labs/computer-architecture/",
            "/ru/cpp/": "/ru/cpp/labs/assessment-1/",
            "/ru/cpp/labs/": "/ru/cpp/labs/assessment-1/",
        })

    def test_groups_with_index_get_no_redirect(self):
        from publishing.navigation import get_group_redirects
        redirects = get_group_redirects(self.nav, self.config)
        # Indexed groups serve the index lesson (no redirect).
        for key in ("/en/common/", "/en/common/guide/",
                    "/en/cpp/advanced-programming-fundamentals/",
                    "/ru/common/"):
            self.assertNotIn(key, redirects)
        # Root/locale roots are SITE-3/4, not group redirects.
        for key in ("/", "/en/", "/ru/"):
            self.assertNotIn(key, redirects)

    def test_recurse_into_first_subgroup_by_label(self):
        from types import SimpleNamespace
        from publishing.navigation import get_group_redirects
        config = SimpleNamespace(
            languages=[SimpleNamespace(code="en")],
            default_language="en")
        nav = [
            {"slug": "en/g/beta/x", "lang": "en", "title": "X",
             "source": "en/g/beta/01_x.md", "order": 1},
            {"slug": "en/g/alpha/y", "lang": "en", "title": "Y",
             "source": "en/g/alpha/01_y.md", "order": 1},
        ]
        redirects = get_group_redirects(nav, config)
        # No direct lessons under g: recurse into first subgroup by
        # label (Alpha before Beta), not by route or insertion order.
        self.assertEqual(redirects["/en/g/"], "/en/g/alpha/y/")
        self.assertEqual(redirects["/en/g/alpha/"], "/en/g/alpha/y/")
        self.assertEqual(redirects["/en/g/beta/"], "/en/g/beta/x/")

    def test_index_group_no_redirect_synthetic_nav(self):
        from types import SimpleNamespace
        from publishing.navigation import get_group_redirects
        config = SimpleNamespace(
            languages=[SimpleNamespace(code="en")],
            default_language="en")
        nav = [
            {"slug": "en/h", "lang": "en", "title": "H Index",
             "source": "en/h/index.md", "order": 0},
            {"slug": "en/h/a", "lang": "en", "title": "A",
             "source": "en/h/01_a.md", "order": 1},
        ]
        self.assertEqual(get_group_redirects(nav, config), {})

    def test_deterministic_sorted(self):
        from publishing.navigation import get_group_redirects
        first = get_group_redirects(self.nav, self.config)
        second = get_group_redirects(self.nav, self.config)
        self.assertEqual(first, second)
        self.assertEqual(list(first), sorted(first))

    def test_existing_root_redirects_unchanged(self):
        from publishing.navigation import get_group_redirects, get_redirects
        root = get_redirects(self.config, self.final)
        self.assertEqual(
            root, {"/": "/en/common/labs/computer-architecture/",
                   "/en/": "/en/common/labs/computer-architecture/",
                   "/ru/": "/ru/common/labs/computer-architecture/"})
        # No key overlap between root and group redirects.
        group = get_group_redirects(self.nav, self.config)
        self.assertFalse(set(root) & set(group))

    def test_astro_config_includes_group_redirects_with_base(self):
        from publishing.navigation import (
            build_sidebars, build_starlight_sidebar, get_group_redirects,
            get_redirects)
        from publishing.site import generate_astro_config
        per_locale = build_sidebars(self.nav, self.config)
        sidebar = build_starlight_sidebar(per_locale, self.config)
        redirects = dict(get_redirects(self.config, self.final))
        redirects.update(get_group_redirects(self.nav, self.config))
        text = generate_astro_config(
            self.config, self.identity, sidebar, redirects)
        # Group redirects use the same Astro mechanism (SITE-2 base
        # prefix) as locale roots, so Astro materializes dist redirect
        # pages for them exactly as it does for /en/ today.
        self.assertIn('"/en/cpp/": "/R/en/cpp/intro/"', text)
        self.assertIn('"/en/cpp/labs/": "/R/en/cpp/labs/first/"', text)
        self.assertIn('"/ru/cpp/": "/R/ru/cpp/labs/assessment-1/"', text)
        # No listing content is generated for those routes (SITE-10):
        # no content file exists whose route equals a redirect source.
        for key in redirects:
            if key in ("/", "/en/", "/ru/"):
                continue
            rest = key.strip("/")
            lang = rest.split("/")[0]
            self.assertNotIn(f"src/content/docs/{rest}.md", self.files)
            self.assertNotIn(f"src/content/docs/{rest}/index.md",
                             self.files)
            _ = lang


class TestPinnedVersions(unittest.TestCase):
    def test_package_json_matches_renderer_lock(self):
        from publishing.site import PINNED_VERSIONS, generate_package_json
        pkg = generate_package_json()
        for name, ver in PINNED_VERSIONS.items():
            self.assertEqual(pkg["dependencies"][name], ver)
        from pathlib import Path as _P
        renderer_pkg = json.loads(
            (_P(__file__).resolve().parent.parent
             / "renderer" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(renderer_pkg["dependencies"],
                         pkg["dependencies"])
        lock = (_P(__file__).resolve().parent.parent
                / "renderer" / "package-lock.json")
        self.assertTrue(lock.is_file(), "renderer lock missing (SITE-1)")
        data = json.loads(lock.read_text(encoding="utf-8"))
        pkgs = data.get("packages", {})
        for name, ver in PINNED_VERSIONS.items():
            key = f"node_modules/{name}"
            self.assertIn(key, pkgs)
            self.assertEqual(pkgs[key]["version"], ver)

    def test_renderer_i18n_matches_labels(self):
        from pathlib import Path as _P
        from publishing.navigation import VIEW_ON_GITHUB_LABELS
        base = _P(__file__).resolve().parent.parent / "renderer"
        for lang in ("en", "ru"):
            data = json.loads(
                (base / "src" / "content" / "i18n" / f"{lang}.json"
                 ).read_text(encoding="utf-8"))
            self.assertEqual(data["page.editLink"],
                             VIEW_ON_GITHUB_LABELS[lang])


class TestSiteBuildOp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "course"
        make_repo(self.root, dict(RICH_FILES))
        self.out = Path(self.tmp.name) / "site-out"

    def tearDown(self):
        self.tmp.cleanup()

    def _run_handler_mocked(self, argv, npm_result=(0, "mock build")):
        """Invoke the handler in-process so npm can be mocked (no network)."""
        import argparse
        from publishing.site import run_site_build
        args = argparse.Namespace(
            out=argv.get("--out"), check=argv.get("--check", False))
        with mock.patch("publishing.site.run_npm_build",
                        return_value=npm_result) as m:
            code = run_site_build(self.root, args)
            return code, m

    def test_site_build_through_shared_op_mocked(self):
        # Entirely through the shared operation: handler registered as
        # `site build` in publish.py (assert registration), invoked here
        # in-process with mocked npm for hermetic unit tests. A subprocess
        # `--check` test below proves the CLI surface without npm.
        import publish
        self.assertIn(("site", "build"), publish.COMMANDS)
        code, m = self._run_handler_mocked({"--out": str(self.out)})
        self.assertEqual(code, 0)
        self.assertEqual(m.call_count, 1)
        # Projection + renderer outputs present.
        self.assertTrue(
            (self.out / "src" / "content" / "docs" / "en" / "common"
             / "labs" / "computer-architecture.md").is_file())
        self.assertTrue((self.out / "astro.config.mjs").is_file())
        self.assertTrue((self.out / "package.json").is_file())
        self.assertTrue((self.out / "site-nav.json").is_file())
        self.assertTrue((self.out / "src" / "content.config.ts").is_file())
        self.assertTrue(
            (self.out / "src" / "content" / "i18n" / "ru.json").is_file())
        self.assertTrue((self.out / "dist").is_dir())
        # No views/presentations placeholder routes or controls.
        names = []
        for dirpath, dirnames, fns in __import__("os").walk(self.out):
            for d in dirnames:
                names.append(d.lower())
            for fn in fns:
                names.append(fn.lower())
        self.assertFalse(any(n in ("views", "presentations") for n in names))
        cfg = (self.out / "astro.config.mjs").read_text(encoding="utf-8")
        low = cfg.lower()
        self.assertNotIn("/views/", low)
        self.assertNotIn("/presentations/", low)
        nav_data = json.loads(
            (self.out / "site-nav.json").read_text(encoding="utf-8"))
        self.assertIn("en", nav_data["sidebar"])
        self.assertIn("ru", nav_data["sidebar"])
        self.assertIn("redirects", nav_data)
        # SITE-15: indexless group redirects ride along to the built
        # config (Astro materializes dist redirect pages from them).
        self.assertEqual(
            nav_data["redirects"]["/en/cpp/"], "/en/cpp/intro/")
        self.assertEqual(
            nav_data["redirects"]["/en/cpp/labs/"],
            "/en/cpp/labs/first/")
        self.assertEqual(
            nav_data["redirects"]["/ru/cpp/"],
            "/ru/cpp/labs/assessment-1/")
        cfg_text = (self.out / "astro.config.mjs").read_text(
            encoding="utf-8")
        self.assertIn('"/en/cpp/": "/R/en/cpp/intro/"', cfg_text)
        # ... and no listing content is emitted for those routes.
        docs = self.out / "src" / "content" / "docs"
        for probe in ("en/cpp.md", "en/cpp/labs.md", "ru/cpp.md",
                      "en/dsa.md", "en/common/labs.md"):
            self.assertFalse((docs / probe).is_file(),
                             f"synthetic listing emitted: {probe}")

    def test_site_check_readonly(self):
        before = {p.resolve(): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()
                  and ".git" not in p.parts}
        proc = run_publish("site", "build", "--course-repo", str(self.root),
                           "--out", str(self.out), "--check")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.out.exists())
        after = {p.resolve(): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file()
                 and ".git" not in p.parts}
        self.assertEqual(before, after)

    def test_site_out_inside_rejected(self):
        inside = self.root / "site-out"
        proc = run_publish("site", "build", "--course-repo", str(self.root),
                           "--out", str(inside))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("outside", (proc.stdout + proc.stderr).lower())

    def test_site_npm_failure_clear_error(self):
        code, _m = self._run_handler_mocked(
            {"--out": str(self.out)}, npm_result=(1, "npm boom"))
        self.assertNotEqual(code, 0)
        # Projection + config still written for inspection.
        self.assertTrue((self.out / "astro.config.mjs").is_file())


if __name__ == "__main__":
    unittest.main()
