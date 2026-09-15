"""Step 4: links (old fix_links.py, verbatim logic). Extracted verbatim."""

import os
import re
from pathlib import Path

from .patterns import (
    EXTERNAL_PREFIXES,
    FENCE_RE,
    HEADING_RE,
    LINK_RE,
    NUM_PREFIX_RE,
    ORDERED_PATTERN,
)


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
