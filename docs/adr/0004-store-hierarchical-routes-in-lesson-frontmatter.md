# Store hierarchical routes in lesson frontmatter

Every lesson stores an explicit, slash-delimited lesson slug in its frontmatter. The slug includes the language and meaningful course hierarchy, allowing stable nested routes while source files and navigation views evolve independently; maintenance derives a missing slug from the initial source path, writes it to the source document, and rejects collisions.

## Consequences

Ordering prefixes are omitted and path components use lowercase kebab-case. Generic document names may collapse to their parent path. Genuine source-name typos should be corrected during initial migration rather than preserved in newly created public routes.
