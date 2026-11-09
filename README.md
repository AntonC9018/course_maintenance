# course_maintenance

Shared maintenance, publishing, CI, and deployment checks for course
repositories. Python tooling uses only the standard library. Source
formatting remains in `maintenance/`; publishing and deployment modules
live in `publishing/`. `maintain.py` and `publish.py` are thin dispatchers.

```sh
python3 maintain.py --check <paths>
python3 publish.py metadata generate --course-repo <repo>
python3 publish.py publishing check --course-repo <repo>
python3 publish.py projection build --course-repo <repo> --out <outside-dir>
python3 publish.py site build --course-repo <repo> --out <outside-dir>
python3 publish.py ci --course-repo <repo> --out <outside-dir>
python3 publish.py smoke check --course-repo <repo>
python3 publish.py pages verify --course-repo <repo> --strict
python3 publish.py toolchain show
python3 publish.py visualizations generate --course-repo <repo>
python3 publish.py visualizations check --course-repo <repo>
python3 -m unittest discover -s tests
```

Course-specific policy lives in each course's `course-publishing.json`.
See `docs/course-configuration.md` for CI scope, optional tooling tests,
navigation, deployment, and smoke probes. `docs/ci-caller-contract.md`
and `docs/ci-caller-workflow.yml` describe the pinned integration.

The composite action `.github/actions/course-ci` owns dependency setup,
cache keys, PR readiness, and validation/build orchestration. Course
workflows call it from their committed submodule checkout and keep only
GitHub triggers, permissions, artifact upload, and deployment.

Maintenance preserves the fixed order rename → convert → headings →
links. Preview before applying; follow `AGENTS.md`. Tests use isolated
temporary course fixtures and do not mutate real course sources.

Visualization rendering is local-only; CI never installs a renderer.
The optional [visualization integration](docs/visualization-assets.md) renders
tagged examples locally, reuses shared assets, and checks referenced
attachments in CI.
