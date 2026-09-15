# Generate lesson metadata before commit

An explicit local metadata-generation operation writes missing lesson slugs and source backlinks before a contributor publishes the site, with an optional pre-commit hook for convenience. Routine maintenance does not generate publishing metadata as a side effect. CI validates the committed metadata, rejects missing or stale values with regeneration instructions, and never pushes corrective commits; this keeps changes reviewable and works with fork pull requests and protected branches.
