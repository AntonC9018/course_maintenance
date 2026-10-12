"""Read-only verification of configured GitHub Pages/protection expectations."""

import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote, urlsplit

from .config import ConfigError, load_config
from .identity import IdentityError, infer_identity


def _github_json(endpoint):
    result = subprocess.run(["gh", "api", endpoint], capture_output=True,
                            text=True, timeout=30)
    if result.returncode:
        raise OSError(f"cannot read GitHub API {endpoint}")
    return json.loads(result.stdout)


def _normalized_url(value):
    parts = urlsplit(value)
    return parts.scheme, parts.netloc.casefold(), parts.path.rstrip("/")


def run_pages_verify(course_repo: Path, args) -> int:
    try:
        config = load_config(course_repo)
        identity = infer_identity(course_repo, config)
    except (ConfigError, IdentityError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    expected = config.deployment
    repository = f"{identity.owner}/{identity.repo}"
    strict = getattr(args, "strict", False)
    failed = False

    def check(label, actual, want):
        nonlocal failed
        if actual == want:
            print(f"PASS: {label}")
        else:
            print(f"FAIL: {label}: expected {want!r}, got {actual!r}")
            failed = True

    def unavailable(exc):
        nonlocal failed
        print(f"SKIP: {exc}; verify repository settings manually")
        failed = failed or strict

    print(f"pages verify: {repository}; branch {expected.branch}; URL {identity.pages_url}")
    try:
        pages = _github_json(f"repos/{repository}/pages")
        check("Pages source is GitHub Actions", pages.get("build_type"), "workflow")
        check("Pages URL", _normalized_url(pages.get("html_url") or ""),
              _normalized_url(identity.pages_url))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        unavailable(exc)
    try:
        protection = _github_json(f"repos/{repository}/branches/{quote(expected.branch, safe='')}/protection")
        status = protection.get("required_status_checks") or {}
        contexts = set(status.get("contexts") or [])
        contexts.update(item["context"] for item in (status.get("checks") or []))
        for context in expected.required_status_checks:
            check(f"required status {context}", context in contexts, True)
        check("pull requests required", bool(protection.get("required_pull_request_reviews")),
              expected.require_pull_requests)
        check("protection enforced for admins", (protection.get("enforce_admins") or {}).get("enabled", False),
              expected.enforce_admins)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        unavailable(exc)
    return 1 if failed else 0
