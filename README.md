# course_maintenance

Shared maintenance + publishing tooling for course repositories.
Stdlib-only Python 3, no install step: every entry point runs as
`python3 <this-repo>/<script> ...` from any working directory.

## Layout (issue #6)

Language choice: **Python 3, stdlib only** (multi-file package, not a
single file). Rationale: the previous `maintain.py` was already
dependency-free Python, the spec fixes the command surface to
`python3 <course_maintenance>/publish.py ...`, and temp-dir tests need
nothing beyond the interpreter. The old single-file constraint now
applies to nothing; the step order below is the constraint that remains.

- `maintain.py` — preserved CLI (thin shim, observable behavior
  unchanged). Preview with `--check`, apply without it; see `AGENTS.md`.
- `publish.py` — stable dispatcher:
  `publish.py <responsibility> <operation> --course-repo <repo>`
  (`metadata generate`, `publishing check`, `projection build`,
  `site build`, plus `ci`). Stubbed with "not yet implemented" errors
  until issues #7–15; see its docstring for the `register()` extension
  point.
- `maintenance/` — one module per responsibility:
  `patterns` (shared regexes), `rename` (NN_ gap closing incl. lettered
  appendices: 16, 16a, 17 → 16, 17, 18), `convert` (opt-in list→`###`),
  `headings` (H1/H3 resequencing), `links` (file/anchor repair),
  `pipeline` (orchestration + path collection).
- `tests/` — stdlib `unittest` suite. Every test builds its repo in a
  `TemporaryDirectory` and passes absolute paths; tests never mutate
  fixtures or live checkouts.

Pipeline order is fixed and must be preserved:
**rename → convert → headings → links**. The link index is built last
(inside `links.run_links`) so it sees final names/slugs, and the file
list is re-collected after renames for the same reason.

## Migration

No action needed: `maintain.py` accepts the same paths/flags and
produces byte-identical output to the pre-#6 monolith (verified by
differential run on a disposable course-repo copy: identical `--check`
output, identical post-apply trees, empty-stable second `--check`).
New code should import from `maintenance.*` (not copy step logic) and
expose new commands through `publish.py`'s registry — never by adding
logic back into one file, and never by recreating the old standalone
scripts (`rename_files.py`, `fix_files.py`, `fix_links.py`,
`convert_lists_to_headers.py`).

## Commands

```sh
python3 -m unittest discover -s tests          # full suite (26 tests)
python3 -m unittest tests.test_rename -v       # one seam
python3 maintain.py --check <paths>            # preview maintenance
python3 publish.py metadata generate --course-repo <repo>  # stub → exit 2
```

Exit codes: `maintain.py` 0 clean/success, 1 dirty in `--check` or
rename errors. `publish.py` 0 success, 1 validation-dirty, 2 usage
error / bad `--course-repo` / not yet implemented.
