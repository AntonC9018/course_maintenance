# Renderer scaffold (issue #11, SITE-1)

Reusable Astro/Starlight scaffold for course sites. The per-course build
(`python3 publish.py site build --course-repo <repo> [--out <dir>]`)
copies this scaffold's dependency lock and generates a per-course
`astro.config.mjs` (site/base/locales/titles/sidebar/redirects/math/
Pagefind/editLink) plus `src/content.config.ts` and localized
`src/content/i18n/*.json` (View on GitHub labels).

## Pinned versions (exact, no ranges)

Proven by the compatibility suite (representative lessons: nested
`<details>`, raw C++ angle brackets, `$`code`$`/`$$` math, Mermaid
placeholders, tables, images, nested routes, rewritten links, Pages
project base):

- `astro` 7.3.2
- `@astrojs/starlight` 0.42.1 (requires `astro ^7.2.10`)
- `remark-math` 6.0.0
- `rehype-katex` 7.0.1
- `katex` 0.16.47 (satisfies `rehype-katex`'s `^0.16.0`; latest `0.18.x`
  does not satisfy that range)

`package-lock.json` is committed alongside `package.json`. `site build`
runs `npm ci` (when `node_modules` is missing) then `npm run build`
inside the disposable output directory. `public/.nojekyll` is emitted per
build so Pagefind's `_pagefind/` survives GitHub Pages (Jekyll bypass).

## Offline behavior

Unit tests never invoke npm (they mock `run_npm_build` and assert
generated config/sidebar/pagination). `site build` requires the pinned
toolchain: with network it runs `npm ci` deterministically from the lock;
without npm/network it exits nonzero with a clear `SITE-1` error after
writing the projection + config for inspection (no guessing, no partial
`dist/` committed). `dist/` is disposable build output, never committed.
