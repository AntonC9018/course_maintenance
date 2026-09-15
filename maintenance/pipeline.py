"""Pipeline orchestration: fixed order rename -> convert -> headings -> links.

The order matters and must be preserved (AGENTS.md): renames move files
first, headings are fixed second, and the link index is built last inside
:func:`maintenance.links.run_links` so it sees final names and slugs.
After renames the markdown file list is re-collected for the same reason.
"""

from pathlib import Path

from .convert import run_convert
from .headings import run_headings
from .links import run_links
from .rename import discover_rename_dirs, run_rename_on_dirs


def collect_markdown(paths: list) -> list:
    files = []
    for p in paths:
        p = Path(p)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if p.is_dir():
            files.extend(sorted(p.rglob('*.md')))
        elif p.is_file():
            files.append(p)
    return [f for f in files if '.git' not in f.parts and f.suffix.lower() == '.md']


def collect_explicit_dirs(paths: list) -> list:
    dirs = []
    for p in paths:
        q = Path(p)
        if not q.is_absolute():
            q = (Path.cwd() / q).resolve()
        if q.is_dir():
            dirs.append(q)
    return dirs


def run(paths, *, root: Path, check_only: bool, quiet: bool,
        no_rename: bool = False, no_headings: bool = False,
        no_links: bool = False, convert_lists: bool = False) -> int:
    """Run the maintenance pipeline. Returns the process exit code.

    Exit codes: 0 clean/success, 1 dirty in --check mode or rename errors.
    """
    md_files = collect_markdown(paths)
    if not md_files and not no_rename:
        # rename-only run on a dir without .md directly? re-check below
        pass

    rename_count = 0
    rename_errors: list = []
    if not no_rename:
        explicit_dirs = collect_explicit_dirs(paths)
        rename_dirs = discover_rename_dirs(explicit_dirs)
        print(f'--- rename ({len(rename_dirs)} dir(s)) ---')
        rename_count, rename_errors = run_rename_on_dirs(
            rename_dirs, check_only, quiet)
        # renames moved files: re-collect so later steps see final names
        md_files = collect_markdown(paths)
    else:
        print('--- rename (skipped) ---')

    if convert_lists:
        print(f'--- convert lists ({len(md_files)} file(s)) ---')
        convert_count = run_convert(md_files, check_only, quiet)
    else:
        print('--- convert lists (skipped, use --convert-lists to enable) ---')
        convert_count = 0

    if not no_headings:
        print(f'--- headings ({len(md_files)} file(s)) ---')
        headings_count = run_headings(md_files, check_only, quiet)
    else:
        print('--- headings (skipped) ---')
        headings_count = 0

    if not no_links:
        print(f'--- links ({len(md_files)} file(s)) ---')
        links_fixed, links_broken = run_links(md_files, root, check_only, quiet)
    else:
        print('--- links (skipped) ---')
        links_fixed, links_broken = 0, 0

    mode = '[CHECK] ' if check_only else ''
    print(f'\n{mode}rename: {rename_count} file(s), '
          f'convert: {convert_count} file(s), '
          f'headings: {headings_count} file(s), '
          f'links: {links_fixed} fixed / {links_broken} broken '
          f'in {len(md_files)} markdown file(s).')
    if rename_errors:
        print(f'{len(rename_errors)} rename error(s).')
    if check_only and (rename_count or convert_count or headings_count
                       or links_fixed or links_broken or rename_errors):
        return 1
    if rename_errors:
        return 1
    return 0
