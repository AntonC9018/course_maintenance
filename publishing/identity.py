"""Repository and site identity inference (CFG-5).

Infers GitHub repo identity, public GitHub URL, and GitHub Pages project
URL solely from the local `origin` remote configuration. Requires no
GitHub CLI or network access and never writes. The published branch is
always `master` per spec.

A missing `origin` remote (including renamed remotes, detached CI
checkouts without origin, non-git directories, or unparseable URLs) is a
validation error with an actionable message.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_FIX_ORIGIN = ("fix: run `git remote add origin "
               "<https://github.com/OWNER/REPO.git or ssh form>` "
               "inside the course repo; operation: publishing check")


class IdentityError(Exception):
    def __init__(self, message: str, *, path: str | Path | None = None,
                 hint: str = _FIX_ORIGIN):
        self.rule = "CFG-5"
        loc = str(path) if path is not None else "origin remote"
        super().__init__(f"{loc}: [CFG-5] {message}; {hint}")


@dataclass(frozen=True)
class RepoIdentity:
    owner: str
    repo: str
    github_url: str
    pages_url: str
    default_branch: str
    origin_url: str


_SCP_RE = re.compile(r"^(?P<user>[^@/:]+)@(?P<host>[^:]+):(?P<path>.+)$")
_URL_RE = re.compile(r"^(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)://(?P<rest>.*)$")
_VALID_PART = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _strip_git_suffix(p: str) -> str:
    if p.lower().endswith(".git"):
        return p[:-4]
    return p


def parse_origin_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) from a GitHub origin URL. Raises IdentityError."""
    raw = url.strip()
    if not raw:
        raise IdentityError("origin URL is empty")
    # Remove trailing slashes, then one .git suffix.
    no_slash = raw.rstrip("/")
    path_part: str | None = None
    host: str | None = None

    m = _URL_RE.match(no_slash)
    if m:
        scheme = m.group("scheme").lower()
        if scheme not in ("https", "http", "ssh", "git"):
            raise IdentityError(
                f"unsupported origin URL scheme {scheme!r} in {raw!r}; "
                f"expected an https:// or ssh (git@) GitHub URL")
        rest = m.group("rest")
        # Split userinfo@host/path.
        if "/" not in rest:
            raise IdentityError(
                f"cannot parse owner/repo from origin URL {raw!r}")
        netloc, _, path = rest.partition("/")
        if "@" in netloc:
            netloc = netloc.rsplit("@", 1)[1]
        host = netloc.split(":", 1)[0]
        path_part = path
    else:
        m2 = _SCP_RE.match(no_slash)
        if not m2:
            raise IdentityError(
                f"cannot parse origin URL {raw!r}; expected "
                f"`git@github.com:OWNER/REPO(.git)` or "
                f"`https://github.com/OWNER/REPO(.git)`")
        host = m2.group("host")
        path_part = m2.group("path")

    assert host is not None and path_part is not None
    if host.lower() != "github.com":
        raise IdentityError(
            f"origin host {host!r} is not github.com (got {raw!r}); "
            f"publishing infers identity only from GitHub origin URLs")
    path_part = _strip_git_suffix(path_part.rstrip("/"))
    segs = [s for s in path_part.split("/") if s != ""]
    if len(segs) != 2:
        raise IdentityError(
            f"cannot parse OWNER/REPO from origin URL {raw!r} "
            f"(expected exactly two path segments)")
    owner, repo = segs
    for label, val in (("owner", owner), ("repo", repo)):
        if not _VALID_PART.match(val):
            raise IdentityError(
                f"invalid {label} {val!r} in origin URL {raw!r}")
    return owner, repo


def _read_origin_url(course_repo: Path) -> str:
    """Read local origin config only (no network, no GH CLI)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(course_repo), "config", "--get",
             "remote.origin.url"],
            capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        raise IdentityError(
            f"cannot read origin remote: {e}",
            path=course_repo / ".git" / "config") from e
    if proc.returncode != 0 or not proc.stdout.strip():
        raise IdentityError(
            "missing origin remote (no `remote.origin.url` in local git "
            "config; renamed remotes such as `upstream` do not count)",
            path=course_repo / ".git" / "config")
    return proc.stdout.strip()


def infer_identity(course_repo: Path | str) -> RepoIdentity:
    """Infer identity from local origin config. Read-only."""
    repo = Path(course_repo).resolve()
    git_config = repo / ".git" / "config"
    url = _read_origin_url(repo)
    try:
        owner, name = parse_origin_url(url)
    except IdentityError as e:
        # Ensure the message carries a filesystem location.
        raise IdentityError(str(e), path=git_config) from e
    return RepoIdentity(
        owner=owner,
        repo=name,
        github_url=f"https://github.com/{owner}/{name}",
        pages_url=f"https://{owner}.github.io/{name}",
        default_branch="master",
        origin_url=url,
    )
