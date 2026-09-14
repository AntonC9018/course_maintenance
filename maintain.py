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
                   Lettered appendices (21a) follow their parent's number,
                   so 21a always stays right after 21.
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
    --convert-lists   enable the list->header conversion step (default: off;
                      it is destructive on genuine ordered lists, so it must
                      be asked for explicitly, per file or dir).
    -q, --quiet       only print changed/broken files and the summary.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Shared patterns
# --------------------------------------------------------------------------

# Ordered lab file: NN_rest, NN_MM_rest, or NN<letter>_rest (stem),
# e.g. 01_instruction, 21a_function_execution. A letter-suffixed file is an
# appendix to its number and is always kept glued right after it through
# renames (21_oop -> 20_oop pulls 21a_func -> 20a_func along).
ORDERED_PATTERN = re.compile(r'^(\d+)([a-z])?(?:_(\d+))?_(.+)$')
H1_RE = re.compile(r'^(#\s+)(\d+)(\.\s+.+)')
H3_RE = re.compile(r'^(###\s+)(\d+)(\.\s+.+)')
LIST_ITEM_RE = re.compile(r'^(\d+)[.)]\s*(.*)')
FENCE_RE = re.compile(r'^\s*(```|~~~)')
LINK_RE = re.compile(r'(!?\[[^\]]*\]\()([^)\s]+)(\s+[^)]*)?(\))')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
NUM_PREFIX_RE = re.compile(r'^\d+-')

EXTERNAL_PREFIXES = ('http://', 'https://', 'mailto:', '//', 'data:', 'ftp://')


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


# --------------------------------------------------------------------------
# Step 1: rename (old rename_files.py, non-recursive per directory)
# --------------------------------------------------------------------------

def plan_renames(directory: Path):
    """Return (operations, errors).

    operations: list of (src, dst) Path pairs. errors: list of str.
    Faithful to rename_files.py: duplicate (n1, letter, n2) aborts the
    directory, >99 ordered files aborts, 2-digit zero padding. Only *.md
    files are considered (keeps asset dirs untouched even if discovered).
    Lettered files (21a) take no number of their own: they follow their
    parent's new number, so 21a always stays right after 21.
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
    current = 0  # number assigned to the latest plain file
    for f, (_n1, letter, _n2, rest, suffix) in matched:
        if letter:
            if current == 0:
                current = 1  # leading appendix with no parent yet: anchor at 1
            new_name = f'{str(current).zfill(2)}{letter}_{rest}{suffix}'
        else:
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
    found: set = set()
    for top in explicit_dirs:
        top = top.resolve()
        if not top.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [x for x in dirnames
                           if x != '.git' and not x.startswith('.')]
            if '.git' in Path(dirpath).parts:
                continue
            d = Path(dirpath)
            if any(parse_ordered(fn) is not None and fn.lower().endswith('.md')
                   for fn in filenames):
                found.add(d)
    return sorted(found)


# --------------------------------------------------------------------------
# Step 2: convert numbered lists to ### headers (opt-in, fixed)
# --------------------------------------------------------------------------

def convert_lists_to_headers(text: str) -> str:
    """Turn "1. text" list items into "### N. text" headers.

    Same numbering rule as the old script (fresh 1..N counter per file),
    but skips fenced code blocks so code examples are never rewritten.
    """
    lines = text.split('\n')
    result = []
    counter = 0
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            in_fence = not in_fence
            result.append(line)
            continue
        if in_fence:
            result.append(line)
            continue
        m = LIST_ITEM_RE.match(line)
        if m:
            counter += 1
            rest = m.group(2).strip()
            if not rest:
                result.append(f'### {counter}.')
            elif rest.startswith('```'):
                result.append(f'### {counter}.')
                result.append(rest)
            else:
                result.append(f'### {counter}. {rest}')
        else:
            result.append(line)
    return '\n'.join(result)


def run_convert(files: list, check_only: bool, quiet: bool):
    """Apply list->header conversion. Returns number of files changed."""
    changed = 0
    for path in files:
        original = path.read_text(encoding='utf-8')
        converted = convert_lists_to_headers(original)
        if converted == original:
            if not quiet:
                print(f'OK      {path}  (no list items)')
            continue
        changed += 1
        if check_only:
            print(f'WOULD-CONVERT {path}')
        else:
            # fixed: old script wrote to Path(path.name), i.e. the cwd
            path.write_text(converted, encoding='utf-8')
            print(f'CONVERTED {path}')
    return changed


# --------------------------------------------------------------------------
# Step 3: headings (old fix_files.py)
# --------------------------------------------------------------------------

def fix_headings_in_text(text: str, h1_number):
    """Apply H1/H3 fixes. Returns (new_text, h1_msgs, h3_msgs, h3_count)."""
    lines = text.splitlines(keepends=True)
    h3_counter = 0
    h1_fixed = h1_number is None  # no H1 expectation if filename unnumbered
    h1_msgs: list = []
    h3_msgs: list = []
    result = []
    for line in lines:
        h1_match = H1_RE.match(line)
        if h1_match and not h1_fixed:
            old_num = int(h1_match.group(2))
            if old_num != h1_number:
                line = f'{h1_match.group(1)}{h1_number}{h1_match.group(3)}\n'
                h1_msgs.append(f'H1 : {old_num} -> {h1_number}')
            h1_fixed = True
            result.append(line)
            continue
        h3_match = H3_RE.match(line)
        if h3_match:
            h3_counter += 1
            old_num = int(h3_match.group(2))
            if old_num != h3_counter:
                line = f'{h3_match.group(1)}{h3_counter}{h3_match.group(3)}\n'
                h3_msgs.append(f'H3 : {old_num} -> {h3_counter}')
            result.append(line)
            continue
        result.append(line)
    return ''.join(result), h1_msgs, h3_msgs, h3_counter


def run_headings(files: list, check_only: bool, quiet: bool):
    """Fix H1/H3 headings. Returns number of files changed."""
    changed = 0
    for path in files:
        m = re.match(r'^(\d+)_', path.name)
        h1_number = int(m.group(1)) if m else None
        original = path.read_text(encoding='utf-8')
        new_text, h1_msgs, h3_msgs, h3_count = fix_headings_in_text(
            original, h1_number)
        if new_text == original:
            if not quiet:
                print(f'OK      {path.name}  '
                      f'(no changes needed, H1={h1_number}, H3 headings={h3_count})')
            continue
        changed += 1
        for msg in h1_msgs + h3_msgs:
            print(f'  {msg}')
        if check_only:
            print(f'WOULD-FIX {path.name}  (H1={h1_number}, H3 headings={h3_count})')
        else:
            path.write_text(new_text, encoding='utf-8')
            print(f'FIXED {path.name}  (H1={h1_number}, H3 headings={h3_count})')
    return changed


# --------------------------------------------------------------------------
# Step 4: links (old fix_links.py, verbatim logic)
# --------------------------------------------------------------------------

def split_rest(name: str) -> str:
    """Stable part of a file/dir name: '01_instruction.md' -> 'instruction.md'.

    Letter suffixes are stripped too: '21a_function_execution.md' ->
    'function_execution.md', so appendix files are matched by topic, not number.
    """
    stem, dot, suffix = (name.partition('.') if '.' in name and not name.startswith('.')
                         else (name, '', ''))
    m = ORDERED_PATTERN.match(stem)
    if not m:
        return name
    return m.group(4) + (('.' + suffix) if dot else '')


def strip_parts_for_match(rel_posix: str):
    return [split_rest(p) for p in rel_posix.split('/') if p not in ('', '.', '..')]


def github_slug(heading_text: str) -> str:
    text = heading_text.strip().lower()
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = text.replace('`', '')
    text = re.sub(r'[^\w\s\-]', '', text, flags=re.UNICODE)
    text = re.sub(r'\s+', '-', text.strip())
    text = re.sub(r'-{2,}', '-', text)
    return text.strip('-')


def strip_numeric_prefix(slug: str) -> str:
    return NUM_PREFIX_RE.sub('', slug)


def is_external(target_path: str) -> bool:
    return target_path.lower().startswith(EXTERNAL_PREFIXES)


def inline_code_spans(line: str):
    return [(m.start(), m.end()) for m in re.finditer(r'`[^`]*`', line)]


def inside_spans(pos: int, spans) -> bool:
    return any(s <= pos < e for s, e in spans)


class LinkFixer:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.all_files: list = []
        self.all_dirs: list = []
        self.by_rest: dict = {}
        self.by_name: dict = {}
        self.anchor_cache: dict = {}
        self._index()

    def _index(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            if '.git' in Path(dirpath).parts:
                continue
            d = Path(dirpath)
            dirnames[:] = [x for x in dirnames if x != '.git']
            for fn in filenames:
                p = (d / fn).resolve()
                self.all_files.append(p)
                self.by_rest.setdefault(split_rest(fn), []).append(p)
                self.by_name.setdefault(fn, []).append(p)
            for dn in dirnames:
                p = (d / dn).resolve()
                self.all_dirs.append(p)
                self.by_rest.setdefault(split_rest(dn), []).append(p)
                self.by_name.setdefault(dn, []).append(p)

    def headings_of(self, md_file: Path):
        md_file = md_file.resolve()
        if md_file in self.anchor_cache:
            return self.anchor_cache[md_file]
        info = {'slugs': set(), 'stripped': {}}
        try:
            text = md_file.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            self.anchor_cache[md_file] = info
            return info
        for line in text.splitlines():
            m = HEADING_RE.match(line)
            if not m:
                continue
            slug = github_slug(m.group(2))
            if not slug:
                continue
            info['slugs'].add(slug)
            key = strip_numeric_prefix(slug)
            info['stripped'].setdefault(key, []).append(slug)
        self.anchor_cache[md_file] = info
        return info

    def fix_anchor(self, md_file: Path, frag: str):
        info = self.headings_of(md_file)
        if frag in info['slugs']:
            return None
        if frag.lower() in info['slugs']:
            return frag.lower()
        key = strip_numeric_prefix(frag.lower())
        candidates = info['stripped'].get(key, [])
        if len(candidates) == 1 and candidates[0] != frag:
            return candidates[0]
        return None

    def find_moved_target(self, source_parent: Path, link_path: str):
        link_base = link_path.split('/')[-1]
        if not link_base or link_base in ('.', '..'):
            return None
        has_dotdot = '..' in link_path.split('/')
        want_rest = split_rest(link_base)
        candidates = list(self.by_rest.get(want_rest, []))
        if not candidates:
            candidates = list(self.by_name.get(link_base, []))
        if not candidates:
            return None

        for c in candidates:
            if c.parent == source_parent.resolve():
                return c

        if not has_dotdot:
            return None

        want_parts = strip_parts_for_match(link_path)
        scored = []
        for c in candidates:
            try:
                rel = c.relative_to(self.root).as_posix()
            except ValueError:
                continue
            cand_parts = strip_parts_for_match(rel)
            score = 0
            for a, b in zip(reversed(want_parts), reversed(cand_parts)):
                if a == b:
                    score += 1
                else:
                    break
            scored.append((score, c))
        if not scored:
            return None
        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best = scored[0]
        if best_score >= 2 and sum(1 for s, _ in scored if s == best_score) == 1:
            return best
        return None

    def process_file(self, path: Path, check_only: bool):
        original = path.read_text(encoding='utf-8')
        lines = original.splitlines(keepends=True)
        out_lines = []
        fixed, broken = 0, []
        in_fence = False

        for lineno, line in enumerate(lines, start=1):
            if FENCE_RE.match(line):
                in_fence = not in_fence
                out_lines.append(line)
                continue
            if in_fence:
                out_lines.append(line)
                continue

            spans = inline_code_spans(line)

            def repl(m):
                nonlocal fixed
                prefix, target, title, suffix = (
                    m.group(1), m.group(2), m.group(3) or '', m.group(4))
                if inside_spans(m.start(2), spans):
                    return m.group(0)
                if is_external(target):
                    return m.group(0)
                new_target = self.fix_target(path, target, lineno, broken)
                if new_target is not None and new_target != target:
                    fixed += 1
                    return f'{prefix}{new_target}{title}{suffix}'
                return m.group(0)

            out_lines.append(LINK_RE.sub(repl, line))

        if fixed and not check_only:
            path.write_text(''.join(out_lines), encoding='utf-8')
        return fixed, broken

    def fix_target(self, source: Path, target: str, lineno: int, broken: list):
        path_part, hash_sep, frag = target.partition('#')
        new_path_part = path_part

        target_file = None
        if path_part and not is_external(path_part):
            clean = path_part.strip()
            if clean.startswith('<') and clean.endswith('>'):
                clean = clean[1:-1]
            if clean.startswith('/'):
                resolved = (self.root / clean.lstrip('/')).resolve()
            else:
                resolved = (source.parent / clean).resolve()
            needs_search = False
            if resolved.exists():
                try:
                    link_rest = split_rest(Path(clean).name)
                    actual_rest = split_rest(resolved.name)
                    if link_rest != actual_rest:
                        needs_search = True
                    else:
                        target_file = resolved
                except Exception:
                    target_file = resolved
            else:
                needs_search = True

            if needs_search:
                found = self.find_moved_target(source.parent, clean)
                if found is None:
                    broken.append((lineno, target, 'target not found'))
                    return None
                try:
                    rel = os.path.relpath(found, source.parent.resolve())
                except ValueError:
                    broken.append((lineno, target, 'ambiguous move'))
                    return None
                new_path_part = Path(rel).as_posix()
                target_file = found
        elif not path_part and hash_sep:
            target_file = source.resolve()

        new_frag = frag
        if hash_sep:
            anchor_scope = target_file if target_file is not None else None
            if anchor_scope is not None and anchor_scope.suffix.lower() == '.md' \
                    and anchor_scope.exists():
                fixed_frag = self.fix_anchor(anchor_scope, frag)
                if fixed_frag is not None:
                    new_frag = fixed_frag
                elif frag.lower() not in self.headings_of(anchor_scope)['slugs']:
                    broken.append((lineno, target, 'anchor not found'))
                    if new_path_part == path_part:
                        return None
            elif anchor_scope is None:
                broken.append((lineno, target, 'anchor without file'))
                return None

        new_target = new_path_part + (hash_sep + new_frag if hash_sep else '')
        if new_target == target:
            return None
        return new_target


def run_links(files: list, root: Path, check_only: bool, quiet: bool):
    """Fix links in files. Returns (fixed_total, broken_total)."""
    fixer = LinkFixer(root)
    total_fixed = 0
    total_broken = 0
    for f in files:
        fixed, broken = fixer.process_file(f, check_only=check_only)
        total_fixed += fixed
        total_broken += len(broken)
        try:
            rel = f.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            rel = f
        if fixed:
            verb = 'WOULD-FIX' if check_only else 'FIXED'
            print(f'{verb} {rel}  ({fixed} link(s) updated)')
        for lineno, target, reason in broken:
            print(f'  BROKEN {rel}:{lineno}: ({target}) [{reason}]')
        if not fixed and not broken and not quiet:
            print(f'OK    {rel}')
    return total_fixed, total_broken


# --------------------------------------------------------------------------
# Path collection
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

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

    root = Path(args.root).resolve()
    check_only = args.check
    quiet = args.quiet

    md_files = collect_markdown(args.paths)
    if not md_files and not args.no_rename:
        # rename-only run on a dir without .md directly? re-check below
        pass

    rename_count = 0
    rename_errors: list = []
    if not args.no_rename:
        explicit_dirs = collect_explicit_dirs(args.paths)
        rename_dirs = discover_rename_dirs(explicit_dirs)
        print(f'--- rename ({len(rename_dirs)} dir(s)) ---')
        rename_count, rename_errors = run_rename_on_dirs(
            rename_dirs, check_only, quiet)
        # renames moved files: re-collect so later steps see final names
        md_files = collect_markdown(args.paths)
    else:
        print('--- rename (skipped) ---')

    if args.convert_lists:
        print(f'--- convert lists ({len(md_files)} file(s)) ---')
        convert_count = run_convert(md_files, check_only, quiet)
    else:
        print('--- convert lists (skipped, use --convert-lists to enable) ---')
        convert_count = 0

    if not args.no_headings:
        print(f'--- headings ({len(md_files)} file(s)) ---')
        headings_count = run_headings(md_files, check_only, quiet)
    else:
        print('--- headings (skipped) ---')
        headings_count = 0

    if not args.no_links:
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


if __name__ == '__main__':
    sys.exit(main())
