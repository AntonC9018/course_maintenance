"""Course maintenance: responsibility-focused components (issue #6).

Language: Python 3, standard library only. Kept because maintain.py was
already dependency-free Python, the spec's command surface is
``python3 <course_maintenance>/publish.py ...``, and temp-dir tests need
no toolchain beyond the interpreter.

Layout (one responsibility per module; pipeline order lives in
:mod:`maintenance.pipeline` and must stay rename -> convert ->
headings -> links):

- :mod:`maintenance.patterns` -- shared regexes/prefixes.
- :mod:`maintenance.rename` -- NN_ gap closing (incl. lettered appendices).
- :mod:`maintenance.convert` -- opt-in list -> ``###`` header conversion.
- :mod:`maintenance.headings` -- H1/H3 resequencing.
- :mod:`maintenance.links` -- file/anchor link repair (index built last).
- :mod:`maintenance.pipeline` -- orchestration + path collection.
- ``maintain.py`` (repo root) -- preserved CLI, thin shim over pipeline.
- ``publish.py`` (repo root) -- stable dispatcher for the four spec
  operations (``metadata generate``, ``publishing check``,
  ``projection build``, ``site build``) plus ``ci``; stubbed until
  issues #7-15. Follow-ups add a module here and register one line in
  publish.py -- no logic goes back into a monolith.
"""
