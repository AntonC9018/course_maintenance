# Build sites from web projections

Course sites are built from ephemeral web projections while the original Markdown remains the authoring source of truth. This preserves repository-relative links for GitHub and editors while allowing the website build to route lesson links through stable web identities, route code and directories to GitHub, and omit the source-only website backlink.

## Consequences

The publishing pipeline must validate the source documents and produce projections deterministically. Generated projections are build artifacts and are not committed.
