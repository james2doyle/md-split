"""Smoke-test the native GTK Markdown renderer.

Run via `meson test`; skips when no display is available.
"""

import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GLib", "2.0")
from gi.repository import Adw, Gdk, GLib, Gtk

if not Gtk.init_check() or Gdk.Display.get_default() is None:
    print("SKIP: no display available")
    sys.exit(77)

Adw.init()

from src.renderer import MarkdownRenderer


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


def labels(root):
    return [widget for widget in walk(root) if isinstance(widget, Gtk.Label)]


def all_text(root):
    values = []
    for label in labels(root):
        for getter in ("get_text", "get_label"):
            try:
                value = getattr(label, getter)()
            except Exception:
                continue
            if value:
                values.append(value)
    return "\n".join(values)


def wait_for(condition, timeout_ms=4000):
    loop = GLib.MainLoop()
    state = {"timed_out": False}

    def poll():
        if condition():
            loop.quit()
            return False
        return True

    def timeout():
        state["timed_out"] = True
        loop.quit()
        return False

    GLib.timeout_add(10, poll)
    timeout_id = GLib.timeout_add(timeout_ms, timeout)
    loop.run()
    if not state["timed_out"]:
        GLib.source_remove(timeout_id)
    assert not state["timed_out"], "timed out waiting for local image"


def make_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


SAMPLE = """# Native Markdown

A paragraph with **bold**, *italic*, ~~strike~~, `inline code`, a
[link](https://example.com) and a bare https://gnome.org autolink.

> A quoted paragraph with *emphasis*.

- [x] Completed task
- [ ] Open task
- Nested list
  - Child item

1. First
2. Second

| Name | Value |
|:-----|------:|
| Alpha | 1 |
| Beta | 2 |

```python
print("native")
```

---

> [!NOTE]
> GitHub alerts render as native boxes.

Footnote reference[^note].

[^note]: Footnote text.

![Tiny dot](dot.png)

![Remote dot](https://127.0.0.1:9/not-fetched.png)
"""

with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "dot.png"), "wb") as image_file:
        image_file.write(make_png(40, 24))

    renderer = MarkdownRenderer()
    root = renderer.render(SAMPLE, base_dir=Path(tmp))
    wait_for(lambda: not renderer._local_pending)

    assert isinstance(root, Gtk.Box)
    assert root.get_first_child() is not None

    text = all_text(root)
    for expected in (
        "Native Markdown",
        "bold",
        "italic",
        "strike",
        "inline code",
        "Completed task",
        "Open task",
        "Child item",
        'print("native")',
        "GitHub alerts render as native boxes.",
        "Footnote text.",
        "Tiny dot",
        "Remote dot",
        "Remote image not loaded",
        "Name",
        "Alpha",
    ):
        assert expected in text, f"missing text: {expected!r}\n---\n{text}"
    assert "Loading image" not in text

    check_buttons = [w for w in walk(root) if isinstance(w, Gtk.CheckButton)]
    assert len(check_buttons) == 2, len(check_buttons)
    assert check_buttons[0].get_active() is True
    assert check_buttons[1].get_active() is False

    grids = [w for w in walk(root) if isinstance(w, Gtk.Grid)]
    assert grids, "table grid missing"
    assert any("md-table" in grid.get_css_classes() for grid in grids)

    pictures = [w for w in walk(root) if isinstance(w, Gtk.Picture)]
    assert pictures, "image picture missing"
    assert pictures[0].get_size_request()[1] == 24, pictures[0].get_size_request()

    from src import renderer as renderer_module

    original_limit = renderer_module._MAX_IMAGE_PIXELS
    renderer_module._MAX_IMAGE_PIXELS = 100
    try:
        oversized = MarkdownRenderer().render(
            "![Too many pixels](dot.png)", base_dir=Path(tmp)
        )
    finally:
        renderer_module._MAX_IMAGE_PIXELS = original_limit
    assert not [
        widget for widget in walk(oversized) if isinstance(widget, Gtk.Picture)
    ]
    assert "Image is too large" in all_text(oversized)

    code_labels = [
        w
        for w in labels(root)
        if "md-code-body" in w.get_css_classes()
    ]
    assert code_labels, "code block missing"
    assert code_labels[0].get_text().strip() == 'print("native")'

    markups = "\n".join(
        label.get_label() or "" for label in labels(root)
    )
    assert 'href="https://example.com"' in markups
    assert 'href="https://gnome.org"' in markups
    assert 'href="#fn-0"' in markups
    assert "<s>strike</s>" in markups

    assert "WebKit" not in sys.modules, "renderer must not use WebKit"

    from src.markdown_view import MarkdownView

    view = MarkdownView()
    view.renderer.render = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("oversized documents must not be parsed")
    )
    view.set_markdown("x" * 2_000_001)
    assert view._stack.get_visible_child_name() == "oversized"
    view.shutdown()

    print("ok: native renderer widgets")
