"""Course publishing: configuration, identity, inventory, metadata, links,
projection + site (#7-11).

Stdlib-only. Layout (one module per responsibility, extensible for #12-15):

- :mod:`publishing.config` -- strict version-1 `course-publishing.json`
  parsing (CFG-1) + lexical path safety.
- :mod:`publishing.identity` -- GitHub repo identity from local `origin`
  config only, no network/GH CLI (CFG-5). Default branch is always
  `master` per spec.
- :mod:`publishing.inventory` -- deterministic lesson selection from
  language roots + exact exclusions (CFG-2, CFG-4) with CFG-6
  case-fold/Unicode ambiguity rejection.
- :mod:`publishing.metadata` -- stable slug derivation (META-1..5) +
  source-backlink insert/refresh (META-6) with two-phase safe writes
  (META-4/8) and read-only validation for the check (META-7).
- :mod:`publishing.links` -- deterministic lesson index (LINK-1) +
  relative-link resolution from source locations (LINK-2), query/frag
  preservation (LINK-3), canonical/blob/tree/image rewriting (LINK-4..6),
  strict rejection (LINK-7) and GitHub-anchor validation (LINK-8).
- :mod:`publishing.check` -- read-only `publishing check` handler
  (config + identity + inventory + metadata + links).
- :mod:`publishing.projection` -- deterministic disposable web projection
  (PROJ-1..PROJ-6, #10): backlink strip, H1-preserving heading shift,
  $`code`$ -> $code$ math (PROJ-3 rejects ambiguous), link rewriting via
  links.rewrite_document + image copies, renderer-only sidebar.order +
  nav.json, placeholder astro/mermaid/dist.
- :mod:`publishing.navigation` -- pure Starlight navigation data
  (SITE-2..14 excl Mermaid, #11): humanize, fixed labels, per-locale
  sidebars, lab sequences/pagination, redirects, blob URLs.
- :mod:`publishing.site` -- `site build` handler (#11): projection +
  navigation + pinned Astro/Starlight scaffold (renderer/) + dist/ via
  `npm ci`/`npm run build` (mockable in unit tests).
"""

from __future__ import annotations
