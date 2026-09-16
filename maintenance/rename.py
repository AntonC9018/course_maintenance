"""Step 1: rename (old rename_files.py, non-recursive per directory).

Extracted verbatim from maintain.py: closes numbering gaps in NN_name.md
files per directory. Every ordered file takes its own number in sorted
order; a letter suffix is stripped and the file moves to the next free
number (16_foo, 16a_bar, 17_baz -> 16_foo, 17_bar, 18_baz).
"""

import os
from pathlib import Path

from .patterns import ORDERED_PATTERN


def parse_ordered(name: str):
    """Return (n1, letter, n2, rest, suffix) or None if not ordered.

    letter is e.g. 'a' for 21a_function_execution.md, else None.
    """
    stem = Path(name).stem
    suffix = Path(name).suffix
    m = ORDERED_PATTERN.match(stem)
    if not m:
        return None
    n1 = int(m.group(1))
    letter = m.group(2)
    n2 = int(m.group(3)) if m.group(3) is not None else None
    return n1, letter, n2, m.group(4), suffix


def order_key(entry):
    n1, letter, n2, *_ = entry[1]
    # plain files sort before their lettered appendices: (21,'') < (21,'a')
    return (n1, letter or '', n2 if n2 is not None else -1)


def plan_renames(directory: Path):
    """Return (operations, errors).

    operations: list of (src, dst) Path pairs. errors: list of str.
    Faithful to rename_files.py: duplicate (n1, letter, n2) aborts the
    directory, >99 ordered files aborts, 2-digit zero padding. Only *.md
    files are considered (keeps asset dirs untouched even if discovered).
    Every ordered file consumes its own number in sorted order; a letter
    suffix is stripped, so 16_foo, 16a_bar, 17_baz become 16_foo, 17_bar,
    18_baz.
    """
    files = sorted(
        (f for f in directory.iterdir()
         if f.is_file() and f.suffix.lower() == '.md'),
        key=lambda f: f.name,
    )
    matched = [(f, parsed) for f in files
               if (parsed := parse_ordered(f.name)) is not None]
    if not matched:
        return [], []

    seen: dict = {}
    duplicates = []
    for f, (n1, letter, n2, _rest, _suffix) in matched:
        key = (n1, letter or '', n2)
        if key in seen:
            duplicates.append((key, seen[key], f))
        else:
            seen[key] = f
    if duplicates:
        errors = ['Duplicate numbering detected -- aborting, no files renamed.']
        for key, first, second in duplicates:
            n1, letter, n2 = key
            label = f'{n1}{letter}' + (f'_{n2}' if n2 is not None else '')
            errors.append(f'  [{label}]  {first.name}  <->  {second.name}')
        return [], errors

    matched.sort(key=order_key)

    if len(matched) > 99:
        return [], [f'{len(matched)} files found -- 2-digit padding supports up to 99.']

    ops = []
    current = 0  # number assigned to the latest file; every ordered file,
    # lettered or not, consumes its own number and the letter is stripped
    for f, (_n1, _letter, _n2, rest, suffix) in matched:
        current += 1
        new_name = f'{str(current).zfill(2)}_{rest}{suffix}'
        if f.name != new_name:
            ops.append((f, directory / new_name))
    return ops, []


def run_rename_on_dirs(directories: list, check_only: bool, quiet: bool):
    """Rename ordered files in each directory. Returns (renamed, errors)."""
    renamed = 0
    errors: list = []
    for d in sorted(directories):
        ops, dir_errors = plan_renames(d)
        if dir_errors:
            print(f'ERROR {d}:')
            for e in dir_errors:
                print(e)
            errors.extend([f'{d}: {e}' for e in dir_errors])
            continue
        if not ops:
            if not quiet:
                print(f'OK      {d}  (numbering already sequential)')
            continue
        for src, dst in ops:
            print(f'  {"WOULD-RENAME" if check_only else "RENAME"}  '
                  f'{src.name} -> {dst.name}')
        if not check_only:
            # two-phase commit via temp names so shifts (e.g. 00_ -> 01_)
            # can never collide with a file still waiting to move.
            tmp_moves = []
            for i, (src, dst) in enumerate(ops):
                tmp = src.parent / f'.maintain-tmp-{i}{src.suffix}'
                src.rename(tmp)
                tmp_moves.append((tmp, dst))
            for tmp, dst in tmp_moves:
                tmp.rename(dst)
        renamed += len(ops)
        print(f'{"WOULD-RENAME" if check_only else "RENAMED"} '
              f'{len(ops)} file(s) in {d}')
    return renamed, errors


def discover_rename_dirs(explicit_dirs: list) -> list:
    """Find rename candidates under explicitly given dirs.

    A dir qualifies if it directly contains >=1 ordered *.md file.
    Skips .git and hidden directories.
    """
    skip = {"node_modules", ".astro", "dist", ".venv", "__pycache__"}
    found: set = set()
    for top in explicit_dirs:
        top = top.resolve()
        if not top.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [x for x in dirnames
                           if x != '.git' and not x.startswith('.')
                           and x not in skip]
            if '.git' in Path(dirpath).parts:
                continue
            if any(part in skip for part in Path(dirpath).parts):
                continue
            d = Path(dirpath)
            if any(parse_ordered(fn) is not None and fn.lower().endswith('.md')
                   for fn in filenames):
                found.add(d)
    return sorted(found)
