# Architecture

MD Split is a native GTK 4 and libadwaita Markdown editor. It deliberately has
no WebKit, embedded browser, web runtime, or compiled WASM assets. The preview
is a tree of ordinary GTK widgets. The renderer is deliberately a standard GTK
widget tree rather than a custom canvas: text stays selectable, links stay
clickable, and styling stays theme-aware with normal Adwaita CSS classes and a
small app stylesheet.

## Module map

| Module | Responsibility |
| --- | --- |
| `src/main.py` | `Adw.Application`, actions, CLI options, icon loading, file activation, session restore, recent files, recovery prompts |
| `src/window.py` | Window layout, `GtkSource.Buffer`, file dialogs, save queue, preview scheduling, scroll sync, search, autosave, file monitoring, spell-check adapter, threaded exports |
| `src/document.py` | Headless document model: file, text, saved text, dirty state, ETag, counts |
| `src/fileio.py` | Headless async UTF-8 load/save, 64 MiB input bound, worker-thread decode, atomic replacement |
| `src/filechanges.py` | External file-event classification and prompt decisions |
| `src/recovery.py` | Recovery drafts, state directories, and bounded timestamped backups |
| `src/session.py` | Session path pruning, deduplication, and recent-file ordering |
| `src/spellcheck.py` | Optional libspelling backend, language discovery and fallback |
| `src/editing.py` | Pure `TextEdit` helpers: wrapping, link completion, formatting, list continuation, search, and replace-all |
| `src/formatting.py` | Pure Markdown source normalizer: headings, lists, block quotes, fences, tables, blank lines and diff summaries |
| `src/markdown_parser.py` | Shared `markdown-it-py` + GFM parser configuration |
| `src/renderer.py` | Markdown tokens to native GTK widgets, links, images, code blocks |
| `src/markdown_view.py` | Scrollable preview, empty/oversized states, theme rerendering, scroll fraction |
| `src/exporting.py` | Standalone HTML and Cairo/Pango PDF export |
| `src/paths.py` | Document-directory path containment and export extension helpers |
| `src/preferences.py` | Settings-backed preferences dialog |
| `src/*.blp` | Blueprint UI; compiled to `build/src/*.ui` |
| `src/style.css` | Preview-specific `md-*` classes and Adwaita theme integration |
| `src/vendor/` | Vendored markdown-it-py, mdit-py-plugins, mdurl |
| `tests/` | Headless and display tests for the document, renderer, window and lifecycle |

`AGENTS.md` contains the repository-specific conventions and gotchas for
contributors and coding agents.

## Startup

`src/md_split.in` registers the installed GResource, then imports
`md_split.main`. `MdSplitApplication.do_startup()` registers the app icon
resource path, so the window and About dialog resolve
`io.github.james2doyle.MdSplit` without a system install. App CSS is not loaded by
hand: `Adw.Application` automatically loads `style.css` from the resource base
path.

The application creates stateful actions for view mode and remote images.
CLI view/appearance overrides are held on the application and applied to the
windows created by that invocation; they are not written to GSettings.

## Edit-to-preview flow

```text
GtkSource.Buffer change
  -> MdSplitWindow._on_buffer_changed
  -> Document.set_text (dirty state, counts)
  -> 120 ms stats debounce
  -> 180 ms preview debounce (400 ms above 100,000 characters)
  -> MarkdownView.set_markdown
  -> MarkdownRenderer.render
  -> GTK widget tree
```

Preview rendering is skipped while the preview pane is hidden and when the
source text has not changed since the last render; restoring the preview
renders once with current text. Cursor-only keys do not copy the buffer. If
the document exceeds 250,000 characters or 10,000 lines, the preview shows a
paused state instead of building an unsafe widget tree.

The editor applies pure `TextEdit` objects from `src/editing.py`. Edits are
wrapped in `begin_user_action()`/`end_user_action()` so undo restores a
formatting or list operation as one step.

`src/document.py` counts words and estimates reading time at 200 words per
minute. CJK characters count individually. The status bar shows document
totals, or the selected slice while a selection exists; counts above the
large-document threshold stay paused.

## File I/O

`src/fileio.py` is GTK-independent and testable headlessly:

- `load_text_async()` queries the ETag and size, rejects files over 64 MiB,
  reads in chunks, joins and decodes them on a worker thread, strips a leading
  BOM, and delivers the result back on the main loop.
- `save_text_async()` uses `Gio.File.replace_contents_async()` so writes are
  atomic. The payload is passed as callback data to keep the `bytes` object
  alive until GIO finishes reading it.
- The window keeps a serialized save queue and an operation epoch/generation
  counter so stale callbacks cannot apply text to a different document.

## Formatting

`src/formatting.py` normalizes Markdown source without rewriting inline
content, link destinations, front matter or code block contents. It uses the
shared GFM parser to locate headings, list items, block quotes, fenced code
and tables, then applies line-based changes only inside those ranges. List
marker characters are preserved because changing `*` and `+` can merge two
adjacent lists and alter the rendered structure. Tables are padded for visual
alignment; cell text and escaped pipes stay intact.

Manual formatting uses the selection when one exists and the whole document
otherwise. Changes above `CONFIRM_CHANGE_LINES` open an `Adw.AlertDialog` with
a unified-diff preview and a Cancel option. Applying a format is one
`TextEdit` user action, so a single undo restores the previous source.

`format-on-save` runs the same formatter on the whole document before the save
queue snapshots the buffer. It is enabled by default and can be disabled in
Preferences.

## Find and replace

`Gtk.SearchBar` sits above the editor scroller. `GtkSource.SearchSettings` and
`SearchContext` drive navigation and highlighting; `src/editing.py` mirrors the
query and provides tested match counting and replace-all behavior. Replace-all
runs as one `TextEdit` user action, so undo restores the previous text in one
step. Search state is cleared when the bar closes or the source pane is hidden.

## Recovery and session state

`src/recovery.py` writes recovery drafts and timestamped backups under
`$XDG_STATE_HOME/md-split`. Draft text and JSON metadata are written atomically
with mode `0600`. Autosave runs on a daemon thread at the configured interval
for dirty documents; a generation counter prevents a late draft from
overwriting a cleared recovery entry.

At startup the application offers each draft for restore or discard. A
restored file-backed draft loads the on-disk baseline first and then marks the
draft text dirty. Successful saves and explicit discards clear the matching
draft.

`src/session.py` prunes and deduplicates saved paths. The application stores
the open file-backed windows and the active path in GSettings, reopens one
window per path, and skips missing files with a warning. Recent files share
the same path list helpers and also feed `Gtk.RecentManager`.

## External file changes

`MdSplitWindow` watches the current file with `Gio.FileMonitor` and
`WATCH_MOVES`. Events are debounced, filtered by `src/filechanges.py`, and
compared against the document ETag. The app's own saves set a short ignore
window and refresh the monitor after save-as. A clean document offers reload or
keep editing; a dirty document makes reload destructive. Deleted files keep the
editor text and offer **Save As…**.

## Spell checking

`src/spellcheck.py` loads the optional `Spelling` GI namespace. The feature
stays disabled when the namespace, provider, or dictionary list is empty, and
logs one warning that names the missing piece. When available, a
`Spelling.TextBufferAdapter` supplies the underline tag, right-click
suggestions, language changes, **Add to Dictionary**, and **Ignore**. The
adapter is detached on window close.

## Preview rendering

`src/markdown_parser.py` creates one CommonMark parser with the GFM plugin:

```python
MarkdownIt("commonmark", {
    "html": False,
    "linkify": False,
    "typographer": False,
    "breaks": False,
})
gfm_plugin(parser, tasklists_editable=False)
```

`MarkdownRenderer` walks tokens and builds labels, boxes, grids, check
buttons, pictures, and code-block headers. Text is escaped with
`GLib.markup_escape_text` before Pango markup. The only promoted inline HTML
tag is a balanced `<u>`/`</u>` pair, and it is promoted only when it nests
correctly with emphasis, strikethrough and resolved links; code spans,
unbalanced tags and crossing pairs remain literal. A soft line break becomes a
space, while two trailing spaces or a backslash force a line break. Nested list
boxes get an increasing start margin, so child items are indented under their
parent.

Links, preview images and export images resolve through `src/paths.py`.
Targets are resolved (including `..`, percent-encoding and symlinks) and must
stay inside the document directory; unsafe schemes (`javascript`, `vbscript`,
`data`) are rejected. External links use `Gtk.UriLauncher`; internal
`#anchors` scroll within the preview.

## Theming

The preview uses Adwaita CSS classes plus app-specific `md-*` classes from
`src/style.css`. The app listens to `Adw.StyleManager` dark-mode changes and
rerenders the preview. Custom colors use Adwaita named colors such as
`@borders`, `@card_bg_color`, and `@accent_bg_color` so light, dark, and
high-contrast themes remain usable.

## Scroll synchronization

Both `Gtk.ScrolledWindow` adjustments are mapped to a fraction of their
scrollable range. A `_scroll_guard` flag suppresses the feedback loop while
one pane drives the other. Preview rerenders capture the current fraction and
restore it when the scrolled window adjustment reports the new allocation.

## Images

Local images are resolved through the document directory, bounded by byte and
pixel limits, decoded asynchronously with a render-cancellable request, and
cached. Superseded reads are cancelled and their callbacks detached from the
replaced widget tree. Remote images are opt-in:

- only `http`/`https`;
- 10 MiB per image, 20 megapixels;
- at most 32 remote images per render;
- 15 second timeout;
- redirects are rechecked for an HTTP(S) scheme;
- decoding happens off the UI thread, with cancellation on rerender/shutdown.

See [security.md](security.md) for the full policy.

## Export

HTML export builds a standalone document with embedded local images; PDF export
lays the same tokens out with Pango and Cairo. The HTML theme lives in
`src/export.css`, adapted from [new.css](https://github.com/xz/new.css) (MIT),
and is inlined at export time. It follows the viewer's
`prefers-color-scheme`. PDF uses the palette and type scale in
`src/exporting.py`; `export-font-size` controls only the PDF base size and
`_TypeScale` derives the rest. The application appearance setting only changes
the native preview. HTML gets measure-limited typography, bordered and
zebra-striped tables, figures with captions and callout styling. PDF uses its
palette for headings, code boxes, tables and quote bars.

`_PdfWriter` gives tables a real cell grid: columns fill the content width,
narrow columns keep their natural size while wide ones are capped, alignment
comes from the GFM column style, and the header row repeats after a page break.
Rows that would overflow a page are split by line so a single tall cell cannot
run past the footer. The footer carries the document title and page number.

`MdSplitWindow` captures the text and base location on the main thread and runs
the render in a daemon worker, then marshals the result or error back with
`GLib.idle_add`. HTML is written through `fileio.save_text_async()`; PDF writes
to a `tempfile.mkstemp` file and atomically replaces the target. Export targets
get the expected `.html`/`.pdf` extension appended, and existing files
(including the open document) require confirmation before replacement.

## Extending the app

- Add Markdown block support in `MarkdownRenderer._render_blocks`, using GTK
  widgets and escaped Pango markup. Add renderer widget-tree tests.
- Add editing behavior as a pure helper in `src/editing.py`, then apply it in
  `MdSplitWindow._apply_text_edit`.
- Add an application action in `src/main.py`, wire it from a `.blp` menu or
  button, and add it to `src/shortcuts-dialog.blp`.
- Add settings to `data/io.github.james2doyle.MdSplit.gschema.xml` and bind them in
  the preferences dialog.

Keep parser behavior GFM-compatible and do not add runtime pip dependencies;
the Markdown parser is vendored under `src/vendor/`.
