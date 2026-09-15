# Course publishing design

This document captures the agreed initial design for publishing the course repositories as GitHub Pages websites. Deferred capabilities are tracked as GitHub issues rather than included in the first implementation.

## Product and hosting

- Each course repository owns one independently deployed GitHub Pages project site.
- Astro Starlight is the selected renderer, subject to a compatibility spike over representative existing content.
- The site provides hierarchical navigation, a sidebar, multilingual content, local search, and code-friendly rendering.
- Empty lessons are valid and publish as blank pages with their metadata.
- Presentations are deferred to [issue #3](https://github.com/AntonC9018/course_maintenance/issues/3).

## Source documents and web projections

- Repository Markdown remains the authoring source of truth and retains its original relative links.
- Each published lesson stores an explicit `title` and stable, nested `slug` in YAML frontmatter.
- Each source document contains a source-only backlink labelled `This lesson on the website`. Russian documents use a natural Russian equivalent.
- The backlink is enclosed in reserved markers so the web projection can omit it.
- The build creates an ephemeral, slug-shaped Markdown tree for Starlight. Generated projections are never committed.
- The projection can inject renderer metadata, but the initial release has no navigation override metadata. Future overrides are tracked in [issue #1](https://github.com/AntonC9018/course_maintenance/issues/1).

## Canonical routes

Lesson slugs include the language and meaningful subject hierarchy, but not the GitHub Pages repository base. For example, `en/cpp/labs/instruction` is served under the repository's Pages base as `/en/cpp/labs/instruction/`.

Missing slugs are generated once using these rules:

- preserve the meaningful hierarchy;
- convert underscores and spaces to hyphens and lowercase;
- remove ordering prefixes such as `01_` and `21a_`;
- collapse `doc.md`, `index.md`, and `README.md` to their directory;
- retain `stub` as a route component;
- reject collisions and require an explicit resolution;
- correct genuine source-name typos before the first public slug is generated.

The initial data-structures-and-algorithms mapping is:

| Source | Canonical section |
| --- | --- |
| `00_introduction` through `03_command_line` | `/{lang}/common/...` |
| `04_compiler_and_ide` through `07_serialization`, including `05a_programming_fundamentals` | `/{lang}/cpp/...` |
| `08_searching_algorithms` through `11_multidimensional_arrays` | `/{lang}/dsa/...` |
| `labs/common` | `/{lang}/common/labs/...` |
| `labs/cpp` | `/{lang}/cpp/labs/...` |
| `labs/algoritms` | `/{lang}/dsa/labs/...` after correcting the directory name to `algorithms` |

`05a_programming_fundamentals` uses `advanced-programming-fundamentals` to distinguish it from `05_programming_fundamentals`. `test1.md` uses `assessment-1` as its public route component.

The initial C# mapping is:

| Source | Canonical section |
| --- | --- |
| `labs/1_basic` | `/ru/csharp/labs/basic/...` |
| `labs/2_design` | `/ru/csharp/design/labs/...` |
| `labs/3_advanced` | `/ru/csharp/advanced/labs/...` |

The `05_dependenices.md` typo is corrected before its slug is generated.

## Link resolution

The build constructs an index from source paths to canonical lesson routes across a small allowlist of participating repositories. It preserves query strings and fragments, then projects links as follows:

- a Markdown target published by a known course repository becomes its canonical website URL;
- a code or other repository file becomes a GitHub `blob` URL;
- a repository directory becomes a GitHub `tree` URL;
- GitHub file and directory links use the target repository's default branch;
- an unresolved local target is a validation error rather than a guessed link.

## Navigation

For the initial release, the projection tree follows canonical slugs and Starlight derives its sidebar from that tree. Subject-specific navigation views are deferred to [issue #2](https://github.com/AntonC9018/course_maintenance/issues/2). A navigation view controls discoverability only: omission never restricts a lesson's direct public URL.

## Maintenance and delivery

- Maintenance writes missing slugs and source backlinks locally.
- An optional pre-commit hook may run maintenance and stage its generated changes.
- CI checks for missing or stale generated metadata and never self-commits.
- Compiled website output is deployed as a GitHub Pages artifact rather than committed.
- CI implementation is deferred to [issue #4](https://github.com/AntonC9018/course_maintenance/issues/4).

## Compatibility spike

Before production implementation, build representative lessons with Starlight and verify nested `<details>` blocks with Markdown, raw C++ angle-bracket text, math, Mermaid, tables, images, stable nested routes, rewritten links, and the GitHub Pages project base. The spike is disposable evidence-gathering work; a serious incompatibility may reopen the renderer decision.
