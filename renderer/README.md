# Renderer scaffold (issues #11-12, SITE-1 + DIAG-1..DIAG-4)

Reusable Astro/Starlight scaffold for course sites. The per-course build
(`python3 publish.py site build --course-repo <repo> [--out <dir>]`)
copies this scaffold's dependency lock and generates a per-course
`astro.config.mjs` (site/base/locales/titles/sidebar/redirects/math/
Pagefind/editLink, no Mermaid client JS) plus `src/content.config.ts` and
localized `src/content/i18n/*.json` (View on GitHub labels). Mermaid fences
are pre-rendered to static SVGs (inline + `mermaid/*.svg` + mirrored
`public/mermaid/*.svg` for `dist/`); no Mermaid client bundle is shipped.

## Pinned versions (exact, no ranges)

Proven by the compatibility suite (representative lessons: nested
`<details>`, raw C++ angle brackets, `$`code`$`/`$$` math, both real
`flowchart LR` Mermaid diagrams, tables, images, nested routes, rewritten
links, Pages project base):

- `astro` 7.3.2
- `@astrojs/starlight` 0.42.1 (requires `astro ^7.2.10`)
- `@astrojs/markdown-remark` 7.3.1
- `remark-math` 6.0.0
- `rehype-katex` 7.0.1
- `katex` 0.16.47 (satisfies `rehype-katex`'s `^0.16.0`; latest `0.18.x`
  does not satisfy that range)
- `mermaid` 10.9.3 (static SVG rendering, DIAG-1; needs `katex ^0.16.9`,
  satisfied by 0.16.47)
- `playwright` 1.48.2 (headless Chromium driver, DIAG-1)
- Chromium `130.0.6723.19` (bundled with playwright 1.48.2, DIAG-1;
  installed via `npx playwright install chromium`; pinned here for CI
  cache keys per CI-8, never cached as authoritative output)

`package-lock.json` is committed alongside `package.json`. `site build`
runs `npm ci` (when `node_modules` is missing) then `npm run build`
inside the disposable output directory. `public/.nojekyll` is emitted per
build so Pagefind's `_pagefind/` survives GitHub Pages (Jekyll bypass).

## Mermaid static rendering (DIAG-1..DIAG-4)

- `render-mermaid.mjs` renders one diagram (stdin) to static SVG (stdout)
  inside headless Chromium via Playwright using the local
  `mermaid/dist/mermaid.min.js` bundle (no CDN). Exit 0 SVG, 2 diagram
  syntax failure (diagnostic on stderr, surfaced with source path per
  DIAG-2), 1 toolchain missing (Python falls back to a deterministic
  placeholder SVG offline; unit tests mock this seam).
- Render id is always `mermaid-static-<idx>` and Python normalizes residual
  `mermaid-*`/UUID/hex ids (DIAG-4) so repeat builds are byte-identical.
- Projected Markdown embeds the SVG inline inside
  `<div class="mermaid-static">`; the same bytes are written to
  `mermaid/<flat-slug>-<idx>.svg` and mirrored to `public/mermaid/` for
  `dist/` smoke tests. No `<script>`/client bundle is emitted (DIAG-3);
  `publishing.mermaid.check_no_mermaid_client_js` fails the build when
  forbidden tokens (`mermaid.min.js`, `mermaid.initialize/run`, CDN/unpkg,
  `import ... from "mermaid"`) appear. Generated SVGs are disposable and
  never committed.

## Offline behavior

Unit tests never invoke npm or browsers (they mock `run_npm_build` and
`render_via_toolchain` and assert generated config/sidebar/pagination/SVG).
`site build` requires the pinned toolchain: with network it runs `npm ci`
deterministically from the lock; without npm/network it exits nonzero with
a clear `SITE-1` error after writing the projection + config for inspection
(no guessing, no partial `dist/` committed). `dist/` is disposable build
output, never committed.
