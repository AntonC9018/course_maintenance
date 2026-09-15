# Publish one site per course repository

Each course repository owns and independently deploys its own GitHub Pages project site. This keeps builds and permissions isolated and avoids making one aggregator coordinate every course release; cross-course navigation is handled through stable links between course sites.

## Considered Options

- A single aggregate site would offer one URL namespace, but every course change would require cross-repository coordination and deployment access.
- Independent project sites add a repository segment to URLs, but keep each course autonomous and fit GitHub Pages' project-site model.
