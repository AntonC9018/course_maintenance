"""Static Mermaid rendering (issue #12, DIAG-1..DIAG-4).

TDD seam: publishing.mermaid (pure) + projection/site integration with
mocked Playwright/Chromium toolchain (no network required). All repos live
in TemporaryDirectory; never mutates live checkouts. Stdlib-only Python;
JS deps pinned (renderer/package.json + lock).
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
        {"source": "labs/common", "destination": "common/labs"},
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


REAL_DIAGRAM_1 = """flowchart LR
A(1) --> B(2)
A --> C(3)
A --> D(4)
B --> C
C --> D
D --> A"""

REAL_DIAGRAM_2 = """flowchart LR
A(1) --> B(2)
B --> C(3)
C --> D(4)
D --> A
D <--> B"""


class TestExtraction(unittest.TestCase):
    def test_extract_single(self):
        from publishing.mermaid import extract_mermaid_blocks
        lines = ["# T", "", "```mermaid", "flowchart LR", "A-->B", "```", ""]
        blocks = extract_mermaid_blocks(lines)
        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0]["closed"])
        self.assertEqual(blocks[0]["open"], 2)
        self.assertEqual(blocks[0]["close"], 5)
        self.assertIn("flowchart LR", blocks[0]["code"])

    def test_extract_two_and_tilde(self):
        from publishing.mermaid import extract_mermaid_blocks
        lines = ["```mermaid", "graph TD", "A-->B", "```",
                 "", "~~~mermaid", "pie", 'title X', "~~~"]
        blocks = extract_mermaid_blocks(lines)
        self.assertEqual(len(blocks), 2)
        self.assertTrue(all(b["closed"] for b in blocks))

    def test_ignores_fences_inside_other_fences(self):
        from publishing.mermaid import extract_mermaid_blocks
        lines = ["```python", "```mermaid", "not a diagram", "```",
                 "```mermaid", "flowchart LR", "A-->B", "```"]
        blocks = extract_mermaid_blocks(lines)
        # First ```mermaid is inside python fence -> ignored; only real one.
        self.assertEqual(len(blocks), 1)
        self.assertIn("flowchart", blocks[0]["code"])

    def test_unclosed_reported(self):
        from publishing.mermaid import extract_mermaid_blocks
        lines = ["```mermaid", "flowchart LR", "A-->B"]
        blocks = extract_mermaid_blocks(lines)
        self.assertEqual(len(blocks), 1)
        self.assertFalse(blocks[0]["closed"])
        self.assertIsNone(blocks[0]["close"])

    def test_info_case_and_attrs(self):
        from publishing.mermaid import extract_mermaid_blocks
        lines = ["```Mermaid", "flowchart LR", "A-->B", "```"]
        blocks = extract_mermaid_blocks(lines)
        self.assertEqual(len(blocks), 1)


class TestValidation(unittest.TestCase):
    def test_real_diagrams_valid(self):
        from publishing.mermaid import validate_diagram
        validate_diagram(REAL_DIAGRAM_1, source_path="a.md")
        validate_diagram(REAL_DIAGRAM_2, source_path="a.md")

    def test_empty_rejected_with_path_and_rule(self):
        from publishing.mermaid import MermaidError
        with self.assertRaises(MermaidError) as ctx:
            from publishing.mermaid import validate_diagram
            validate_diagram("   \n  ", source_path="en/a.md")
        msg = str(ctx.exception)
        self.assertIn("en/a.md", msg)
        self.assertIn("DIAG-2", msg)

    def test_unknown_type_rejected(self):
        from publishing.mermaid import MermaidError, validate_diagram
        with self.assertRaises(MermaidError) as ctx:
            validate_diagram("not-a-diagram @@@\nA-->B",
                             source_path="en/a.md")
        msg = str(ctx.exception)
        self.assertIn("en/a.md", msg)
        self.assertIn("DIAG-2", msg)
        self.assertIn("unknown diagram type", msg.lower())

    def test_comments_skipped(self):
        from publishing.mermaid import validate_diagram
        validate_diagram("%% comment\nflowchart LR\nA-->B",
                         source_path="a.md")


class TestNormalization(unittest.TestCase):
    def test_random_ids_normalize_equal(self):
        from publishing.mermaid import normalize_svg
        a = '<svg><g id="mermaid-abc123"><a href="#mermaid-abc123">x</a></g></svg>'
        b = '<svg><g id="mermaid-xyz789"><a href="#mermaid-xyz789">x</a></g></svg>'
        self.assertEqual(normalize_svg(a), normalize_svg(b))
        self.assertIn("mermaid-static", normalize_svg(a))
        self.assertNotIn("abc123", normalize_svg(a))

    def test_uuid_and_hash_normalized(self):
        from publishing.mermaid import normalize_svg
        a = '<svg id="a-12345678-1234-1234-1234-123456789012">x deadbeef</svg>'
        n = normalize_svg(a)
        self.assertIn("uuid-static", n)
        self.assertIn("hash-static", n)

    def test_deterministic_repeatable(self):
        from publishing.mermaid import deterministic_svg
        a = deterministic_svg(REAL_DIAGRAM_1, diagram_index=0,
                              slug="en/common/labs/x")
        b = deterministic_svg(REAL_DIAGRAM_1, diagram_index=0,
                              slug="en/common/labs/x")
        self.assertEqual(a, b)
        self.assertIn("<svg", a)
        self.assertIn("flowchart", a)  # escaped source preserved


class TestRenderDiagram(unittest.TestCase):
    def test_fallback_deterministic_when_no_toolchain(self):
        from publishing.mermaid import render_diagram
        with mock.patch("publishing.mermaid.render_via_toolchain",
                        return_value=None):
            a = render_diagram(REAL_DIAGRAM_1, source_path="a.md",
                               diagram_index=0, slug="en/x")
            b = render_diagram(REAL_DIAGRAM_1, source_path="a.md",
                               diagram_index=0, slug="en/x")
            self.assertEqual(a, b)
            self.assertIn("<svg", a)

    def test_toolchain_svg_normalized(self):
        from publishing.mermaid import render_diagram
        raw = '<svg><g id="mermaid-rand999">x</g></svg>'
        with mock.patch("publishing.mermaid.render_via_toolchain",
                        return_value=raw):
            out = render_diagram(REAL_DIAGRAM_1, source_path="a.md")
            self.assertIn("mermaid-static", out)

    def test_toolchain_diagnostic_includes_path(self):
        from publishing.mermaid import MermaidError, render_diagram
        err = MermaidError("Mermaid diagram cannot render: syntax error")
        with mock.patch("publishing.mermaid.render_via_toolchain",
                        side_effect=err):
            with self.assertRaises(MermaidError) as ctx:
                render_diagram("flowchart LR\nA-->B",
                               source_path="en/bad.md", diagram_index=0)
            self.assertIn("en/bad.md", str(ctx.exception))
            self.assertIn("DIAG-2", str(ctx.exception))

    def test_invalid_diagram_never_calls_toolchain(self):
        from publishing.mermaid import MermaidError
        with mock.patch("publishing.mermaid.render_via_toolchain") as m:
            with self.assertRaises(MermaidError):
                from publishing.mermaid import render_diagram
                render_diagram("garbage @@@", source_path="a.md")
            m.assert_not_called()


class TestProcessBlocks(unittest.TestCase):
    def test_replace_with_inline_svg_and_files(self):
        from publishing.mermaid import process_mermaid_blocks
        body = ["# T", "", "```mermaid", REAL_DIAGRAM_1, "```", "",
                "text", "", "```mermaid", REAL_DIAGRAM_2, "```"]
        with mock.patch("publishing.mermaid.render_via_toolchain",
                        return_value=None):
            new_lines, svgs, errors = process_mermaid_blocks(
                body, source_path="en/a.md", slug="en/common/labs/a")
        self.assertEqual(errors, [])
        self.assertEqual(len(svgs), 2)
        text = "\n".join(new_lines)
        self.assertNotIn("```mermaid", text)
        self.assertEqual(text.count("<svg"), 2)
        self.assertIn('class="mermaid-static"', text)
        # svg files deterministic rels
        self.assertTrue(svgs[0][0].startswith("mermaid/en-common-labs-a-0"))
        self.assertTrue(svgs[1][0].endswith("-1.svg"))
        self.assertIn("<svg", svgs[0][1])

    def test_invalid_reports_path_and_rule(self):
        from publishing.mermaid import process_mermaid_blocks
        body = ["```mermaid", "not a diagram", "```"]
        new_lines, svgs, errors = process_mermaid_blocks(
            body, source_path="en/bad.md", slug="en/bad")
        self.assertTrue(errors)
        self.assertIn("en/bad.md", errors[0])
        self.assertIn("DIAG-2", errors[0])
        self.assertEqual(svgs, [])

    def test_unclosed_reports(self):
        from publishing.mermaid import process_mermaid_blocks
        body = ["```mermaid", "flowchart LR", "A-->B"]
        _n, _s, errors = process_mermaid_blocks(
            body, source_path="en/a.md", slug="en/a")
        self.assertTrue(errors)
        self.assertIn("DIAG-2", errors[0])
        self.assertIn("unclosed", errors[0].lower())

    def test_no_mermaid_passthrough(self):
        from publishing.mermaid import process_mermaid_blocks
        body = ["# T", "text"]
        new_lines, svgs, errors = process_mermaid_blocks(
            body, source_path="a.md", slug="en/a")
        self.assertEqual(new_lines, body)
        self.assertEqual(svgs, [])
        self.assertEqual(errors, [])


class TestForbiddenJs(unittest.TestCase):
    def test_detects_client_bundle(self):
        from publishing.mermaid import contains_forbidden_js
        self.assertIsNotNone(contains_forbidden_js(
            '<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js">'))
        self.assertIsNotNone(contains_forbidden_js("mermaid.initialize({});"))
        self.assertIsNotNone(contains_forbidden_js('import mermaid from "mermaid";'))

    def test_static_svg_clean(self):
        from publishing.mermaid import (contains_forbidden_js,
                                        deterministic_svg)
        svg = deterministic_svg(REAL_DIAGRAM_1, diagram_index=0, slug="en/x")
        self.assertIsNone(contains_forbidden_js(svg))
        # inline wrapper also clean
        wrapper = f'<div class="mermaid-static">{svg}</div>'
        self.assertIsNone(contains_forbidden_js(wrapper))

    def test_check_out_dir(self):
        from publishing.mermaid import check_no_mermaid_client_js
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "good.html").write_text("<svg></svg>", encoding="utf-8")
            self.assertEqual(check_no_mermaid_client_js(root), [])
            (root / "bad.html").write_text(
                '<script src="mermaid.min.js"></script>', encoding="utf-8")
            problems = check_no_mermaid_client_js(root)
            self.assertTrue(problems)
            self.assertIn("DIAG-3", problems[0])


class TestPinnedVersions(unittest.TestCase):
    def test_pins_include_mermaid_playwright_chromium(self):
        from publishing.site import PINNED_BROWSERS, PINNED_VERSIONS
        for name in ("astro", "@astrojs/starlight", "remark-math",
                     "rehype-katex", "katex", "mermaid", "playwright"):
            self.assertIn(name, PINNED_VERSIONS,
                          f"missing pin for {name}")
        self.assertEqual(PINNED_VERSIONS["astro"], "7.3.2")
        self.assertEqual(PINNED_VERSIONS["@astrojs/starlight"], "0.42.1")
        self.assertEqual(PINNED_VERSIONS["remark-math"], "6.0.0")
        self.assertEqual(PINNED_VERSIONS["rehype-katex"], "7.0.1")
        self.assertEqual(PINNED_VERSIONS["katex"], "0.16.47")
        # Chromium browser pin (Playwright-bundled) documented separately.
        self.assertIn("chromium", PINNED_BROWSERS)

    def test_package_json_matches_renderer(self):
        import json as _json
        from pathlib import Path as _P
        from publishing.site import PINNED_VERSIONS, generate_package_json
        pkg = generate_package_json()
        for name, ver in PINNED_VERSIONS.items():
            # Chromium is a browser pin, not an npm dep.
            if name == "chromium":
                continue
            self.assertEqual(pkg["dependencies"][name], ver)
        renderer_pkg = _json.loads(
            (_P(__file__).resolve().parent.parent
             / "renderer" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(renderer_pkg["dependencies"],
                         pkg["dependencies"])


if __name__ == "__main__":
    unittest.main()
