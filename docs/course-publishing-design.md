# Course publishing design

This document captures the agreed initial design for publishing course repositories as GitHub Pages websites. The first rollout targets the data-structures-and-algorithms repository; the shared implementation remains suitable for adding the C# repository afterward. Deferred capabilities are tracked as GitHub issues.

## Product and hosting

- Each course repository owns one independently deployed GitHub Pages project site.
- Astro Starlight is the selected renderer, subject to a compatibility spike over representative existing content.
- The initial data-structures-and-algorithms site is titled `Programming Fundamentals and Data Structures`, with the Russian equivalent `Основы программирования и структуры данных`.
- The site provides hierarchical navigation, a sidebar, multilingual content, local search, and code-friendly rendering.
- The initial site uses Starlight's default theme, layout, typography, and responsive behavior without a custom logo or course branding.
- Empty lessons are valid and publish as blank pages with their metadata.
- Presentations are deferred to [issue #3](https://github.com/AntonC9018/course_maintenance/issues/3).
- Deferred presentations and subject-specific views do not appear as placeholders, disabled controls, or coming-soon pages.

## Source documents and web projections

- Repository Markdown remains the authoring source of truth and retains its original relative links.
- Each course repository initially uses a `course-publishing.json` content configuration that selects language content roots and may explicitly include or exclude Markdown source documents. The configuration does not enumerate every lesson individually. The format is provisional and may be replaced when the implementation is restructured.
- Site and repository identity are initially inferred from repository context rather than required as configuration.
- The initial data-structures-and-algorithms configuration publishes all Markdown under `en` and `ru` except supporting README files in `linker_examples`, `snake/raylib-example`, `vector`, `waves_algorithm`, `waves_algorithm/minecraft`, and `sorting/examples`, plus `ru/labs/cpp/README.md`. Outline and stub lessons remain published.
- Each published lesson stores an explicit `title` and stable, nested `slug` in YAML frontmatter.
- Starlight renders the frontmatter title as the sole website H1. The projection shifts every authored Markdown heading down one level, preserving its text and relative hierarchy, so documents with existing H1 headings do not gain duplicate page-level headings.
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
- elect at most one index lesson in each directory, preferring `index.md`, then `README.md`, then `doc.md`; only that lesson collapses to its directory, while any remaining candidates keep their basename as a route component;
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

`05a_programming_fundamentals` uses `advanced-programming-fundamentals` to distinguish it from `05_programming_fundamentals`. The existing `labs/cpp/test1.md` lessons use `assessment-1` as their public route component.

The planned C# rollout uses this mapping:

| Source | Canonical section |
| --- | --- |
| `labs/1_basic` | `/ru/csharp/labs/basic/...` |
| `labs/2_design` | `/ru/csharp/design/labs/...` |
| `labs/3_advanced` | `/ru/csharp/advanced/labs/...` |

## Link resolution

The build constructs an index from source paths to canonical lesson routes across a small allowlist of participating repositories. It preserves query strings and fragments, then projects links as follows:

- a Markdown target published by a known course repository becomes its canonical website URL;
- a Markdown target excluded from publication becomes a GitHub `blob` URL;
- a code or other repository file becomes a GitHub `blob` URL;
- a repository directory becomes a GitHub `tree` URL;
- a locally embedded image is copied into the web projection so it displays on the course site; other repository artifacts remain linked rather than copied;
- GitHub file and directory links use the target repository's default branch;
- an unresolved local target is a validation error rather than a guessed link.

## Navigation

For the initial release, the projection tree follows canonical slugs and produces one locale-wide sidebar containing Common, C++, and Data Structures and Algorithms groups. Structural labels are fixed by the specification. A group with an elected index lesson takes its label from that lesson's title and presents the lesson itself as `Overview` or `Обзор`. Any unelected `index.md`, `README.md`, or `doc.md` lesson is an ordinary lesson placed immediately after the overview, in that precedence order. Remaining route segments are humanized by replacing hyphens with spaces and uppercasing the first cased character without otherwise changing the segment. These renderer-owned rules are not author-controlled navigation override metadata.

The projection injects renderer-only ordering derived from source numbering so the sidebar retains teaching order even though canonical slugs omit ordering prefixes. Numeric prefixes sort numerically, including lettered positions such as `21a`; unnumbered siblings sort alphabetically. This derived order is not author-controlled navigation override metadata.

All sidebar groups are collapsed by default. Starlight's standard behavior highlights the current lesson, opens its ancestor groups, and preserves the sidebar's scroll position; the initial site adds no custom scrolling or dynamic reordering. Outline documents named `stub.md` receive no special badges, labels, or visibility rules.

Only existing source documents produce lesson routes. A directory without an index lesson remains a non-clickable sidebar group and does not receive a generated listing page. Instead, each indexless group route redirects to the first descendant lesson in that group's sidebar order (a redirect, not a listing page: no content is generated). The site does not synthesize localized fallback routes for missing translations. The site root and `/en/` redirect to the first ordinal English Common lab, `/en/common/labs/computer-architecture/`; `/ru/` redirects to the corresponding first Russian Common lab, `/ru/common/labs/computer-architecture/`. The locale roots do not receive separate starter pages.

Each locale has its own lab sequence containing lessons below that locale's `/{subject}/labs/` route. The sequence contains ordinal Common labs, then C++ labs, then data-structures-and-algorithms labs. Within each lab group, numeric source order is authoritative, so a newly added numbered lab is inserted at its numeric position; unnumbered labs follow numbered labs alphabetically. Assessment 1 is placed last among the C++ labs for the initial release. Non-lab lessons use ordinary sidebar-order previous and next links.

Subject-specific navigation views are deferred to [issue #2](https://github.com/AntonC9018/course_maintenance/issues/2). A navigation view controls discoverability only: omission never restricts a lesson's direct public URL.

## Renderer compatibility

- Inline mathematical formulas use the repository's GitHub-friendly `$`code`$` source notation. Display formulas use GitHub's `$$` block notation. The web projection may deterministically translate either notation into renderer input, but source documents are not normalized to the renderer's preferred delimiters.
- Mermaid diagrams are rendered to SVG during the build. Generated SVGs are ephemeral build artifacts and are never committed.
- Raw C++ angle brackets in prose must remain inside code spans; tables and nested `<details>` use the renderer's supported Markdown forms.

## Maintenance and delivery

- An explicit local metadata-generation operation writes missing slugs and source backlinks before the site is published. Routine maintenance does not generate them as a side effect.
- Existing slugs are validated but never silently regenerated after source files move. The marked source-backlink block may be refreshed when its generated URL changes.
- The source backlink immediately follows YAML frontmatter, is enclosed by `<!-- course-site-backlink:start -->` and `<!-- course-site-backlink:end -->`, and uses `This lesson on the website` in English or `Этот урок на сайте` in Russian.
- Each projected lesson provides a localized `View on GitHub` link to the normal rendered GitHub page for its source document, never to the ephemeral projection or raw-file response.
- An optional pre-commit hook may run metadata generation and stage its generated changes.
- CI checks for missing or stale generated metadata, fails with instructions to run metadata generation, and never self-commits.
- Compiled website output is deployed as a GitHub Pages artifact rather than committed.
- CI and GitHub Pages deployment are part of the initial version. Shared CI support is implemented through [issue #14](https://github.com/AntonC9018/course_maintenance/issues/14), and the first course rollout is implemented through [issue #15](https://github.com/AntonC9018/course_maintenance/issues/15).
- Each course repository keeps a thin workflow that checks out and executes its pinned `course_maintenance` submodule. Shared-tool changes reach a course through an explicit submodule-pointer commit rather than a floating workflow reference.
- The stable CI invocation is `python3 <course_maintenance>/publish.py ci --course-repo <course_repository>`. Local publishing operations use the same executable, responsibility words, and `--course-repo` option.
- Pull requests to `master` validate the complete site without deploying. Every successful push to `master`, including a direct commit, republishes that exact revision; failed validation leaves the preceding site live.
- The validation check is required for ordinary pull-request merges, while repository administrators retain the protection bypass needed for direct `master` commits.
- The initial rollout has no peer-repository checkout and no automatic deployment rollback.

The implementation may replace the current monolithic maintenance script with responsibility-focused components and may use a language other than Python. Compatibility with the existing internal structure is not a design constraint; restructuring begins only when implementation is explicitly authorized.

## Compatibility spike

Before production implementation, build representative lessons with Starlight and verify nested `<details>` blocks with Markdown, raw C++ angle-bracket text, math, Mermaid, tables, images, stable nested routes, rewritten links, and the GitHub Pages project base. The spike is disposable evidence-gathering work. Plugins and deterministic web-projection transforms are acceptable; reopen the renderer decision if representative content cannot be rendered faithfully without widespread source-document rewrites or an unbounded compatibility layer.
