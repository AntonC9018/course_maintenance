"""Read-only `publishing check` handler (issues #7-9: CFG + META + LINK).

Validates configuration, selected content, repo identity, route-mapping
uniqueness, committed lesson metadata (slugs + source backlinks), and
lesson links/assets without writing source files. Returns 0 on success,
1 on any validation error. Usage errors (bad --course-repo) are handled
by the publish.py dispatcher (exit 2) before this runs.

Extensibility: future issues (#10-15) add projection stages as new
functions called in order here; keep this handler read-only and keep
error format (source path + rule + corrective operation).

Error format: `<config or source path>: [RULE] <what> ; <fix + operation>`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .config import ConfigError, load_config
from .identity import IdentityError, infer_identity
from .inventory import InventoryError, build_inventory


def run_publishing_check(course_repo: Path, args) -> int:
    """Handler(course_repo, args) -> int for publish.py registry."""
    _ = args
    repo = Path(course_repo).resolve()
    try:
        config = load_config(repo)
        identity = infer_identity(repo)
        inventory = build_inventory(repo, config)
    except (ConfigError, IdentityError, InventoryError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # defensive: still read-only, still nonzero
        print(f"error: publishing check failed for {repo}: {e}",
              file=sys.stderr)
        return 1

    try:
        from .metadata import validate_all_metadata
        meta_errors = validate_all_metadata(
            repo, config, inventory, identity.pages_url)
    except Exception as e:  # defensive: still read-only, still nonzero
        print(f"error: publishing check failed for {repo}: {e}",
              file=sys.stderr)
        return 1
    if meta_errors:
        for msg in meta_errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    try:
        from .projection import validate_all_h1
        h1_errors = validate_all_h1(repo, inventory)
    except Exception as e:  # defensive: still read-only, still nonzero
        print(f"error: publishing check failed for {repo}: {e}",
              file=sys.stderr)
        return 1
    if h1_errors:
        for msg in h1_errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    try:
        from .links import LinkError, validate_all_links
        from .metadata import collect_metadata_state
        final, collect_errors, _missing = collect_metadata_state(
            repo, config, inventory, identity.pages_url)
        if collect_errors:
            for msg in sorted(collect_errors):
                print(f"error: {msg}", file=sys.stderr)
            return 1
        link_errors = validate_all_links(
            repo, config, identity, inventory, final)
    except LinkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # defensive: still read-only, still nonzero
        print(f"error: publishing check failed for {repo}: {e}",
              file=sys.stderr)
        return 1
    if link_errors:
        for msg in link_errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    counts = inventory.count_by_language()
    per_lang = ", ".join(
        f"{n} {code}" for code, n in sorted(counts.items()))
    print(f"publishing check: OK ({inventory.total()} lessons"
          + (f": {per_lang}" if per_lang else "")
          + f"; repo {identity.owner}/{identity.repo}"
          + f"; Pages {identity.pages_url}"
          + f"; branch {identity.default_branch})")
    return 0
