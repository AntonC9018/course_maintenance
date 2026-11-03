# Visualization toolchain

Local-only renderer toolchain for the C++ memory/pointer visualizations. It is
kept out of the stdlib-only maintenance core: nothing under `maintenance/` or
`publishing/` imports Manim, and CI never installs or runs it.

This directory is the maintenance-side toolchain only. Course-specific scene
code and templates live in the course repo's `visualizations/` directory.
Plain SVG static visuals need neither Manim nor LaTeX; only animations use this
stack.

- `requirements.txt` pins Manim and every transitive Python dependency.
- `system-packages.txt` is the Debian/Ubuntu package set for the native and
  LaTeX dependencies.
- `smoke.py` is the headless proof scene. It uses `MathTex`, so it exercises
  LaTeX and `dvisvgm`, then `ffmpeg` for the MP4.
- The venv lives at `course_maintenance/.venv` and is ignored by git.

## Fresh machine (Ubuntu/Debian)

```sh
cd course_maintenance
sudo apt-get update
sudo apt-get install -y $(grep -v '^#' visualizations/system-packages.txt | xargs)

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r visualizations/requirements.txt

.venv/bin/manim --version
latex --version
dvisvgm --version
ffmpeg -version | head -1
```

## TinyTeX instead of TeX Live

When system packages cannot be installed, use a user-space TinyTeX. The package
names differ from the TeX Live collection names:

```sh
curl -fsSL https://yihui.org/tinytex/install-bin-unix.sh | sh
tlmgr install standalone preview babel babel-english amsmath amsfonts \
  doublestroke jknapltx setspace tipa ragged2e calligra wasysym physics \
  microtype xcolor pgf tools dvisvgm
tlmgr path add
```

`doublestroke` provides `dsfont.sty`; `jknapltx` provides `mathrsfs.sty`.
`tlmgr path add` must be rerun after installing new binaries such as `dvisvgm`.

## Proof render

```sh
cd course_maintenance
.venv/bin/manim -ql --format=mp4 --media_dir /tmp/manim-smoke \
  visualizations/smoke.py Smoke
MP4=$(find /tmp/manim-smoke -name '*.mp4' | head -1)
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height \
  -of default=noprint_wrappers=1 "$MP4"
ffmpeg -v error -i "$MP4" -f null - && echo 'decode: OK'
```

Measured on Ubuntu, Python 3.14.4, Manim 0.22.0, TeX Live 2026 (TinyTeX):

- Python venv: about 481 MB.
- TinyTeX: about 221 MB (51 MB download plus packages).
- Combined disk: about 700 MB. The apt TeX Live route is larger because
  `texlive-latex-extra` pulls a broad package set; TinyTeX is the measured
  minimal route.
- Cold Python install: a few minutes; many dependencies build from source.
- TinyTeX download + package install: about 1-2 minutes on a fast link.
- Smoke render: about 5 seconds at 480p15; the MP4 is about 18 KB for 1.5 s.

## Version policy

- Bump `requirements.txt` and the TinyTeX/TeX package lists together, then rerun
  the proof render and inspect the output. Regenerate the lock with
  `.venv/bin/pip freeze | sort` after a deliberate upgrade.
- Keep Manim pinned exactly; do not use a range.
- Python 3.14.4 is the tested interpreter; Manim 0.22 requires Python 3.11+.
  The lock includes `audioop-lts` for Python 3.13+.
- CI needs only Python 3.12 for `maintain.py` and `publish.py`. It must never
  install Manim, TeX, or a browser to validate visualizations. The most CI may
  do is check that referenced asset files exist.
