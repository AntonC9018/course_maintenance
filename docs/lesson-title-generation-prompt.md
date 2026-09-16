# Lesson title generation prompt (DEPRECATED)

> Titles are no longer stored in source frontmatter. The page title is
> derived from each lesson's first authored H1 during projection
> (PROJ-2); `publishing check` and `maintain.py` fail lessons with no
> H1. Keep this file for history only: to retitle a lesson, rewrite its
> H1 (descriptive, no lab number, no ordering prefix). The prompt below
> was used once to backfill H1s from the old committed titles.

Use the following prompt with a language model when adding explicit titles to an existing course repository. Give each worker a disjoint list of Markdown files.

## Prompt

You are adding explicit lesson titles to an existing course repository.

Work only on the Markdown files in the assigned scope. Read each file closely enough to identify its actual subject. Add a `title` field to YAML frontmatter at the beginning of every assigned file. If frontmatter already exists, add or update only its `title` field without changing any other field. If it does not exist, create it.

Choose a concise, natural title in the language of the document. Prefer an accurate existing H1 when one exists, but improve it when it is misleading, overly narrow, numbered, or absent. Infer a useful title from the document content and its surrounding course context, not mechanically from the filename. Do not put lesson numbers, path segments, `doc`, `README`, or `stub` in the title merely because they appear in the source path. For an empty or outline-only lesson, infer the intended subject from its filename, directory, translated counterpart, and neighboring lessons.

Do not add slugs, website links, headings, translations, explanations, or comments. Do not edit lesson bodies, whitespace outside frontmatter, filenames, or any non-Markdown file. Do not commit. At the end, report the files changed and any title whose intent remains genuinely ambiguous.

## Review prompt

Review only the newly added `title` values in the assigned Markdown files. Read the nearby document content and, when available, compare matching English and Russian lessons. Fix a title only when it is misleading, inconsistent with its counterpart, or unnatural in the document's language. Prefer concise teaching-material titles over literal filename translations. Do not change frontmatter delimiters, add fields, edit document bodies, rename files, or commit. Report every title changed and any unresolved ambiguity.
