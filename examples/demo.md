# MD Split

A native GNOME Markdown editor with a live **GitHub-Flavored Markdown** preview.

> [!NOTE]
> The preview is rendered with real GTK widgets — labels, grids, lists and
> pictures — rather than a web view.

## Features

- [x] Native GTK 4 + libadwaita interface
- [x] GFM tables, task lists, alerts and footnotes
- [x] Autolinks such as https://gnome.org
- [ ] Your next note

## Markdown support

| Feature | Supported | Native widget |
|:--------|:---------:|--------------:|
| Tables | Yes | `Gtk.Grid` |
| Task lists | Yes | `Gtk.CheckButton` |
| Code blocks | Yes | `Gtk.Label` |
| Images | Yes | `Gtk.Picture` |

## Code

```python
def render(markdown: str) -> Gtk.Widget:
    return renderer.render(markdown)
```

> Markdown is a lightweight markup language for creating formatted text using a
> plain-text editor.

Read more at [the CommonMark spec](https://commonmark.org/) or
[GitHub's GFM spec](https://github.github.com/gfm/).

Footnote reference[^native].

[^native]: The parser is markdown-it-py with its composite GFM plugin.

![MD Split icon](../data/icons/hicolor/scalable/apps/com.james2doyle.MdSplit.svg)
