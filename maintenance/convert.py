"""Step 2: convert numbered lists to ### headers (opt-in).

Extracted verbatim from maintain.py (old convert_lists_to_headers.py,
fixed to write back in place and to skip fenced code).
"""

from .patterns import FENCE_RE, LIST_ITEM_RE


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
