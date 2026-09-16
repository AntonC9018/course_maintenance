"""Step 3: headings (old fix_files.py). Extracted verbatim."""

import re

from .patterns import FENCE_RE, H1_RE, H3_RE

_H1_ANY_RE = re.compile(r'^\s{0,3}#\s+\S')
_H1_SETEXT_RE = re.compile(r'^\s{0,3}=+\s*$')
_ATX_ANY_RE = re.compile(r'^\s{0,3}#{1,6}(?:\s+|$)')


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


def has_h1(text: str) -> bool:
    """True when text has an authored H1 outside fenced code.

    Counts ATX ``# Title`` (exactly one #) or Setext ``===`` under
    paragraph text. The page title is derived from the H1, so every
    lesson needs one.
    """
    lines = text.splitlines()
    in_fence = False
    fenced: list[bool] = []
    for line in lines:
        if FENCE_RE.match(line):
            fenced.append(True)
            in_fence = not in_fence
            continue
        fenced.append(in_fence)
    prev_text = False
    for i, line in enumerate(lines):
        if fenced[i]:
            prev_text = False
            continue
        if _H1_ANY_RE.match(line):
            return True
        if _H1_SETEXT_RE.match(line) and prev_text:
            return True
        if line.strip() == '' or FENCE_RE.match(line):
            prev_text = False
            continue
        if _ATX_ANY_RE.match(line):
            prev_text = False
            continue
        prev_text = True
    return False


def is_lesson(text: str) -> bool:
    """True when the file carries lesson metadata (a ``slug:`` frontmatter key).

    Only published lessons need an H1 (the page title derives from it).
    Non-lesson docs (repo README, agent instructions, excluded asset
    READMEs) share the rename/links hygiene but must not trip the H1
    requirement. Frontmatter, when present, is the leading ``---`` block,
    so no fence tracking is needed to read it.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return False
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == '---' or stripped == '...':
            break
        if re.match(r'^slug\s*:', line):
            return True
    return False


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
            if not has_h1(new_text) and is_lesson(new_text):
                changed += 1
                print(f'MISSING H1 {path.name}  '
                      f'(expected exactly one `# Title`; '
                      f'the page title is derived from the H1)')
                continue
            if not quiet:
                print(f'OK      {path.name}  '
                      f'(no changes needed, H1={h1_number}, H3 headings={h3_count})')
            continue
        changed += 1
        for msg in h1_msgs + h3_msgs:
            print(f'  {msg}')
        if not has_h1(new_text) and is_lesson(new_text):
            print(f'MISSING H1 {path.name}  '
                  f'(expected exactly one `# Title`; '
                  f'the page title is derived from the H1)')
        if check_only:
            print(f'WOULD-FIX {path.name}  (H1={h1_number}, H3 headings={h3_count})')
        else:
            path.write_text(new_text, encoding='utf-8')
            print(f'FIXED {path.name}  (H1={h1_number}, H3 headings={h3_count})')
    return changed
