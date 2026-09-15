# Use Astro Starlight to render course sites

Course sites use Astro Starlight because it provides documentation navigation, multilingual content, and free local search while shipping little client-side JavaScript by default. Docusaurus offers stronger built-in handling of source-relative Markdown links and easier React-heavy interactivity, but the web-projection pipeline must already resolve cross-repository links and the initial release does not include interactive course state; Hugo would require assembling more of the documentation experience ourselves.

## Consequences

Implementation begins with a compatibility spike covering the course corpus's nested details blocks, raw angle-bracket text, math, Mermaid, links, and assets. A serious incompatibility may reopen this decision before the renderer is put into production.
