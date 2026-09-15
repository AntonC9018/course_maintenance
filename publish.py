#!/usr/bin/env python3
"""Stable top-level command dispatcher for course maintenance (issue #6).

Usage:
    python3 <course_maintenance>/publish.py <responsibility> <operation> \\
        --course-repo <course_repository>
    python3 <course_maintenance>/publish.py ci --course-repo <course_repository>

Responsibilities (spec "Required operations"; issues #7-15 own the logic):

    metadata generate   add missing lesson slugs and refresh backlinks (#7-8)
    publishing check    validate config/content/metadata/links/assets (#9)
    projection build    disposable web projection without compiling (#10-11)
    site build          projection + renderer toolchain + dist/ (#12-13)
    ci                  shared CI entry point (#14)

Issue #6 ships the dispatcher only: the four operations above (and `ci`)
are registered stubs returning a clear "not yet implemented" error with a
nonzero exit code. Follow-up tickets add a module (e.g. under
maintenance/ or a new package) implementing
``handler(course_repo: Path, args: Namespace) -> int`` and register it
with one :func:`register` line below -- no logic goes back into this file
or any other monolith.

Exit codes: 0 success, 1 check/validation dirty, 2 usage error
(incl. unknown command, bad --course-repo, not yet implemented).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FOLLOW_UP_ISSUES = {
    ("metadata", "generate"): "#7/#8",
    ("publishing", "check"): "#9",
    ("projection", "build"): "#10/#11",
    ("site", "build"): "#12/#13",
    ("ci", None): "#14",
}

COMMANDS: dict = {}


def register(responsibility, operation, handler, help_text=""):
    """Register a (responsibility, operation) handler.

    handler(course_repo: Path, args) -> int. Overwrites any stub with
    the same key so follow-up tickets plug in real logic with one call.
    """
    COMMANDS[(responsibility, operation)] = (handler, help_text)


def unregister(responsibility, operation):
    """Remove a handler (mainly for tests). Returns True if one existed."""
    return COMMANDS.pop((responsibility, operation), None) is not None


def _not_yet_implemented(responsibility, operation):
    ticket = FOLLOW_UP_ISSUES.get((responsibility, operation), "a follow-up issue")

    def handler(course_repo, args):
        label = (
            responsibility if operation is None
            else f"{responsibility} {operation}"
        )
        print(
            f"error: '{label}' is not yet implemented "
            f"(see issue {ticket}); course repo: {course_repo}",
            file=sys.stderr,
        )
        return 2

    return handler


register("metadata", "generate",
         _not_yet_implemented("metadata", "generate"),
         "add missing lesson slugs and refresh marked source backlinks")
register("publishing", "check",
         _not_yet_implemented("publishing", "check"),
         "validate configuration, content, metadata, links and assets")
register("projection", "build",
         _not_yet_implemented("projection", "build"),
         "create a deterministic disposable web projection")
register("site", "build",
         _not_yet_implemented("site", "build"),
         "build the projection and produce dist/ via the renderer")
register("ci", None,
         _not_yet_implemented("ci", None),
         "shared CI entry point (checks + compatibility suite + site build)")


def build_parser():
    ap = argparse.ArgumentParser(
        description="Course maintenance dispatcher: "
                    "<responsibility> <operation> --course-repo <repo>")
    ap.add_argument("responsibility", nargs="?",
                    help="metadata | publishing | projection | site | ci")
    ap.add_argument("operation", nargs="?",
                    help="generate | check | build (omit for ci)")
    ap.add_argument("--course-repo", default=".",
                    help="explicit path to the course-repository root "
                         "(default: .)")
    return ap


def dispatch(argv=None) -> int:
    """Parse argv, validate --course-repo, run the handler. Returns exit code."""
    args, _unknown = build_parser().parse_known_args(argv)
    if not args.responsibility:
        build_parser().print_usage(sys.stderr)
        print("error: expected <responsibility> <operation> "
              "(e.g. 'metadata generate') or 'ci'", file=sys.stderr)
        return 2

    if args.responsibility == "ci" and args.operation is None:
        key = ("ci", None)
    elif args.operation is None:
        build_parser().print_usage(sys.stderr)
        print(f"error: unknown command '{args.responsibility}'; "
              f"expected '<responsibility> <operation>' or 'ci'",
              file=sys.stderr)
        return 2
    else:
        key = (args.responsibility, args.operation)

    if key not in COMMANDS:
        build_parser().print_usage(sys.stderr)
        if key[1] is None:
            print(f"error: unknown command '{key[0]}'", file=sys.stderr)
        else:
            print(f"error: unknown command '{key[0]} {key[1]}'",
                  file=sys.stderr)
        known = sorted(
            r if o is None else f"{r} {o}" for r, o in COMMANDS
        )
        print(f"known commands: {', '.join(known)}", file=sys.stderr)
        return 2

    course_repo = Path(args.course_repo)
    if not course_repo.is_absolute():
        course_repo = (Path.cwd() / course_repo).resolve()
    else:
        course_repo = course_repo.resolve()
    if not course_repo.is_dir():
        print(f"error: course repo not found or not a directory: "
              f"{args.course_repo}", file=sys.stderr)
        return 2

    handler, _help = COMMANDS[key]
    return handler(course_repo, args)


def main(argv=None) -> int:
    return dispatch(argv)


if __name__ == "__main__":
    sys.exit(main())
