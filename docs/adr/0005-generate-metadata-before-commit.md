# Generate lesson metadata before commit

The maintenance command writes missing lesson slugs and source backlinks before a contributor commits, with an optional pre-commit hook for convenience. CI runs the same operation in check mode and rejects incomplete metadata instead of pushing corrective commits, which keeps changes reviewable and works with fork pull requests and protected branches.
