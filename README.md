# MD Split

A native GNOME Markdown editor with a live, GitHub-Flavored Markdown preview.

![MD Split showing the editor and native preview](docs/screenshot.png)

MD Split is built with GTK 4, libadwaita and GtkSourceView. The preview is a
real GTK widget tree — headings are labels, tables are `Gtk.Grid`s, task lists
are check buttons, code blocks are selectable monospace labels, and images are
`Gtk.Picture`s. There is no WebKit, no embedded browser and no web runtime.

Markdown parsing is done by [markdown-it-py](https://github.com/executablebooks/markdown-it-py)
with its composite GFM plugin. Both are vendored under `src/vendor`, so the app
has no runtime Python dependencies beyond PyGObject.

## Features

- Split view with a GtkSourceView editor and a native live preview
- GitHub-Flavored Markdown: tables, strikethrough, autolinks, task lists,
  alerts and footnotes
- Native rendering for headings, paragraphs, links, lists, block quotes,
  fenced and indented code blocks, tables, images and horizontal rules
- System, light and dark appearance with system as the default
- Optional bundled demo document when opening without a file
- Synchronized editor/preview scrolling
- Selection wrapping for brackets, braces, backticks and quotes
- Automatic `[]` to `[]()` completion for links
- Bold, italic, underline, block quote and code formatting shortcuts
- Standalone HTML and styled PDF export
- Open, save and save-as with UTF-8 files
- Unsaved-change prompts, window geometry and preview state persistence
- Word and character counts plus cursor position in the status bar
- Copy-code buttons in code block headers
- Command-line file opening and `%f` desktop integration
- Raw HTML is disabled by default for safe previewing; `<u>...</u>` is the
  only inline HTML tag rendered as formatting

## Requirements

- Python 3.12+ and PyGObject (`Gtk-4.0`, `Adw-1`, `GtkSource-5` GIRs)
- GTK 4 and libadwaita 1.8+ (the Flatpak runtime provides 1.10)
- GtkSourceView 5
- Pycairo for PDF export
- `meson`, `ninja`, `blueprint-compiler`
- `gettext` (`msgfmt`); optional validators: `desktop-file-validate`,
  `appstreamcli`, `glib-compile-schemas`
- `flatpak` and `flatpak-builder` for packaging

The Markdown parser is vendored; install no parser packages.

## Build and run

```sh
meson setup build --prefix="$PWD/build-install"   # once
meson compile -C build
python3 scripts/test.py
meson install -C build
./build-install/bin/md_split
```

Open a document from the command line:

```sh
./build-install/bin/md_split examples/demo.md
```

The launcher hard-codes the install prefix, so uninstalled runs need the
`build-install` prefix and the `meson install` step. It also adds that prefix
to `GSETTINGS_SCHEMA_DIR` and `XDG_DATA_DIRS`, so schemas and icons resolve
without extra environment setup.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+N | New document |
| Ctrl+O | Open |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| F9 | Toggle preview |
| Ctrl+B | Bold |
| Ctrl+I | Italic |
| Ctrl+U | Underline |
| Ctrl+T | Block quote |
| Ctrl+` | Code |
| Ctrl+, | Preferences |
| Ctrl+? | Show shortcuts |
| Ctrl+Q | Quit |

## Markdown support

The preview uses the composite GFM plugin from `mdit-py-plugins`:

- CommonMark blocks and inline syntax
- Tables with per-column alignment
- Strikethrough with `~~` (and single tildes)
- GFM autolinks for bare `http://`, `https://`, `www.` and email addresses
- Task lists with disabled check boxes in the preview
- GitHub alerts (`> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`,
  `[!CAUTION]`)
- Footnotes and block quotes
- Fenced code blocks with language labels and copy buttons
- Local and remote images
- Underline with `<u>...</u>` (the only inline raw HTML tag interpreted)

Relative links and images are resolved against the open document's directory.
Local images are decoded asynchronously with size and pixel limits. Remote
images are disabled by default: enable **Load Remote Images** in the main menu
or Preferences to fetch public HTTP(S) images, subject to byte, pixel, timeout,
and cache limits.

## Export

**Export HTML…** writes a standalone HTML document with embedded CSS. Local
images are embedded as bounded data URIs, remote images keep their URLs, and
relative links are resolved against the source document. **Export PDF…** uses
Cairo and Pango to write a styled A4 PDF with headings, lists, quotes, code,
tables, local images and footnotes. Export uses the current editor contents,
including unsaved changes.

## Architecture

```text
src/main.py             Adw.Application, actions, CSS loading, file activation
src/window.py           split-view window, file I/O, dialogs, settings
src/document.py         headless document model (text, file, dirty state)
src/fileio.py           headless async UTF-8 load/save helpers
src/editing.py          selection wrapping, link completion, formatting edits
src/exporting.py        standalone HTML and styled PDF export
src/markdown_parser.py  shared GFM parser configuration
src/renderer.py         Markdown tokens -> native GTK widgets
src/markdown_view.py    scrollable preview, empty state, theme rerendering
src/preferences.py      settings-backed preferences dialog
src/preferences-dialog.blp  preferences UI
src/window.blp          Blueprint UI
src/style.css           preview table, code block, alert, quote styling
src/vendor/             vendored markdown-it-py, mdit-py-plugins and mdurl
tests/                  document, renderer and window smoke tests
```

The renderer is deliberately a standard GTK widget tree rather than a custom
canvas. That keeps text selectable, links clickable and styling theme-aware
with normal Adwaita CSS classes and a small app stylesheet.

## Tests

```sh
python3 scripts/test.py
```

The wrapper removes stale test logs and runs Meson with a sanitized
environment so API keys and tokens are not copied into `build/meson-logs`.
No app process is needed. Most tests run completely headless:

- document model and dirty-state logic
- Markdown parsing and Pango markup generation
- asynchronous UTF-8 file loading and saving
- editing helpers, selection wrapping, and link completion
- HTML and PDF export, including pagination
- desktop/AppStream/schema validators

GUI tests construct widgets and application actions in-process (not a running
app) to inspect the preview tree, window lifecycle, keyboard focus, scroll
sync, formatting, preferences, and remote-image policy. They skip themselves
when no display is available; CI runs them under Xvfb.

## Flatpak

```sh
flatpak-builder --user --install --force-clean build-flatpak com.james2doyle.MdSplit.json
flatpak run com.james2doyle.MdSplit
```

The manifest builds from the working tree and allows network access so remote
Markdown images can load when explicitly enabled. Flathub packaging requires
the public repository and the `v0.1.0` tag referenced by the AppStream
screenshot; use a commit-pinned source archive for release builds rather than
the development manifest's working-tree source.

## Third-party licenses

- The app is MIT licensed; see `COPYING`.
- `markdown-it-py`, `mdit-py-plugins` and `mdurl` are MIT licensed; their
  license texts are in `src/vendor/LICENSES/`.
