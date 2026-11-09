# Visualization assets

A course may opt into automatic visualization generation while keeping CI independent of compiler,
GDB, and browser installations. Templates and tracing logic remain course-owned.
The maintenance package owns source lookup, minimal updates, upload, and referenced-asset checks.

## Course configuration

Add an optional `visualizations` object to `course-publishing.json`:

```json
{
  "visualizations": {
    "templates": "visualizations",
    "roots": ["en/labs/cpp", "ru/labs/cpp"],
    "manifest": "visualizations/assets.json",
    "repository": "owner/course",
    "issue": 123
  }
}
```

The roots select Markdown files recursively. All paths must be canonical repository-relative paths;
symlinks escaping the repository are rejected. `templates` and `manifest` have the defaults shown.
The repository and positive issue number identify a durable upload issue. Old comments and assets
are retained when a visualization changes. A course without this object has no visualization step.

## Author marker and source lookup

Place a marker inside an answer's `<details>` block, exactly where its media should appear:

````markdown
```cpp
int a{5};
a = 7;
```

<details>
<summary>Answer</summary>

<!-- <visualization type="animation"> -->

<!-- </visualization> -->

</details>
````

`type` is required: `animation` or `static`. `template` may override the automatic/default
`expression-timeline` template. There are no per-example parameters or source hashes.
The source is the nearest preceding code fence outside **all** `<details>` blocks; it must use
`cpp`, `c++`, or `cxx`. A fence inside an answer cannot replace the source example. Markdown fences
also protect HTML-looking strings and comments inside code from changing answer nesting.

After generation, maintenance puts the attachment inside the paired visualization markers.
The opening and closing tags are separate HTML comments, so GitHub can render the link between
them. The URL appears once, in the body; no generated `src` attribute is needed:

```html
<!-- <visualization type="animation"> -->

https://github.com/user-attachments/assets/00000000-0000-0000-0000-000000000000

<!-- </visualization> -->
```

GitHub resolves the bare attachment paragraph to its allowed media host. Raw `<video>` tags
pointing at `github.com` are blocked by GitHub's `media-src` policy in repository documents.
The site projection replaces the entire visualization block with a `<video controls
preload="metadata">` element. Authored documents keep the durable attachment URL; neither signed
media URLs nor rendered media belong in Git. Older single markers with a `src` attribute and an
embed after them are read during migration; generation upgrades them without re-uploading.
Nested visualization blocks, orphan closing markers, and blocks crossing code or `<details>`
boundaries are rejected.

Static media uses `<img alt="" src="...">` inside the same paired markers. Generated media must
remain language-neutral; English and Russian markers referencing identical C++ sources reuse one
attachment. Source fences are
normalized only for line endings, trailing whitespace, and surrounding empty lines.

## Local generation

Preview normal course maintenance first, then apply as usual:

```sh
python3 maintain.py --root <course> --check <edited-files>
python3 maintain.py --root <course> <edited-files>
```

The fixed formatting order remains rename, convert, headings, links. A configured visualization
stage follows links, processing only the selected files. Its check mode reads local metadata only.
To generate all configured tags explicitly:

```sh
python3 publish.py visualizations generate --course-repo <course>
```

Generation compares the exact source, template, media type, and renderer revision with the committed
manifest. Moving a marker or sharing an unchanged source across languages does not render or upload
again. Changing source or renderer revision regenerates its asset. Confirmed missing remote assets
regenerate
as well. Transient access errors retry twice, then retain existing media with a diagnostic;
they never trigger an unnecessary render or upload. Existing manifest entries remain available for
recovery; they are never deleted.

Each successful upload is recorded immediately, so a later failure can resume without repeating it.
Render or upload failure preserves that marker's previous media and returns a diagnostic/nonzero
exit code. No fabricated URL or alternate publishing destination is substituted. Uploads use
`gh issue comment --attach` and body files; recovery fetches the resulting comment through `gh api`.
Comment fetch retries do not repeat a successful upload. The upload and fetch retry counts are
bounded at two attempts, and attachments larger than 100 MiB are rejected.

## Course renderer interface

`<templates>/generate.py` implements three subprocess commands:

```sh
python3 generate.py revision
python3 generate.py probe --source /tmp/snippet.cpp
python3 generate.py render --source /tmp/snippet.cpp --output /tmp/asset.mp4 \
  --type animation --template expression-timeline
```

`revision` prints a nonempty stable renderer revision. `probe` prints JSON with `supported: true`,
or `supported: false` plus `reason`. `render` produces the requested nonempty MP4 or SVG and returns
nonzero on failure. The renderer supplies its own compiler, tracing, and media dependencies.
`probe` and `render` run only in local generation, never in checks or CI.

The version-1 JSON manifest contains an `assets` list. Each entry stores `source`, `template`,
`type`, `src`, and `renderer_revision`; it stores the source itself rather than a source hash.

## Read-only checks

```sh
python3 publish.py visualizations check --course-repo <course>
python3 publish.py publishing check --course-repo <course>
```

Both validate marker placement, source/manifest agreement, managed embeds, and anonymous attachment
availability. URLs are checked once per invocation with HTTP HEAD; a server rejecting HEAD gets a
one-byte range GET fallback. Missing assets and stale sources fail with path/line diagnostics.
These checks never invoke a renderer, compiler, browser, upload command, or source-writing step.
`publishing check` includes this validation automatically, so existing course CI callers need no new
job or media dependencies. CI does not regenerate media or compare renderer revisions.
