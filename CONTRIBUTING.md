# Contributing

Thanks for helping improve MD Split. The app is a native GTK 4/libadwaita
Markdown editor; it must not grow a WebKit/webview dependency or a compiled WASM
runtime.

## Quick start

```sh
meson setup build --prefix="$PWD/build-install"
meson compile -C build
python3 scripts/test.py
meson install -C build
./build-install/bin/md_split examples/demo.md
```

See [README.md](README.md) for requirements and [docs/testing.md](docs/testing.md)
for the test matrix and focused test commands.

## Where changes belong

- Static UI, labels, menus, and bindings: the `.blp` files.
- Runtime behavior, dialogs, and actions: `src/window.py` and `src/main.py`.
- Pure editing logic: `src/editing.py`, with headless tests.
- Markdown parsing: `src/markdown_parser.py` and the renderer in
  `src/renderer.py`; do not add a second parser.
- HTML/PDF export: `src/exporting.py`.
- Settings: `data/io.github.james2doyle.MdSplit.gschema.xml` and the preferences
  dialog.

See [docs/architecture.md](docs/architecture.md) for the module map and data
flow. `AGENTS.md` has repository-specific GTK/Blueprint gotchas and file
indexes.

## Tests and checks

```sh
meson compile -C build
python3 scripts/test.py
uvx pyright src/*.py tests/*.py
uvx ruff check --select E9,F63,F7,F82,F401,I001 \
  --exclude src/vendor src tests scripts dev.py
command -v actionlint >/dev/null && actionlint .github/workflows/*.yml
for file in src/*.blp; do
  blueprint-compiler compile "$file" >/dev/null
  blueprint-compiler lint "$file"
done
```

Add a new Meson test target in `src/meson.build` when adding a new focused test
file. Display tests must exit 77 when no display is available.

## Style

- Keep the Markdown parser GFM-compatible.
- Escape every text fragment with `GLib.markup_escape_text` before Pango markup.
- Wrap user-visible strings with `_()`/`ngettext()` in Python and `_()`/`C_()`
  in Blueprint; add new source files to `po/POTFILES.in`.
- Call `gi.require_version` before importing a GI namespace.
- Keep Meson source lists explicit; no globbing.
- Do not edit generated `build/src/*.ui` files.
- Do not add runtime pip dependencies. Pure-Python Markdown code is vendored
  under `src/vendor/`.
- Do not commit secrets, `.env` files, keys, or tokens.

## Commits and pull requests

- Prefer focused commits with a clear `feat:`, `fix:`, `test:`, `docs:`, or
  `chore:` prefix.
- Do not commit build outputs, `dist/`, Flatpak state, or `__pycache__`.
- Explain behavior changes and include the commands you ran to verify them.
- For UI changes, include a screenshot or describe the visual check.
- For release changes, follow [docs/releasing.md](docs/releasing.md).

## Reporting

For bugs and feature requests, include the version, distribution, display server
(Wayland/X11), GTK/libadwaita version, and steps to reproduce. For security
issues, follow [docs/security.md](docs/security.md) instead of posting exploit
details publicly.
