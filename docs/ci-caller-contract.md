# Shared CI caller contract (issue #14, for #13/#15 and C# reuse)

This document defines the minimal workflow a course repository must
provide. The shared implementation lives in `course_maintenance`; course
repos own only a thin GitHub Actions workflow that checks out its pinned
submodule and invokes one stable command.

## Stable command

```sh
python3 course_maintenance/publish.py ci --course-repo .
```

Run from the course-repository root with `course_maintenance` checked out
as a submodule (or any checkout at a pinned revision). It works from a
clean checkout with the submodule present; it never fetches a reusable
workflow independently of the submodule revision (CI-2).

In order, it runs (CI-1):

1. existing course-maintenance checks (`maintain.py --check` semantics);
2. publishing checks (`publishing check`: config, content, metadata,
   links, assets);
3. the shared compatibility suite (`tests.test_compatibility`, isolated
   temp-dir fixtures);
4. a complete static site build (`site build` to a disposable directory
   outside the course repo, pinned Astro Starlight + Playwright/Chromium
   toolchain, `dist/` suitable for a Pages artifact).

Read-only wrt sources, actionable failures (source path + rule +
corrective operation), reliable exit codes: 0 success, 1 validation or
build failure, 2 usage error (bad `--course-repo` or `--out` inside
sources). CI never writes or commits source metadata (CI-5).

## Caller workflow

Copy `docs/ci-caller-workflow.yml` to
`.github/workflows/course-site.yml` in the course repo. It:

- checks out the course with `submodules: recursive` at the committed
  `course_maintenance` revision (CI-6);
- sets up the pinned Python 3.12 and Node 22 runtimes (see
  `publishing/ci.py` `PINNED_PYTHON`/`PINNED_NODE`);
- restores npm + Playwright/Chromium caches keyed by
  `renderer/package-lock.json` and the pinned browser versions, then runs
  `npm ci` + `playwright install chromium` from the submodule;
- invokes the stable command above with `--course-repo .`.

The fixture pins all third-party actions to immutable commit SHAs with
version comments (CI-8), uses no path filters (CI-5), confines
pull-request validation to `contents: read` (CI-9, never deploys on PR,
CI-3), and applies concurrency that discards superseded runs so an older
run cannot deploy after a newer master revision (CI-10).

## Caches (CI-8)

Pinned sources of truth (single place each):

- renderer/npm: `renderer/package.json` + committed
  `renderer/package-lock.json` (exact versions, see
  `publishing/site.py` `PINNED_VERSIONS` and `renderer/README.md`);
- browser: Playwright 1.48.2 + Chromium 130.0.6723.19 (see
  `publishing/site.py` `PINNED_BROWSERS`, installed via
  `npx playwright install chromium`);
- runtimes: Python 3.12, Node 22 (see `publishing/ci.py`).

Safe cache keys (see `publishing/ci.py` `npm_cache_key()` /
`browser_cache_key()`, exercised by `tests/test_ci.py`):

- npm: `npm-<platform>-node-22-lock-<sha16(package-lock.json)>`;
- browsers: `playwright-<playwright>-chromium-<chromium>-<sha(package-lock.json)>`
  (workflow `hashFiles('course_maintenance/renderer/package-lock.json')`).

Caches hold runtimes/dependencies only and can never substitute outputs
from a different lockfile or browser/toolchain version. Source metadata,
projections, and deployable output are never cached as authoritative
results.

## What stays where

- `course_maintenance` owns: maintenance checks, publishing validation,
  compatibility testing, dependency setup, complete site build
  orchestration, pinned versions + lockfiles, shared CI config
  (`.github/workflows/ci.yml`), and this contract.
- Course repos own: the thin caller workflow above, `course-publishing.json`,
  Markdown sources + committed slugs/backlinks, and the submodule pointer.
  Deployment (Pages artifact, `github-pages` environment, post-deploy
  smoke tests) is issue #15 and reuses the same pins, permissions, and
  concurrency.

## Reuse

- Data-structures rollout (#15): copy the fixture workflow, commit the
  `course_maintenance` submodule pointer at the reviewed revision, require
  the validation status for ordinary pull-request merges (CI-12, repo
  settings), keep GitHub Actions as the Pages source with admin bypass
  for direct master commits.
- C# course: same fixture and command; only `course-publishing.json`
  (language roots, route sections, titles, root lesson) and sources
  differ. No peer-repository checkout in the initial release (CI-7);
  peer automation is deferred until a rollout needs it.
