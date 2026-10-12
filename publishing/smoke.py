"""Read-only, bounded HTTP smoke probes configured by the course."""

import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit

from .config import ConfigError, load_config
from .identity import IdentityError, infer_identity
from .metadata import is_valid_slug, parse_slug_value
from .options import SmokeCheck


_HTTP_PROBE = """
import html, sys
from urllib.request import Request, urlopen
try:
    request = Request(sys.argv[1], headers={"User-Agent": "course-smoke/2.0"})
    with urlopen(request, timeout=float(sys.argv[3])) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        if sys.argv[2]:
            body = html.unescape(response.read().decode("utf-8", errors="replace"))
            if sys.argv[2] not in body:
                raise ValueError(f"missing {sys.argv[2]!r}")
except Exception as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)
"""


def _fetch(url, contains, timeout):
    # A socket timeout alone does not bound a slowly streaming response.
    # The subprocess deadline covers connection, redirects, headers and body
    # and kills a timed-out probe without leaving blocked worker threads.
    try:
        result = subprocess.run(
            [sys.executable, "-c", _HTTP_PROBE, url, contains or "", str(timeout)],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"request exceeded {timeout}s"
    except OSError as exc:
        return str(exc)
    return None if result.returncode == 0 else result.stderr.strip()


def run_smoke_check(course_repo: Path, args) -> int:
    try:
        config = load_config(course_repo)
        identity = infer_identity(course_repo, config)
        base = getattr(args, "base_url", None) or os.environ.get("BASE_URL") or identity.pages_url
        parts = urlsplit(base)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("--base-url must be an HTTP(S) URL")
        base = base.rstrip("/")
        text = (config.course_repo / config.root_lesson).read_text(encoding="utf-8")
        _, root_slug, count, _ = parse_slug_value(text)
        language = next(l.code for l in config.languages
                        if config.root_lesson.startswith(l.root + "/"))
        if count != 1 or not root_slug or not is_valid_slug(root_slug, language):
            raise ValueError(f"{config.root_lesson}: missing/invalid slug; operation: metadata generate")
        # The root redirect selects default_language; root_lesson may be a counterpart.
        root_route = "/" + config.default_language + "/" + root_slug.split("/", 1)[1] + "/"
    except (ConfigError, IdentityError, OSError, ValueError) as exc:
        print(f"error: smoke check: {exc}", file=sys.stderr)
        return 1

    def expand(value):
        return value.replace("{root_route}", root_route).replace(
            "{repository}", f"{identity.owner}/{identity.repo}")

    checks = config.smoke.checks or (
        SmokeCheck("root redirect", ("/",), "{root_route}"),
        SmokeCheck("root lesson search markup", ("{root_route}",), "pagefind"),
        SmokeCheck("search index", ("/pagefind/pagefind.js", "/_pagefind/pagefind.js")),
    )
    options = config.smoke
    passed = 0
    print(f"smoke: {base}; {len(checks)} checks; {options.retries} attempts")
    for check in checks:
        matched = False
        last_error = ""
        for attempt in range(options.retries):
            # Alternatives share one retry budget; a failed alternative is
            # not a failed check when another URL succeeds.
            for path in check.paths:
                url = base + expand(path)
                expected = expand(check.contains) if check.contains is not None else None
                error = _fetch(url, expected, options.timeout_seconds)
                if error is None:
                    matched = True
                    print(f"PASS: {check.label} ({url})")
                    break
                last_error = f"{url}: {error}"
            if matched:
                break
            print(f"attempt {attempt + 1}/{options.retries}: {check.label}: {last_error}")
            if attempt + 1 < options.retries:
                time.sleep(options.retry_delay_seconds)
        if matched:
            passed += 1
        else:
            print(f"FAIL: {check.label}: {last_error}", file=sys.stderr)
    print(f"smoke: {passed} passed, {len(checks) - passed} failed")
    return 0 if passed == len(checks) else 1
