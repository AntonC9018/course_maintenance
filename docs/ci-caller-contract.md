# Shared CI caller contract

Course repositories own content and `course-publishing.json`; the pinned
`course_maintenance` submodule owns validation, dependency setup, renderer
pins, smoke checks, and Pages-settings verification. The C# and
data-structures rollout (#15) use the same implementation.

## Stable commands

```sh
python3 course_maintenance/publish.py ci --course-repo . --out /tmp/course-site
python3 course_maintenance/publish.py smoke check --course-repo .
python3 course_maintenance/publish.py pages verify --course-repo . --strict
```

CI runs configured document maintenance, publishing validation, optional
compatibility tests, and the full site build in that order, failing fast.
Sources remain read-only; build output must be outside the course repo.
Exit codes are 0 success, 1 validation/build failure, 2 bad CLI/output
location. Both course repos disable compatibility tests; the shared repo
runs its own unit/compatibility fixtures.

The caller workflow uses the composite action
`./course_maintenance/.github/actions/course-ci`. It validates configuration
and PR readiness before expensive setup, reads shared runtime/browser pins,
restores lockfile-keyed npm/browser caches, installs dependencies, and
invokes the stable CI command. Its version is exactly the committed
submodule pointer: there is no independently fetched reusable workflow.
Caches contain dependencies/runtimes, never authoritative source or build
output. See `course-configuration.md` for the complete JSON contract.

## GitHub Actions integration

`ci-caller-workflow.yml` provides a complete pinned checkout/validate/
upload/deploy/smoke example. Caller workflows own GitHub triggers and
permissions. Validation is read-only; Pages write/id-token permissions
belong to the deploy job. PRs do not upload or deploy. Concurrency cancels
superseded runs so older revisions cannot replace newer deployments.
Workflow branch filters must match `deployment.branch` in the JSON.

Post-deploy smoke jobs check out the committed submodule too, then invoke
`publish.py smoke check`. Public URLs and representative lesson/asset
checks come from configuration and repository identity. No peer checkout
is required. Settings verification is read-only; it never changes branch
protection or Pages settings.
