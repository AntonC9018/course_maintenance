# Agent instructions

Single maintenance script for the course repos: `maintain.py`.
It replaces the old per-task scripts (`rename_files.py`, `fix_files.py`,
`fix_links.py`, `convert_lists_to_headers.py`) — do not resurrect those.

## When asked to maintain a course repo after edits

1. Always preview first:
   `python3 <this-repo>/maintain.py --check <paths>`
2. If the preview looks right, apply:
   `python3 <this-repo>/maintain.py <paths>`
3. File args fix only that file and never trigger renames.
   Dir args (default `.`) also close `NN_` numbering gaps in every lab
   dir underneath. So: pass files you edited; pass a lab dir (or `.`)
   when files were added, removed, or reordered.

## Pipeline (fixed order: rename → convert → headings → links)

- **rename**: closes `NN_` gaps per directory, `*.md` files only (numbered
  assets such as `images/01_*.png` are never touched). Duplicate numbers
  abort that directory with an error — fix by hand, never force.
  Lettered appendices (`21a_...`) take no number of their own: they follow
  their parent's new number (`21_oop` → `20_oop` pulls `21a_func` →
  `20a_func`), so `21a` always stays right after `21`.
- **convert**: off unless `--convert-lists` is passed. It rewrites genuine
  ordered lists too, so enable it only for files whose numbered items are
  all meant to become `###` headers.
- **headings**: `H1` number := `NN_` filename prefix; all `### N.` headers
  resequenced `1..N`. Files whose `H1` has no number are left alone.
- **links**: repairs file links broken by renames and anchors broken by
  heading resequencing. Skips external URLs and code blocks/spans.
  `BROKEN` lines it cannot fix need a human — report them, don't guess.

## When editing this script

- Keep it dependency-free (stdlib only) and single-file.
- Preserve the step order; the link index must be built after renames
  and heading fixes so it sees final names/slugs.
- Validate on a copy of a course repo (`cp -a <repo> /tmp/opencode/...`,
  never the live repo): `--check` output must be empty-stable on the
  second run, and the first run's rename plan must match the old scripts'
  `--dry` output for directories without lettered files.
