# Course-owned configuration

`course-publishing.json` is the single configuration file for content,
CI, navigation, deployment expectations, and post-deploy probes. The
shared commands read it relative to `--course-repo`, from any working
directory. Configuration is strictly validated, including unknown fields,
option types, and repository-relative paths. No source changes occur in
CI, smoke checks, or settings verification.

The original version-1 content fields remain required. The following
fields are optional so existing content configurations still load.

## Maintenance formatting

`maintenance.heading_numbering` selects `"section"` (the default, restart
numbered H3 examples after each H2) or `"document"` (continuous numbering).
CI and `maintain.py --root <course-repo>` read the same setting. C# uses
`document`; the data-structures course uses `section`. Other maintenance
steps preserve their shared rename → convert → headings → links order.

## CI

```json
"ci": {
  "maintenance_paths": ["labs", "docs", "README.md"],
  "run_compatibility_tests": false,
  "required_pr_label": "ci-ready"
}
```

`maintenance_paths` selects existing Markdown files or directories;
directories also check numbering. Absolute, escaping, missing, and
shared-tooling paths are rejected. When omitted, configured language
roots and root Markdown files are checked. There is no fallback scan of
the entire checkout. Publishing validation always uses `languages` and
`exclude`, and a successful CI run always builds the complete course.

`run_compatibility_tests` defaults to `true` for the previous caller
contract. Course repositories should explicitly set it to `false`:
shared unit and compatibility fixtures run in the shared repository's CI.
`required_pr_label` defaults to `null`; when set, GitHub pull-request
validation fails before dependencies are installed until that label is
present. Local checks and push builds do not require labels.

## Deployment expectations

```json
"deployment": {
  "branch": "master",
  "required_status_checks": ["validate"],
  "require_pull_requests": false,
  "enforce_admins": false
}
```

These are also the defaults. `branch` controls GitHub source links and
branch-protection verification. GitHub workflow branch triggers must
match this value; GitHub Actions cannot read JSON while choosing triggers.
Repository identity is inferred from the local GitHub `origin` remote.
The Pages project URL is derived from that identity; optional `pages_url`
overrides it for a custom domain or base path and is used consistently by
metadata backlinks, renderer site/base, and smoke/settings checks.

`publish.py pages verify --course-repo .` reads Pages and branch-protection
settings with `gh api`, compares structured JSON to the configured
expectations, and changes nothing. API access failures print `SKIP`;
`--strict` makes unavailable verification fail. Actual mismatches always
fail. This verifies classic branch protection, not repository rulesets.

## Navigation and metadata

`navigation` accepts:

- `group_labels`: group paths or segment names mapped to per-language
  labels; index lesson titles still take precedence. Unconfigured groups
  use humanized route segments.
- `subject_order`: subjects to put first in sidebars and lab sequences;
  other lab sections follow numbered source-directory order, then name.
- `lab_prefixes`: language-less route prefixes identifying lab lessons.
  Omitted/empty retains the generic `subject/labs/topic` or
  `labs/section/topic` convention. Custom prefixes allow other layouts.
- `last_lessons`: language-less lesson routes placed last within their
  lab subject, for example an assessment.
- `index_labels` and `source_labels`: per-language labels for index links
  and the rendered GitHub source link. English/Russian UI defaults remain.

`slug_overrides` maps exact source paths **below a language root** to
language-less routes, for example
`{"labs/cpp/test1.md": "cpp/labs/assessment-1"}`. It applies to missing
slugs in every language; existing valid slugs are preserved. Section
names belong in `route_sections`, not special cases in the algorithm.
`backlink_labels` optionally overrides the source backlink text per
configured language; English/Russian defaults remain.

## Smoke probes

```json
"smoke": {
  "retries": 30,
  "retry_delay_seconds": 10,
  "timeout_seconds": 30,
  "checks": [
    {"label": "root redirect", "paths": ["/"], "contains": "{root_route}"},
    {"label": "search markup", "paths": ["{root_route}"], "contains": "pagefind"},
    {"label": "search index", "paths": ["/pagefind/pagefind.js", "/_pagefind/pagefind.js"]}
  ]
}
```

The retry values above are defaults. Each check requires HTTP 200 and,
when `contains` is supplied, the expected text in the decoded response.
`paths` are alternatives under the site's base URL: any one may succeed
within the shared retry budget. A missing legacy Pagefind path does not
fail a successful current-path check. Retry counts/timeouts must be
positive integers; retry delay may be zero.

`{root_route}` comes from the configured root lesson's committed slug and
default language. `{repository}` expands to the inferred `OWNER/REPO`,
useful for copied-asset paths. Other lesson/asset routes and expected
text belong in the course's probe list. With no explicit checks, the
three root/search checks above run.

Run `publish.py smoke check --course-repo .`. `--base-url` (or `BASE_URL`)
can point at a local HTTP server for a built site. No course URLs,
specific lesson paths, or titles are embedded in the shared probe code.

## Shared toolchain

The renderer's pinned package versions/lockfile and the Python/Node/browser
constants remain shared implementation choices. `publish.py toolchain show`
exposes these pins and the lockfile-based browser cache key, also writing
step outputs when `GITHUB_OUTPUT` is set. The shared workflow and composite
action consume those outputs; course JSON does not duplicate toolchain
versions. Course workflows retain only triggers, permissions, checkout,
the local shared action call, and GitHub Pages artifact/deploy operations.
