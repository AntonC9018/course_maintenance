"""Step 3: headings (old fix_files.py). Extracted verbatim."""

import re

from .patterns import H1_RE, H3_RE


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
