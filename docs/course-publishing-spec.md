# Initial course publishing specification

This specification defines the first production release of the shared course-publishing system. It turns Markdown in the data-structures-and-algorithms course repository into an independently deployed Astro Starlight site while keeping repository Markdown as the authoring source of truth.

The product decisions and rationale are recorded in [course-publishing-design.md](course-publishing-design.md) and ADRs 0001–0006. This document defines observable behavior and acceptance criteria for implementation.

## Release boundary

The initial release:

- publishes the data-structures-and-algorithms repository completely;
- keeps reusable publishing behavior, validation, renderer setup, and deployment support in `course_maintenance`;
- generates and validates committed lesson metadata explicitly;
- builds disposable web projections and a deployable static site;
- includes shared CI support through issue #14 and the data-structures-and-algorithms GitHub Pages rollout through issue #15.

The initial release does not include:

- the C# course rollout;
- author-controlled navigation overrides from issue #1;
- subject-specific navigation views from issue #2;
- Slidev presentation publishing from issue #3;
- generated translations, accounts, progress tracking, or access control;
- custom visual branding or placeholders for deferred features.

## Inputs and generated outputs

### Course repository

A course repository supplies:

- Git history and an `origin` remote from which repository identity, public GitHub URL, and GitHub Pages project URL are inferred; the published branch is always `master`;
- a repository-owned `course-publishing.json` file;
- Markdown source documents below configured language roots;
- committed lesson titles, slugs, and source backlinks.

A missing `origin` remote is a validation error with an actionable message. Inference reads only the local `origin` configuration and requires no GitHub CLI or network access.

### Content configuration

`course-publishing.json` is a provisional, versioned JSON interface. Its first schema is:

```json
{
  "version": 1,
  "default_language": "en",
  "languages": [
    { "code": "en", "root": "en", "label": "English" },
    { "code": "ru", "root": "ru", "label": "Русский" }
  ],
  "exclude": [
    "en/05_programming_fundamentals/linker_examples/README.md"
  ],
  "route_sections": [
    { "source": "00_introduction", "destination": "common" },
    { "source": "labs/common", "destination": "common/labs" }
  ],
  "site_title": {
    "en": "Programming Fundamentals and Data Structures",
    "ru": "Основы программирования и структуры данных"
  },
  "root_lesson": "en/labs/common/01_computer_architecture.md",
  "peer_repositories": []
}
```

The checked-in data-structures-and-algorithms configuration expands the abbreviated arrays above to include every exclusion and source-to-section mapping recorded in the design. Paths use forward slashes and are relative to the course repository root. Version 1 rejects unknown fields, duplicate language codes or roots, absolute paths, escaping paths, overlapping route mappings, unknown root lessons, and exclusions outside configured language roots.

`peer_repositories` is an allowlist of local repository paths used to resolve cross-repository lesson links. It is empty for the first rollout but the index format must support adding the C# repository without changing lesson identity.

### Committed source metadata

Every selected lesson has YAML frontmatter containing:

```yaml
---
title: A concise localized title
slug: en/cpp/labs/instruction
---
```

Immediately after frontmatter, every lesson has one generated block:

```md
<!-- course-site-backlink:start -->
[This lesson on the website](https://example.github.io/course/en/cpp/labs/instruction/)
<!-- course-site-backlink:end -->
```

Russian lessons use `Этот урок на сайте`. Existing slugs are stable identities and are never silently regenerated.

### Disposable outputs

Projection and build commands write only below an explicit or automatically created output directory outside the source tree. They produce:

- a slug-shaped Starlight content tree;
- copied local image assets;
- renderer configuration and generated navigation data;
- static Mermaid SVGs;
- a static `dist/` suitable for a GitHub Pages artifact.

None of these outputs are committed to a course repository.

## Required operations

The implementation language and internal module layout are unconstrained. The command-line surface may replace the current monolithic script, but it must expose four responsibility-focused operations through `python3 <course_maintenance>/publish.py <responsibility> <operation> --course-repo <course_repository>`:

1. `metadata generate`: add missing lesson slugs and add or refresh marked source backlinks;
2. `publishing check`: validate configuration, selected content, metadata, links, assets, and route uniqueness without writing source files;
3. `projection build`: create a deterministic disposable web projection without compiling the site;
4. `site build`: create the projection, invoke the pinned renderer toolchain, and produce `dist/`.

`<course_maintenance>` is the path to the maintenance checkout or submodule, and `<course_repository>` is the explicit path to the course-repository root. Check mode is read-only and returns a nonzero status for any error. Errors identify the source path, the violated rule, and the corrective operation when one exists.

## Functional requirements

### Configuration and lesson inventory

- **CFG-1:** Parse and strictly validate version 1 of `course-publishing.json`.
- **CFG-2:** Select Markdown only from configured language roots, then apply exact repository-relative exclusions.
- **CFG-3:** The initial configuration selects exactly 140 current Markdown lessons: 77 English and 63 Russian.
- **CFG-4:** Empty, outline, and `stub.md` documents remain valid lessons.
- **CFG-5:** Infer repository and site identity solely from the `origin` remote URL; a missing `origin` is a validation error.
- **CFG-6:** Reject case-folded duplicate source paths and configuration paths that do not resolve to the intended repository entry.

### Metadata generation and validation

- **META-1:** Generate a missing slug from the configured language, route section, and source path.
- **META-2:** Slug components are lowercase kebab-case; ordering prefixes such as `01_` and `21a_` are removed; `stub` remains a component. In each directory containing selected lessons named `index.md`, `README.md`, or `doc.md` case-insensitively, elect the first existing candidate in that precedence order as the index lesson and collapse only its slug to the directory. Any other candidate keeps `index`, `readme`, or `doc` as its final slug component.
- **META-3:** Apply the recorded special mappings: the `05a_programming_fundamentals` directory component maps to `advanced-programming-fundamentals`, and the existing `labs/cpp/test1.md` lessons (English and Russian counterparts) map to an `assessment-1` route component. The `test1.md` mapping applies only to these existing lessons, not as a general basename rule.
- **META-4:** Reject duplicate slugs after Unicode normalization and case folding.
- **META-5:** Never modify an existing valid slug during generation. Invalid or conflicting existing slugs fail with a diagnostic requiring explicit correction.
- **META-6:** Insert or replace exactly one marked source-backlink block immediately after frontmatter, using the lesson language and inferred canonical site URL.
- **META-7:** `publishing check` rejects missing slugs and missing, duplicate, malformed, or stale backlink blocks and tells the contributor to run metadata generation. A backlink block is stale when its URL differs from the absolute website URL generated from the lesson's current slug and the inferred site URL.
- **META-8:** Metadata generation is idempotent and ordinary course maintenance does not invoke it implicitly.

### Route and link resolution

- **LINK-1:** Build an index from normalized absolute source paths to canonical lesson URLs for the course repository and configured peers.
- **LINK-2:** Resolve relative links from the original source location before moving the document into the projection.
- **LINK-3:** Preserve query strings and fragments.
- **LINK-4:** Rewrite a link to a published Markdown target as its canonical course-site URL.
- **LINK-5:** Rewrite excluded Markdown and ordinary files as GitHub `blob` URLs and directories as GitHub `tree` URLs, always using the `master` branch.
- **LINK-6:** Copy locally embedded images into the projection and rewrite image destinations to the copied assets. An image is any Markdown `![...](...)` destination, plus an `<img>` `src` if one is ever used. Other artifacts remain GitHub links.
- **LINK-7:** Reject missing, escaping, ambiguous, or unsupported local targets instead of guessing.
- **LINK-8:** Validate Markdown heading fragments against the target source document using the same GitHub-anchor rules as course maintenance.

### Markdown projection

- **PROJ-1:** Remove the marked source-backlink block from projected content.
- **PROJ-2:** Keep the frontmatter title as the sole website H1 and shift every authored Markdown heading down one level while preserving relative hierarchy.
- **PROJ-3:** Convert GitHub-friendly inline math `$`code`$` and `$$` display blocks deterministically into the pinned math renderer's accepted input without changing source files.
- **PROJ-4:** Preserve fenced code, tables, nested `<details>`, raw C++ text protected by code spans, and ordinary Markdown semantics.
- **PROJ-5:** Inject renderer-only navigation order and presentation metadata; never write renderer metadata into source documents.
- **PROJ-6:** Produce byte-identical projections for identical inputs and configuration, excluding explicitly identified tool timestamps if unavoidable.

### Renderer and navigation

- **SITE-1:** Build with pinned Astro Starlight and plugin versions proven by the compatibility suite.
- **SITE-2:** Serve canonical slugs below the repository's GitHub Pages project base with trailing-slash URLs.
- **SITE-3:** Configure English and Russian locales without generating fallback lesson routes or locale-root starter pages. Redirect `/en/` to `/en/common/labs/computer-architecture/` and `/ru/` to `/ru/common/labs/computer-architecture/`.
- **SITE-4:** Redirect `/` to `/en/common/labs/computer-architecture/`; English is the default locale.
- **SITE-5:** Use localized site titles and otherwise retain Starlight's default theme, layout, typography, responsive behavior, and outline presentation.
- **SITE-6:** Produce one sidebar per locale with these fixed structural labels:

  | Role or segment | English | Russian |
  | --- | --- | --- |
  | `common` | Common | Общие темы |
  | `cpp` | C++ | C++ |
  | `dsa` | Data Structures and Algorithms | Структуры данных и алгоритмы |
  | `labs` | Labs | Лабораторные работы |
  | index link | Overview | Обзор |

- **SITE-7:** A group with an index lesson uses that lesson's title as the group label and the localized fixed index-link label from SITE-6 for the lesson itself. Place any unelected `index.md`, `README.md`, or `doc.md` lessons immediately after the index link, in that precedence order, as ordinary lessons. For any other group label without a fixed label or index lesson, humanize its route segment by replacing each hyphen with a space and uppercasing the first cased character without otherwise changing it; for example, `advanced-programming-fundamentals` becomes `Advanced programming fundamentals`.
- **SITE-8:** Keep groups collapsed by default and retain Starlight's default current-page highlighting, ancestor expansion, and scroll persistence without custom reordering or scrolling.
- **SITE-9:** Sort numbered siblings numerically, including lettered positions such as `21a`; sort unnumbered siblings alphabetically.
- **SITE-10:** Leave groups without index lessons non-clickable and do not create synthetic listing lessons.
- **SITE-11:** A lab page is a lesson whose canonical slug matches `/{lang}/{subject}/labs/...`. Give lab pages explicit previous and next links within one sequence per locale: Common labs, C++ labs, then data-structures-and-algorithms labs. Within a lab group, insert numbered labs by numeric source order and place unnumbered labs afterward alphabetically; place Assessment 1 last among C++ labs. Give non-lab pages ordinary sidebar-order pagination.
- **SITE-12:** Add a localized `View on GitHub` footer link to the normal rendered source-document page, not the edit form, raw response, or projection.
- **SITE-13:** Include Pagefind local search and index only existing published lesson routes.
- **SITE-14:** Do not expose controls or placeholder pages for navigation views or presentations.

### Mermaid and static output

- **DIAG-1:** Convert every Mermaid fence into an SVG during the build using pinned Playwright and Chromium dependencies.
- **DIAG-2:** Fail the build with the source path and Mermaid diagnostic when a diagram cannot render.
- **DIAG-3:** Do not ship Mermaid client JavaScript or commit generated SVGs.
- **DIAG-4:** Keep generated SVG output deterministic enough for repeatable build tests, normalizing nondeterministic identifiers where necessary.

### CI and deployment

- **CI-1:** `course_maintenance` owns the stable CI-facing command `python3 <course_maintenance>/publish.py ci --course-repo <course_repository>`. It runs existing course-maintenance checks, publishing checks, the compatibility suite, and a complete static site build. Shared dependency setup and CI configuration remain in `course_maintenance`.
- **CI-2:** A course repository owns only a thin GitHub Actions workflow. It checks out the course and its pinned `course_maintenance` submodule, then invokes the shared command from that submodule; it does not fetch a separate floating maintenance or reusable-workflow revision.
- **CI-3:** Every pull request targeting `master` runs the complete validation with read-only repository permissions. A failing validation is a required status check for ordinary pull-request merges. Pull-request jobs never deploy.
- **CI-4:** Every push to `master`, whether direct or produced by a pull-request merge, validates and builds that exact course and submodule revision. A successful build is deployed through the official GitHub Pages artifact workflow and the `github-pages` environment. Feature-branch pushes without a pull request do not run course-site CI.
- **CI-5:** Validation and deployment workflows use no path filters. CI never writes or commits source metadata.
- **CI-6:** A change in `course_maintenance` affects a course only after the course repository explicitly commits an updated submodule pointer. The course CI validates that revision before deployment.
- **CI-7:** The initial data-structures-and-algorithms configuration has no peer repositories, and the initial CI does not implement peer-repository checkout. Peer checkout automation is deferred until a rollout needs it.
- **CI-8:** Third-party actions are pinned to immutable commit revisions. Build caches are keyed by the relevant pinned runtime, browser, and dependency-lock revisions and never cache source metadata, projections, or deployable output as authoritative results.
- **CI-9:** Pull-request validation has only `contents: read`. Pages write and identity-token permissions are confined to the deployment job for a successful `master` build.
- **CI-10:** Validation and deployment use concurrency controls that discard superseded work and ensure an older run cannot become the final deployment after a newer `master` revision. Failed validation does not deploy, so the previously published site remains live; the initial release does not perform automatic rollback.
- **CI-11:** After deployment, bounded-retry smoke tests verify the root redirect, representative English and Russian routes, search, static Mermaid output, and a copied asset at the public Pages URL.
- **CI-12:** The repository uses GitHub Actions as its Pages source and makes the validation status required for ordinary pull-request merges. It does not require changes to arrive through pull requests, and repository administrators retain the default protection bypass so direct `master` commits remain possible.

## Data-structures-and-algorithms rollout

The first rollout must:

1. correct `labs/algoritms` to `labs/algorithms` before generating public slugs;
2. add the complete `course-publishing.json` with the nine recorded supporting-document exclusions;
3. generate and review slugs and localized source backlinks for all 140 lessons;
4. build all routes and copied images without unresolved internal links;
5. verify that selected English and Russian lessons are counterparts when their repository-relative source paths are identical after removing their configured language roots, and that counterpart slugs are identical after removing the leading language component;
6. preserve all authored Markdown except intentional typo correction and generated metadata;
7. leave projection, Mermaid, browser, and `dist/` artifacts untracked.

Changes to translated source documents follow the course repository's translation-review workflow.

## Compatibility and acceptance suite

Automated fixtures and representative real lessons must cover:

- every slug-generation rule and collision class;
- English and Russian backlink generation;
- source links to published lessons, excluded Markdown, files, directories, images, peers, fragments, queries, and missing targets;
- matching, differing, absent, and repeated authored H1 headings;
- inline and display math;
- both real Mermaid diagrams in the initial corpus;
- nested `<details>`, tables, raw C++ angle brackets, fenced code, empty lessons, and outlines;
- locale-prefixed routes, GitHub Pages base paths, root redirect, sidebar labels/order/collapse, lab pagination, GitHub source links, Pagefind, and absence of fallback routes;
- a second identical projection/build that introduces no source changes or newly tracked files.

The initial release is accepted when all requirements above pass locally for a clean checkout, issues #14 and #15 pass their CI/deployment acceptance criteria on GitHub, and the published site is reachable at the inferred Pages URL.
