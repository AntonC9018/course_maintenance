# Course Publishing

Course publishing turns the teaching material kept in course repositories into navigable websites without making the website format the authoring format.

## Language

**Course repository**:
A repository containing the source material for one course and owning one independently deployed course site.
_Avoid_: Documentation repository, website repository

**Course site**:
The public website published from one course repository. Other course sites may link to it, but do not own or deploy its lessons.
_Avoid_: Portal, aggregate site

**Content configuration**:
The repository-owned selection of language content roots and explicit inclusion or exclusion patterns that determines which Markdown source documents are lessons.
_Avoid_: Lesson manifest, website configuration

**Lesson**:
A Markdown source document selected for publication by a course repository's content configuration. A lesson may be incomplete, empty, or presentation-oriented.
_Avoid_: Page, article

**Lesson slug**:
The stable, language-prefixed hierarchical identity of a lesson within its course site. It determines the canonical lesson route independently of the source document's location.
_Avoid_: Filename, source path, generated path

**Lesson title**:
The concise, language-appropriate display name stored with a lesson and used by website navigation. It describes the lesson rather than its repository position or sequence number.
_Avoid_: Filename, navigation label

**Source document**:
The repository-readable Markdown file that authors edit and that remains the source of truth for a lesson.
_Avoid_: Website Markdown, generated document

**Web projection**:
The website-facing form of a source document. It may adapt links and suppress source-only elements without changing what authors read and edit in the course repository.
_Avoid_: Source document, generated source

**Navigation view**:
A curated way of discovering a subset of lessons, such as the C++ or data-structures material. Absence from a view does not restrict direct access to a lesson.
_Avoid_: Access level, permission, locked content

**Lab sequence**:
The ordered progression through a course site's lab lessons. It can cross sidebar groups and therefore does not define the ordering of non-lab material.
_Avoid_: Navigation view, sidebar order

**Source backlink**:
The source-only link labelled "This lesson on the website" that takes a repository reader to the lesson's canonical route. It is not part of the web projection.
_Avoid_: Canonical link, navigation link
