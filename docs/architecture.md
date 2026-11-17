# Architecture

MD Split is a native GTK 4 and libadwaita Markdown editor. It deliberately has
no WebKit, embedded browser, web runtime, or compiled WASM assets. The preview
is a tree of ordinary GTK widgets.

## Module map

| Module | Responsibility |
| --- | --- |
| `src/main.py` | `Adw.Application`, actions, CLI options, CSS/icon loading, file activation |
| `src/window.py` | Window layout, `GtkSource.Buffer`, file dialogs, save queue, preview scheduling, scroll sync |
| `src/document.py` | Headless document model: file, text, saved text, dirty state, ETag, counts |
| `src/fileio.py` | Headless async UTF-8 load/save, 64 MiB input bound, atomic replacement |
| `src/editing.py` | Pure `TextEdit` helpers: wrapping, link completion, formatting, list continuation |
| `src/markdown_parser.py` | Shared `markdown-it-py` + GFM parser configuration |
| `src/renderer.py` | Markdown tokens to native GTK widgets, links, images, code blocks |
| `src/markdown_view.py` | Scrollable preview, empty/oversized states, theme rerendering, scroll fraction |
| `src/exporting.py` | Standalone HTML and Cairo/Pango PDF export |
| `src/preferences.py` | Settings-backed preferences dialog |
| `src/*.blp` | Blueprint UI; compiled to `build/src/*.ui` |
| `src/style.css` | Preview-specific `md-*` classes and Adwaita theme integration |
| `src/vendor/` | Vendored markdown-it-py, mdit-py-plugins, mdurl |

`AGENTS.md` contains the repository-specific conventions and gotchas for
contributors and coding agents.

## Startup

`src/md_split.in` registers the installed GResource, then imports
`md_split.main`. `MdSplitApplication.do_startup()` registers:

- the app icon resource path, so the window and About dialog resolve
  `com.james2doyle.MdSplit` without a system install;
- the application CSS provider.

The application creates stateful actions for view mode and remote images.
CLI view/appearance overrides are held on the application and applied to the
windows created by that invocation; they are not written to GSettings.

## Edit-to-preview flow

```text
GtkSource.Buffer change
  -> MdSplitWindow._on_buffer_changed
  -> Document.set_text (dirty state, counts)
  -> 120 ms stats debounce
  -> 180 ms preview debounce
  -> MarkdownView.set_markdown
  -> MarkdownRenderer.render
  -> GTK widget tree
```

Preview rendering is skipped while the preview pane is hidden. If the
document exceeds 250,000 characters or 10,000 lines, the preview shows a
paused state instead of building an unsafe widget tree.

The editor applies pure `TextEdit` objects from `src/editing.py`. Edits are
wrapped in `begin_user_action()`/`end_user_action()` so undo restores a
formatting or list operation as one step.

## File I/O

`src/fileio.py` is GTK-independent and testable headlessly:

- `load_text_async()` queries the ETag and size, rejects files over 64 MiB,
  reads in chunks, decodes UTF-8, and strips a leading BOM.
- `save_text_async()` uses `Gio.File.replace_contents_async()` so writes are
  atomic. The payload is passed as callback data to keep the `bytes` object
  alive until GIO finishes reading it.
- The window keeps a serialized save queue and an operation epoch/generation
  counter so stale callbacks cannot apply text to a different document.

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
tag is a balanced `<u>`/`</u>` pair; code spans and unbalanced tags remain
literal.

Links are resolved against the document's directory or `Gio.File` parent.
Unsafe schemes (`javascript`, `vbscript`, `data`) are rejected. External links
use `Gtk.UriLauncher`; internal `#anchors` scroll within the preview.

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
restore it after the new widget tree is allocated (40 ms timeout).

## Images

Local images are resolved through the document directory, bounded by byte and
pixel limits, decoded asynchronously, and cached. Remote images are opt-in:

- only `http`/`https`;
- 10 MiB per image, 20 megapixels;
- at most 32 remote images per render;
- 15 second timeout;
- redirects are rechecked for an HTTP(S) scheme;
- decoding happens off the UI thread, with cancellation on rerender/shutdown.

See [security.md](security.md) for the full policy.

## Extending the app

- Add Markdown block support in `MarkdownRenderer._render_blocks`, using GTK
  widgets and escaped Pango markup. Add renderer widget-tree tests.
- Add editing behavior as a pure helper in `src/editing.py`, then apply it in
  `MdSplitWindow._apply_text_edit`.
- Add an application action in `src/main.py`, wire it from a `.blp` menu or
  button, and add it to `src/shortcuts-dialog.blp`.
- Add settings to `data/com.james2doyle.MdSplit.gschema.xml` and bind them in
  the preferences dialog.

Keep parser behavior GFM-compatible and do not add runtime pip dependencies;
the Markdown parser is vendored under `src/vendor/`.
