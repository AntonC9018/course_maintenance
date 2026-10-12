"""Course policy exercises real selectors/HTTP and read-only API verification."""

import argparse
import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import time
from threading import Thread
import unittest
from unittest.mock import patch

from publishing.config import ConfigError, load_config
from publishing.ci import run_ci, run_ci_prepare, run_maintain_check
from publishing.identity import infer_identity
from publishing.pages import run_pages_verify
from publishing.smoke import run_smoke_check
from tests.helpers import write
from tests.test_ci import MIN_CONFIG, init_repo_with_origin, snapshot


class TestCourseOptions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "course"
        init_repo_with_origin(self.root)
        self.config = copy.deepcopy(MIN_CONFIG)
        self.config.update({
            "default_language": "ru", "languages": [{"code": "ru", "root": "labs", "label": "Русский"}],
            "site_title": {"ru": "Курс"}, "root_lesson": "labs/01_start.md",
            "route_sections": [], "ci": {"run_compatibility_tests": False},
        })
        write(self.root / "labs/01_start.md", "---\nslug: ru/labs/start\n---\n# 1. Start\n")
        write(self.root / "course_maintenance/README.md", "[broken](missing.md)\n")
        self.save()

    def save(self):
        write(self.root / "course-publishing.json", json.dumps(self.config, ensure_ascii=False))

    def test_labs_selected_from_config_and_shared_docs_excluded(self):
        # A real numbering gap under labs must make CI red; a broken
        # tooling README must not make the clean course red.
        self.assertEqual(run_maintain_check(self.root), 0)
        write(self.root / "labs/03_gap.md", "# 3. Gap\n")
        before = snapshot(self.root)
        with patch("publishing.ci.run_compat_suite") as compatibility, \
                patch("publishing.ci.run_site_build_stage") as site:
            self.assertEqual(run_ci(self.root, argparse.Namespace(out=None)), 1)
            compatibility.assert_not_called()
            site.assert_not_called()
        self.assertEqual(snapshot(self.root), before)

    def test_compatibility_disabled_but_publishing_and_build_retained(self):
        with patch("publishing.ci.run_maintain_check", return_value=0), \
                patch("publishing.ci.run_publishing_check_stage", return_value=0) as publishing, \
                patch("publishing.ci.run_site_build_stage", return_value=0) as build, \
                patch("publishing.ci.run_compat_suite") as compatibility:
            self.assertEqual(run_ci(self.root, argparse.Namespace(out=None)), 0)
            publishing.assert_called_once()
            build.assert_called_once()
            compatibility.assert_not_called()

    def test_heading_numbering_policy_used_by_ci_and_maintenance_cli(self):
        from tests.helpers import run_maintain
        text = "---\nslug: ru/labs/start\n---\n# 1. Start\n## One\n### 1. First\n## Two\n### 2. Second\n"
        write(self.root / "labs/01_start.md", text)
        for policy, expected in (("document", 0), ("section", 1)):
            with self.subTest(policy=policy):
                self.config["maintenance"] = {"heading_numbering": policy}
                self.save()
                self.assertEqual(run_maintain_check(self.root), expected)
                result = run_maintain("--root", str(self.root), "--check", str(self.root / "labs"))
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertEqual((self.root / "labs/01_start.md").read_text(), text)

    def test_explicit_paths_fail_closed(self):
        for paths in (["missing"], ["../course"], ["course_maintenance"], ["."], [], ["placeholder.txt"]):
            with self.subTest(paths=paths):
                self.config["ci"]["maintenance_paths"] = paths
                self.save()
                with self.assertRaises(ConfigError):
                    load_config(self.root)

    def test_nested_options_are_strict(self):
        for field, value in (("ci", {"run_compatibility_tests": "false"}),
                             ("smoke", {"retries": 0}),
                             ("smoke", {"checks": [{"label": "x", "paths": ["https://elsewhere"]}]}),
                             ("deployment", {"pages_url": "https://user:password@host/"}),
                             ("navigation", {"group_labels": {"labs": {"unknown": "x"}}}),
                             ("ci", {"unknown_option": True})):
            with self.subTest(field=field, value=value):
                original = copy.deepcopy(self.config)
                self.config[field] = value
                self.save()
                with self.assertRaises(ConfigError):
                    load_config(self.root)
                self.config = original

    def test_custom_pages_url_and_branch_used_by_renderer(self):
        from publishing.site import astro_base, astro_site, edit_link_base
        self.config["deployment"] = {"branch": "main", "pages_url": "https://course.example/teaching"}
        self.save()
        identity = infer_identity(self.root, load_config(self.root))
        self.assertEqual(astro_site(identity), "https://course.example")
        self.assertEqual(astro_base(identity), "/teaching/")
        self.assertIn("/blob/main/", edit_link_base(identity))

    def test_configured_pr_label_checked_before_dependency_setup(self):
        self.config["ci"]["required_pr_label"] = "ready-to-check"
        self.save()
        event = self.root / "event.json"
        write(event, json.dumps({"pull_request": {"labels": []}}))
        with patch.dict("os.environ", {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": str(event)}):
            self.assertEqual(run_ci_prepare(self.root, argparse.Namespace()), 1)
            write(event, json.dumps({"pull_request": {"labels": [{"name": "ready-to-check"}]}}))
            self.assertEqual(run_ci_prepare(self.root, argparse.Namespace()), 0)

    def test_configured_backlink_label_used_by_generation_and_validation(self):
        from tests.helpers import run_publish
        self.config["backlink_labels"] = {"ru": "Открыть урок на сайте"}
        self.save()
        result = run_publish("metadata", "generate", "--course-repo", str(self.root))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (self.root / self.config["root_lesson"]).read_text()
        self.assertIn("[Открыть урок на сайте]", text)
        result = run_publish("publishing", "check", "--course-repo", str(self.root))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generic_navigation_and_slug_override(self):
        from publishing.metadata import expected_slug_for
        from publishing.navigation import build_lab_sequences, build_sidebars, get_redirects, is_lab_slug
        self.config["navigation"] = {
            "group_labels": {"workshop": {"ru": "Практика"}},
            "lab_prefixes": ["workshop"], "last_lessons": ["workshop/final"],
        }
        self.config["slug_overrides"] = {"exam.md": "workshop/final"}
        self.save()
        cfg = load_config(self.root)
        nav = [{"slug": "ru/workshop/final", "lang": "ru", "title": "Final", "order": 0},
               {"slug": "ru/workshop/intro", "lang": "ru", "title": "Intro", "order": 1}]
        self.assertTrue(is_lab_slug("ru/workshop/intro", cfg))
        self.assertEqual(build_lab_sequences(nav, cfg)["ru"], ["ru/workshop/intro", "ru/workshop/final"])
        self.assertEqual(build_sidebars(nav, cfg)["ru"][0]["label"], "Практика")
        self.assertEqual(expected_slug_for("exam.md", "ru", [], False, cfg.slug_overrides), "ru/workshop/final")
        with self.assertRaisesRegex(ValueError, "missing root lesson slug"):
            get_redirects(cfg, {})

    def test_smoke_real_http_fallback_and_failure(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = {"/course/": "/ru/labs/start/", "/course/ru/labs/start/": "pagefind",
                        "/course/_pagefind/pagefind.js": "search"}.get(self.path)
                self.send_response(200 if body is not None else 404)
                self.end_headers()
                self.wfile.write((body or "missing").encode())

            def log_message(self, *args):
                pass

        self.config["smoke"] = {"retries": 1, "retry_delay_seconds": 0, "timeout_seconds": 2}
        self.save()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            args = argparse.Namespace(base_url=f"http://127.0.0.1:{server.server_port}/course")
            self.assertEqual(run_smoke_check(self.root, args), 0)
            self.config["smoke"]["checks"] = [{"label": "missing SVG", "paths": ["/missing"], "contains": "<svg"}]
            self.save()
            self.assertEqual(run_smoke_check(self.root, args), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_pages_verification_reads_exact_nested_fields(self):
        self.config["deployment"] = {"branch": "main", "required_status_checks": ["validate"]}
        self.save()
        pages = {"build_type": "workflow", "html_url": "https://O.github.io/R/"}
        protection = {"required_status_checks": {"checks": [{"context": "validate"}]},
                      "enforce_admins": {"enabled": True}, "another_setting": {"enabled": False}}
        with patch("publishing.pages._github_json", side_effect=[pages, protection]) as api:
            self.assertEqual(run_pages_verify(self.root, argparse.Namespace(strict=True)), 1)

            self.assertIn("branches/main/protection", api.call_args.args[0])
        protection["enforce_admins"]["enabled"] = False
        with patch("publishing.pages._github_json", side_effect=[pages, protection]):
            self.assertEqual(run_pages_verify(self.root, argparse.Namespace(strict=True)), 0)
        with patch("publishing.pages._github_json", side_effect=OSError("offline")):
            self.assertEqual(run_pages_verify(self.root, argparse.Namespace(strict=False)), 0)
            self.assertEqual(run_pages_verify(self.root, argparse.Namespace(strict=True)), 1)

    def test_smoke_timeout_bounds_slowly_streaming_response(self):
        from publishing.smoke import _fetch

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(20):
                        self.wfile.write(b"x")
                        self.wfile.flush()
                        time.sleep(0.2)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            started = time.monotonic()
            error = _fetch(f"http://127.0.0.1:{server.server_port}/", "expected", 1)
            self.assertIn("exceeded 1s", error)
            self.assertLess(time.monotonic() - started, 2.5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
