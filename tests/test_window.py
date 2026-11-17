"""Smoke test: load the built gresource and exercise the native window.

Run via `meson test`; APP_RESOURCE points at the built gresource.
"""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCE = os.environ.get("APP_RESOURCE")

if not RESOURCE or not os.path.exists(RESOURCE):
    print("SKIP: APP_RESOURCE is not set")
    sys.exit(77)

sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

if not Gtk.init_check() or Gdk.Display.get_default() is None:
    print("SKIP: no display available")
    sys.exit(77)

Adw.init()

resource = Gio.Resource.load(RESOURCE)
resource._register()

from src.window import MdSplitWindow


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


window = MdSplitWindow()
assert "MD Split" in window.get_title(), window.get_title()
assert not window.document.is_dirty

window.set_text("# Native preview\n\n**bold** and [link](https://example.com)")
assert window.get_text().startswith("# Native preview")
assert window.document.is_dirty
assert "Untitled.md" in window.window_title.get_title()
assert "•" in window.window_title.get_title()
assert "words" in window.label_stats.get_label(), window.label_stats.get_label()

texts = []
for widget in walk(window.preview):
    if isinstance(widget, Gtk.Label):
        texts.append(widget.get_text())
        texts.append(widget.get_label() or "")
joined = "\n".join(texts)
assert "Native preview" in joined, joined
assert "bold" in joined, joined
assert 'href="https://example.com"' in joined, joined
assert "WebKit" not in sys.modules, "window must not instantiate a web view"

window.set_view_mode("source")
assert window.editor_pane.get_visible()
assert not window.preview_container.get_visible()
assert window.preview._paused
window.set_view_mode("preview")
assert not window.editor_pane.get_visible()
assert window.preview_container.get_visible()
assert not window.preview._paused
window.set_view_mode("both")
assert window.editor_pane.get_visible()
assert window.preview_container.get_visible()

window.destroy()

# Gtk.FileDialog invokes its callback with only (source_object, result).
# A required user-data parameter raises TypeError before the dialog result is
# handled, so guard the arity directly.
import inspect

open_parameters = list(
    inspect.signature(MdSplitWindow._on_open_finished).parameters
)
assert open_parameters == ["self", "dialog", "result"], open_parameters

# A save completing after newer edits must not mark those edits clean.
from src import fileio

window = MdSplitWindow()
file = Gio.File.new_for_path("/tmp/opencode/test-save-race.md")
window.document.load("old", file)
pending_saves = []
original_save = fileio.save_text_async


def fake_save(_file, text, callback, cancellable=None, etag=None):
    pending_saves.append((text, callback))


fileio.save_text_async = fake_save
try:
    window.set_text("first version")
    window.save_document()
    assert window.document.is_dirty
    window.set_text("new unsaved edit")
    payload, complete = pending_saves.pop(0)
    complete(None, "new-etag")
    assert payload == "first version"
    assert window.get_text() == "new unsaved edit"
    assert window.document.is_dirty
finally:
    fileio.save_text_async = original_save
    window.destroy()

# A load completing after the user edited must not replace those edits.
window = MdSplitWindow()
pending_loads = []
original_load = fileio.load_text_async


def fake_load(_file, callback, cancellable=None):
    pending_loads.append((callback, cancellable))


fileio.load_text_async = fake_load
try:
    window.open_file(Gio.File.new_for_path("/tmp/opencode/test-load-race.md"))
    window.set_text("typed while loading")
    loaded, _cancellable = pending_loads.pop(0)
    loaded("disk contents", "etag", None)
    assert window.get_text() == "typed while loading"
    assert window.document.is_dirty
finally:
    fileio.load_text_async = original_load
    window.destroy()

# Hidden previews must not synchronously render or start image requests.
window = MdSplitWindow()
window.set_view_mode("source")
rendered = []
window._preview.set_markdown = lambda *args, **kwargs: rendered.append(True)
window.set_text("# Hidden")
window._render_preview()
assert not rendered
window.destroy()

# The editor owns keyboard focus once the window is mapped.
window = MdSplitWindow()
window.present()
while GLib.MainContext.default().iteration(False):
    pass
assert window.get_focus() is window.editor_view, window.get_focus()
window.destroy()

# The bundled demo loads as clean, untitled scratch content.
window = MdSplitWindow()
window.load_demo_document()
assert window.get_text().startswith("# MD Split"), window.get_text()[:40]
assert not window.document.is_dirty
assert window.document.file is None
window.set_text(window.get_text() + "\nchanged")
assert window.document.is_dirty
window.destroy()

# Typing ] after an empty [ completes a link with the cursor inside ().
window = MdSplitWindow()
window.set_text("abc [")
window._buffer.place_cursor(window._buffer.get_end_iter())
assert window._on_key_pressed(None, Gdk.KEY_bracketright, 0, Gdk.ModifierType(0))
assert window.get_text() == "abc []()", window.get_text()
insert = window._buffer.get_iter_at_mark(window._buffer.get_insert())
assert insert.get_offset() == 7, insert.get_offset()
window._settings.set_boolean("autocomplete-links", False)
window.set_text("abc [")
window._buffer.place_cursor(window._buffer.get_end_iter())
assert not window._on_key_pressed(None, Gdk.KEY_bracketright, 0, Gdk.ModifierType(0))
window.destroy()

# Selections can be surrounded with brackets, braces, backticks and quotes.
window = MdSplitWindow()
for keyval, expected in (
    (Gdk.KEY_bracketleft, "h[ell]o"),
    (Gdk.KEY_braceleft, "h{ell}o"),
    (Gdk.KEY_grave, "h`ell`o"),
    (Gdk.KEY_quotedbl, 'h"ell"o'),
    (Gdk.KEY_apostrophe, "h'ell'o"),
):
    window.set_text("hello")
    window._buffer.select_range(
        window._buffer.get_iter_at_offset(1),
        window._buffer.get_iter_at_offset(4),
    )
    assert window._on_key_pressed(None, keyval, 0, Gdk.ModifierType(0))
    assert window.get_text() == expected, (keyval, window.get_text())
window.destroy()

# Formatting shortcuts operate on the current selection.
window = MdSplitWindow()
for kind, expected in (
    ("bold", "h**ell**o"),
    ("italic", "h*ell*o"),
    ("underline", "h<u>ell</u>o"),
    ("code", "h`ell`o"),
):
    window.set_text("hello")
    window._buffer.select_range(
        window._buffer.get_iter_at_offset(1),
        window._buffer.get_iter_at_offset(4),
    )
    window.format_selection(kind)
    assert window.get_text() == expected, (kind, window.get_text())
window.set_text("one\ntwo")
window._buffer.select_range(
    window._buffer.get_iter_at_offset(0),
    window._buffer.get_iter_at_offset(len("one\ntwo")),
)
window.format_selection("blockquote")
assert window.get_text() == "> one\n> two", window.get_text()
window.destroy()

print("ok: native window")
