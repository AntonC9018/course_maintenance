# Visualizations

A course may tag C++ examples for compiler-backed execution traces.
The course owns the tracer and its toolchain: a `generate.py` adapter and a Nix flake dev shell.
The maintenance package owns tag lookup, the trace store, and the CI steps that fill it.

## Course configuration

Add an optional `visualizations` object to `course-publishing.json`:

```json
{
  "visualizations": {
    "templates": "visualizations",
    "roots": ["en/labs/cpp", "ru/labs/cpp"],
    "shell": "visualizations",
    "traces": ".cache/visualizations",
    "labels": {"layout": {"en": "▶ Explore this layout on the course site"}}
  }
}
```

- `roots` select Markdown files recursively and are required.
- `templates` is the directory that holds `generate.py`.
- `shell` names a dev shell of the flake at the course root (`nix develop .#<shell>`).
- `traces` is the generated trace directory; add it to `.gitignore`.
- `labels` overrides the site-link label for tags with a `template` override, per language.
  Other tags and unlisted languages keep the built-in step-through label.

All paths must be canonical repository-relative paths; symlinks escaping the repository are
rejected. The other fields default to the values shown, and `labels` to none.
A course without this object has no visualization step.

## Tags and source lookup

Place a tag inside a `<details>` block after the example, where its player should appear:

````markdown
```cpp
int a{5};
a = 7;
```

<details>
<summary>Execution trace</summary>

<!-- <visualization> -->

<!-- </visualization> -->

</details>
````

The opening and closing markers are separate HTML comments, so a body between them renders on
GitHub. Maintenance owns that body (see below).
Write `<!-- <visualization template="name"> -->` only when the tracer's own template choice is
wrong; there are no other attributes or per-example parameters.

The source is the nearest preceding code fence outside **all** `<details>` blocks; it must use
`cpp`, `c++`, or `cxx`. A fence inside an answer cannot replace the source example. Markdown fences
also protect HTML-looking strings and comments inside code from changing answer nesting.

## Site links and players

`metadata generate` writes each tag's body: a localized link to the same example on the site, at the
nearest preceding heading's anchor, so a GitHub reader can open the player.

```markdown
<!-- <visualization> -->

[▶ Step through this example on the course site](https://owner.github.io/course/en/lesson/#4-heading)

<!-- </visualization> -->
```

`publishing check` requires the body to be exactly that link. Anchors follow Astro: smartypants
dashes, then github-slugger, including `-1` suffixes for repeated headings. After a real build,
`site build` also checks every link's page and heading id against the generated HTML.

The site projection replaces each tag, link included, with one raw-HTML line embedding its trace:

```html
<div class="course-visualization"><script type="application/json">…</script></div>
```

The course's own player renders it; ship it through `site_assets`
(see [course configuration](course-configuration.md)).

## Traces

A trace is stored at `<traces>/<key>.json`. The key hashes the normalized snippet, the template
override and the tracer revision, which the course computes over its tracer sources and its
`flake.lock`. Languages that share a snippet therefore share a trace, and a moved tag keeps it.

```sh
nix develop .#visualizations --command \
  python3 course_maintenance/publish.py visualizations generate --course-repo .
python3 course_maintenance/publish.py visualizations check --course-repo .
```

- `generate` traces every tag without a stored trace, then prunes traces no tag uses.
  Given selected files, it traces only those and prunes nothing.
- A tag that fails to trace is an error naming its lesson and line; nothing is stored for it.
- `check` runs no tracer. It reports malformed tags and tags without a trace.
- `maintain.py` checks tag syntax only, so it needs no toolchain.
- `publishing check`, and therefore CI, requires every trace; the projection embeds them.

## The adapter contract

`generate.py` (or `generate.mjs`) runs as a separate process with these operations:

- `revision` prints a nonempty identifier that changes whenever traces could change.
- `trace --source <file> [--template <name>]` prints the trace as JSON, or exits nonzero with the
  reason on standard error.

## CI

`ci prepare` reports whether the course configures visualizations, and exposes the dev shell
reference, the trace directory, and one key for the whole trace set.
When it does, the shared action:

1. installs Nix and enables the Magic Nix Cache for the toolchain's store paths;
2. restores the trace directory from `actions/cache`, falling back to the newest older set;
3. runs `visualizations generate` inside the dev shell, tracing only what changed.

A failed trace fails the build before validation. Traces are build inputs, never committed.
