# MD Split

A native GNOME Markdown editor with a live **GitHub-Flavored Markdown** preview.

> [!NOTE]
> The preview is a real GTK widget tree — headings are labels, tables are
> `Gtk.Grid`s, task lists are check buttons, and images are `Gtk.Picture`s.
> There is no WebKit, no embedded browser and no web runtime.

## Why MD Split?

- [x] Native GTK 4, libadwaita and GtkSourceView
- [x] GFM tables, task lists, alerts, autolinks and footnotes
- [x] Synchronized scrolling and three view modes
- [x] Find, replace and Format Document
- [x] Autosave recovery, session restore and external-change warnings
- [x] Standalone HTML and styled PDF export
- [ ] Your next note

## Markdown at a glance

| Feature | Example | Native widget |
|:--------|:-------:|:--------------|
| Tables | this table | `Gtk.Grid` |
| Task lists | above | `Gtk.CheckButton` |
| Code blocks | below | `Gtk.Label` |
| Images | at the end | `Gtk.Picture` |
| Alerts | this page | styled `Gtk.Box` |

> [!TIP]
> Press **F9** to cycle between both panes, source only, and preview only.

## Code

```python
def render(markdown: str) -> Gtk.Widget:
    return MarkdownRenderer().render(markdown)
```

Inline code such as `Ctrl+Shift+R` formats the document or selection.

## Formatting

**Bold**, *italic*, ~~strikethrough~~, <u>underline</u>, and
[a link to the project](https://github.com/james2doyle/md-split).

> Markdown is a lightweight markup language for creating formatted text using a
> plain-text editor.

## Try it

1. Open a Markdown file with **Ctrl+O**.
2. Press **F9** to change the view.
3. Format the document with **Ctrl+Shift+R**.
4. Export HTML or a styled PDF from the main menu.

## Keyboard shortcuts

| Shortcut | Action |
|:---------|:-------|
| Ctrl+N | New document |
| Ctrl+O | Open |
| Ctrl+S | Save |
| Ctrl+Shift+S | Save As |
| Ctrl+F | Find |
| Ctrl+H | Replace |
| Ctrl+Shift+R | Format document or selection |
| F9 | Cycle view mode |
| Ctrl+, | Preferences |

## Export and recovery

Export HTML or a styled PDF from the main menu. Autosave recovery drafts,
session restore, recent files and optional timestamped backups keep your work
safe. Spell checking uses libspelling when a system dictionary is available.

## Security

Raw HTML is disabled. A balanced `<u>...</u>` pair is the only inline HTML tag
rendered as formatting. Remote images stay off until you enable **Load Remote
Images**; local images are decoded asynchronously with size limits.

## Learn more

- [Architecture](https://github.com/james2doyle/md-split/blob/main/docs/architecture.md)
- [Markdown support](https://github.com/james2doyle/md-split#markdown-support)
- [CommonMark spec](https://commonmark.org/)
- [GitHub GFM spec](https://github.github.com/gfm/)

Footnote reference[^native].

[^native]: The parser is markdown-it-py with its composite GFM plugin.

![MD Split icon](../data/icons/hicolor/scalable/apps/com.james2doyle.MdSplit.svg)
