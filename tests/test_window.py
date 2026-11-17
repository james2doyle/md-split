"""Smoke test: load the built gresource and exercise the native window.

Run via `meson test`; APP_RESOURCE points at the built gresource.
"""

import os
import sys
import tempfile
import threading
from pathlib import Path

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

os.environ.setdefault(
    "MD_SPLIT_STATE_DIR",
    os.path.join(
        tempfile.gettempdir(), f"md-split-window-state-{os.getpid()}"
    ),
)

from src import recovery
from src.window import MdSplitWindow, _preview_interval

assert _preview_interval(0) == 180
assert _preview_interval(100_000) == 180
assert _preview_interval(100_001) == 400


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


def wait_until(predicate, timeout_ms=4000):
    loop = GLib.MainLoop()
    state = {"timed_out": False}

    def poll():
        if predicate():
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
    assert not state["timed_out"], "timed out waiting for background work"


from src import spellcheck

window = MdSplitWindow()
assert "MD Split" in window.get_title(), window.get_title()
assert not window.document.is_dirty
if not spellcheck.backend_available():
    assert window.spell_adapter is None
else:
    assert window.spell_adapter is not None
    assert window.spell_adapter.get_enabled() is True
    window._settings.set_boolean("spell-check", False)
    while GLib.MainContext.default().iteration(False):
        pass
    assert not window.spell_adapter.get_enabled()
    window._settings.set_boolean("spell-check", True)
    while GLib.MainContext.default().iteration(False):
        pass
    assert window.spell_adapter.get_enabled()

window.set_text("# Native preview\n\n**bold** and [link](https://example.com)")
assert window.get_text().startswith("# Native preview")
assert window.document.is_dirty
assert "Untitled.md" in window.window_title.get_title()
assert "•" in window.window_title.get_title()
assert "words" in window.label_stats.get_label(), window.label_stats.get_label()
assert "minute read" in window.label_stats.get_label(), window.label_stats.get_label()

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

# Selection statistics replace document totals while text is selected.
window.set_text("Hello world from the selection test")
window._buffer.select_range(
    window._buffer.get_iter_at_offset(0),
    window._buffer.get_iter_at_offset(11),
)
window._update_stats()
selection_stats = window.label_stats.get_label()
assert selection_stats.startswith("Selection:"), selection_stats
assert "2 words" in selection_stats, selection_stats
assert "11 characters" in selection_stats, selection_stats
assert "minute read" in selection_stats, selection_stats
window._buffer.place_cursor(window._buffer.get_end_iter())
window._update_stats()
assert not window.label_stats.get_label().startswith("Selection:")
assert "6 words" in window.label_stats.get_label(), window.label_stats.get_label()

# Find and replace wiring.
assert not window.search_bar.get_search_mode()
window.show_find()
assert window.search_bar.get_search_mode()
assert not window.replace_row.get_visible()
window.show_replace()
assert window.search_bar.get_search_mode()
assert window.replace_row.get_visible()

window.set_text("one one one")
window.search_entry.set_text("one")
window._on_search_changed()
assert "3 matches" in window.search_status_label.get_label(), (
    window.search_status_label.get_label()
)
window._find_next()
bounds = window._buffer.get_selection_bounds()
assert bounds, "find did not select a match"
assert window._buffer.get_text(bounds[0], bounds[1], True) == "one"

window.replace_entry.set_text("two")
window._replace_all()
assert window.get_text() == "two two two", window.get_text()
window._buffer.undo()
assert window.get_text() == "one one one", window.get_text()

window._buffer.select_range(
    window._buffer.get_iter_at_offset(0),
    window._buffer.get_iter_at_offset(3),
)
window._replace_current()
assert window.get_text() == "two one one", window.get_text()
window._buffer.undo()
assert window.get_text() == "one one one", window.get_text()

window.search_entry.set_text("[")
window.search_regex_button.set_active(True)
window._on_search_changed()
assert "Invalid regular expression" in window.search_status_label.get_label()
window._close_search()
assert not window.search_bar.get_search_mode()

# External edits prompt once per etag and offer reload/keep choices.
with tempfile.TemporaryDirectory() as tmp:
    external_path = Path(tmp) / "external.md"
    external_path.write_text("base", encoding="utf-8")
    external = Gio.File.new_for_path(str(external_path))
    window.document.load("base", external, "old-etag")
    window._handle_file_change(external, "changed", "new-etag")
    dialog = window._confirm_dialog
    assert dialog is not None
    assert dialog.get_heading() == "File changed on disk"
    dialog.close()
    window._confirm_dialog = None

    window._handle_file_change(external, "deleted", None)
    dialog = window._confirm_dialog
    assert dialog is not None
    assert dialog.get_heading() == "File deleted"
    dialog.close()
    window._confirm_dialog = None

# Autosave drafts are written off the main loop and clear on save/discard.
window.set_text("draft text")
window._autosave_now()
draft_key = window._draft_key()
wait_until(lambda: recovery.read_draft(draft_key) is not None)
draft = recovery.read_draft(draft_key)
assert draft is not None and draft.text == "draft text"
window._clear_recovery()
assert recovery.read_draft(draft_key) is None

with tempfile.TemporaryDirectory() as tmp:
    recovered_path = Path(tmp) / "recovered.md"
    recovered_path.write_text("saved baseline", encoding="utf-8")
    recovered = recovery.Draft(
        key="recovered",
        text="unsaved recovery",
        path=str(recovered_path),
        name="recovered.md",
        updated=0.0,
    )
    window.load_recovered_draft(recovered)
    assert window.get_text() == "unsaved recovery"
    assert window.document.is_dirty
    assert window.document.file is not None
    assert window.document.file.get_path() == str(recovered_path)
    window._clear_recovery()

with tempfile.TemporaryDirectory() as tmp:
    recent_path = Path(tmp) / "recent.md"
    recent_path.write_text("recent", encoding="utf-8")
    window._record_recent(Gio.File.new_for_path(str(recent_path)))
    assert str(recent_path) in window._settings.get_strv("recent-files")
    menu = window.button_recent.get_menu_model()
    assert menu is not None and menu.get_n_items() >= 1
window._settings.set_strv("recent-files", [])

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

# Cursor-only keys must not copy the whole buffer.
window = MdSplitWindow()
window.set_text("plain text")
window._buffer.place_cursor(window._buffer.get_start_iter())
text_reads = []
original_get_text = window.get_text


def counting_get_text():
    text_reads.append(True)
    return original_get_text()


window.get_text = counting_get_text
for keyval in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Home, Gdk.KEY_End):
    assert not window._on_key_pressed(
        None, keyval, 0, Gdk.ModifierType(0)
    )
window._buffer.select_range(
    window._buffer.get_iter_at_offset(1),
    window._buffer.get_iter_at_offset(4),
)
assert not window._on_key_pressed(None, Gdk.KEY_Left, 0, Gdk.ModifierType(0))
assert not text_reads, text_reads
window.get_text = original_get_text
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

# Export overwrites are confirmed, and a missing file is accepted directly.
import tempfile
from pathlib import Path

window = MdSplitWindow()
with tempfile.TemporaryDirectory() as export_dir:
    target = Gio.File.new_for_path(str(Path(export_dir) / "report.html"))
    Path(export_dir, "report.html").write_text("old", encoding="utf-8")
    accepted = []
    window._confirm_export_overwrite(target, accepted.append)
    assert window._confirm_dialog is not None
    assert not accepted, accepted
    window._confirm_dialog.emit("response", "replace")
    assert accepted == [target], accepted
    window._confirm_dialog = None

    missing = Gio.File.new_for_path(str(Path(export_dir) / "new.html"))
    accepted = []
    window._confirm_export_overwrite(missing, accepted.append)
    assert accepted == [missing], accepted
window.destroy()

# Exports run in a worker thread and finish on the main loop.
window = MdSplitWindow()
window.set_text("# Export")
rendered_threads = []
saved = []
from src import exporting

original_render = exporting.render_html
original_save = fileio.save_text_async


def threaded_render(*args, **kwargs):
    rendered_threads.append(threading.get_ident())
    return original_render(*args, **kwargs)


def capture_save(file, text, callback, cancellable=None, etag=None):
    saved.append((file.get_path(), text))
    callback(None, None)


exporting.render_html = threaded_render
fileio.save_text_async = capture_save
try:
    html_target = Gio.File.new_for_path("/tmp/opencode/threaded.html")
    window._export_html_to(html_target)
    assert saved == [], "HTML export blocked the caller"
    wait_until(lambda: bool(saved))
finally:
    exporting.render_html = original_render
    fileio.save_text_async = original_save
assert rendered_threads and rendered_threads[0] != threading.get_ident()
assert saved[0][0] == html_target.get_path()
assert saved[0][1].startswith("<!doctype html>")
window.destroy()

window = MdSplitWindow()
window.set_text("# PDF")
pdf_threads = []
original_pdf = exporting.write_pdf


def threaded_pdf(*args, **kwargs):
    pdf_threads.append(threading.get_ident())


exporting.write_pdf = threaded_pdf
try:
    window._export_pdf_to(
        Gio.File.new_for_path("/tmp/opencode/threaded.pdf")
    )
    wait_until(lambda: bool(pdf_threads))
finally:
    exporting.write_pdf = original_pdf
assert pdf_threads[0] != threading.get_ident()
window.destroy()

# Window geometry is clamped to the schema ranges before it is persisted.
window = MdSplitWindow()
assert window._clamped_setting("window-width", 5000) == 4000
assert window._clamped_setting("window-height", 100) == 400
assert window._clamped_setting("paned-position", 9000) == 4000
window.get_width = lambda: 5000
window.get_height = lambda: 3500
window._save_settings()
assert window.settings.get_int("window-width") == 4000
assert window.settings.get_int("window-height") == 3000
window.destroy()

print("ok: native window")
