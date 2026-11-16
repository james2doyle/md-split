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
from gi.repository import Adw, Gdk, Gio, Gtk

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

window.set_preview_visible(False)
assert not window.preview_container.get_visible()
window.set_preview_visible(True)
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
window.set_preview_visible(False)
rendered = []
window._preview.set_markdown = lambda *args, **kwargs: rendered.append(True)
window.set_text("# Hidden")
window._render_preview()
assert not rendered
window.destroy()

print("ok: native window")
