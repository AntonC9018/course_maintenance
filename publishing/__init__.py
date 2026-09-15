"""Course publishing: configuration, identity, inventory, metadata, links (#7-9).

Stdlib-only. Layout (one module per responsibility, extensible for #10-15):

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
  (config + identity + inventory + metadata + links). Future issues add
  projection (#10-11), site (#12-13), CI (#14) without touching this
  model: import LessonInventory / PublishingConfig and extend.
"""

from __future__ import annotations
