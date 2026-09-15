#!/usr/bin/env python3
"""
Course maintenance: one script for all routine lab upkeep.

Replaces the old per-task scripts (rename_files.py, fix_files.py,
fix_links.py, convert_lists_to_headers.py). Lives outside the course repo
in ../course_maintenance so it can be shared between courses.

Usage:
    python maintain.py [options] [<file.md|dir> ...]

    Paths default to '.' (the current directory / course repo root).

    python maintain.py ru/labs/cpp/06_struct.md   # fix one file (no renames)
    python maintain.py ru/labs/cpp                # full upkeep of one lab dir
    python maintain.py --check .                  # report only, exit 1 if dirty
    python maintain.py --convert-lists file.md    # opt-in list->header step

Pipeline order (matters, do not reorder):
    1. rename    - close numbering gaps in NN_name.md files per directory
                    (old rename_files.py; runs first because it moves files).
                    Every ordered file takes its own number in sorted order;
                    a letter suffix (21a) is stripped and the file moves to
                    the next free number, so 16, 16a, 17 become 16, 17, 18.
    2. convert   - OPT-IN only (--convert-lists): turn "1. text" list items
                   into "### N. text" headers (old convert_lists_to_headers.py,
                   fixed to write back in place and to skip fenced code).
    3. headings  - H1 number := NN_ filename prefix; resequence ### N. 1..N
                   (old fix_files.py).
    4. links     - repair file/anchor links broken by the renames above
                   (old fix_links.py; runs last so it sees final names/slugs).

Rename scope: only explicitly given directories (and their subdirectories)
are considered for renames. A single file argument never triggers renames
in its parent dir. A directory is a rename candidate only if it contains at
least one ordered *.md file (NN_name.md); this keeps asset dirs such as
images/ (numbered .png files) untouched. Rename itself is non-recursive per
directory, exactly like the old script -- recursion comes from discovering
multiple candidate dirs under the given paths.

Options:
    --root DIR        repo root used for link move lookup (default: '.').
    --check           report only, write nothing; exit 1 if anything would
                      change (also covers the old rename --dry behaviour).
    --no-rename       skip the rename step.
    --no-headings     skip the headings step.
    --no-links        skip the links step.
    --convert-lists   enable the list-item -> ### header conversion step (default: off;
                      it is destructive on genuine ordered lists, so it must
                      be asked for explicitly, per file or dir).
    -q, --quiet       only print changed/broken files and the summary.

Implementation (issue #6): this file is a thin CLI shim. The pipeline
lives in the maintenance/ package (one module per responsibility) and
runs in the fixed order rename -> convert -> headings -> links via
maintenance.pipeline.run(). The future stable entry point is
publish.py; this script's observable behavior is preserved.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from maintenance.pipeline import run  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='One maintenance script for course labs: '
                    'rename + (opt-in) list conversion + headings + links.')
    ap.add_argument('paths', nargs='*', default=['.'],
                    help='markdown files or directories (default: .)')
    ap.add_argument('--root', default='.',
                    help='repo root used for move lookup (default: .)')
    ap.add_argument('--check', action='store_true',
                    help='report only, do not rewrite files (exit 1 if dirty)')
    ap.add_argument('--no-rename', action='store_true', help='skip rename step')
    ap.add_argument('--no-headings', action='store_true', help='skip headings step')
    ap.add_argument('--no-links', action='store_true', help='skip links step')
    ap.add_argument('--convert-lists', action='store_true',
                    help='enable list-item -> ### header conversion')
    ap.add_argument('-q', '--quiet', action='store_true',
                    help='only print changed/broken files and the summary')
    args = ap.parse_args(argv)

    return run(
        args.paths,
        root=Path(args.root).resolve(),
        check_only=args.check,
        quiet=args.quiet,
        no_rename=args.no_rename,
        no_headings=args.no_headings,
        no_links=args.no_links,
        convert_lists=args.convert_lists,
    )


if __name__ == '__main__':
    sys.exit(main())
