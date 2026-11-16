"""In-process tests for application actions and pending file operations."""

import gc
import os
import sys
import weakref

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

from src import fileio
from src.main import MdSplitApplication
from src.window import MdSplitWindow

app = MdSplitApplication("test")
app.register(None)

# Defaults: follow the system theme, load the demo, and enable both helpers.
assert app.settings.get_string("appearance") == "system"
assert app.settings.get_boolean("load-demo-on-startup") is True
assert app.settings.get_boolean("sync-scroll") is True
assert app.settings.get_boolean("autocomplete-links") is True

# Quit must request a window close so the dirty-document guard runs.
close_requests = []
original_close_request = MdSplitWindow._on_close_request


def guarded_close(self, *_args):
    close_requests.append(True)
    return True


MdSplitWindow._on_close_request = guarded_close
try:
    window = MdSplitWindow(application=app)
    window.present()
    while GLib.MainContext.default().iteration(False):
        pass
    window.set_text("unsaved")
    app.lookup_action("quit").activate()
    assert close_requests == [True]
    window._force_close = True
    window.destroy()
finally:
    MdSplitWindow._on_close_request = original_close_request

# Global settings/style-manager signals must not retain destroyed windows.
probe = MdSplitWindow(application=app)
reference = weakref.ref(probe)
probe.destroy()
probe.run_dispose()
while GLib.MainContext.default().iteration(False):
    pass
del probe
gc.collect()
gc.collect()
assert reference() is None, "destroyed window is still retained"

# Every GIO-opened file gets a window instead of silently dropping extras.
opened = []
original_open_file = MdSplitWindow.open_file


def record_open(self, file, on_loaded=None):
    opened.append(file.get_path())


MdSplitWindow.open_file = record_open
try:
    app.do_open(
        [
            Gio.File.new_for_path("/tmp/opencode/one.md"),
            Gio.File.new_for_path("/tmp/opencode/two.md"),
        ],
        2,
        "",
    )
    assert opened == ["/tmp/opencode/one.md", "/tmp/opencode/two.md"]
    for extra_window in app.get_windows():
        extra_window._force_close = True
        extra_window.destroy()
finally:
    MdSplitWindow.open_file = original_open_file

# Saves are serialized and a later snapshot supersedes earlier continuations.
window = MdSplitWindow(application=app)
file = Gio.File.new_for_path("/tmp/opencode/serialized-save.md")
window.document.load("saved", file)
pending = []
original_save = fileio.save_text_async
continuations = []


def fake_save(_file, text, callback, cancellable=None, etag=None):
    pending.append((text, callback))


fileio.save_text_async = fake_save
try:
    window.set_text("first")
    window.save_document_then(lambda: continuations.append("first"))
    window.set_text("second")
    window.save_document_then(lambda: continuations.append("second"))
    assert len(pending) == 1

    first_payload, finish_first = pending.pop(0)
    finish_first(None, "etag-one")
    assert first_payload == "first"
    assert len(pending) == 1
    assert not continuations

    second_payload, finish_second = pending.pop(0)
    finish_second(None, "etag-two")
    assert second_payload == "second"
    assert continuations == ["second"]
    assert window.document.file is not None
    assert window.document.file.equal(file)
    assert not window.document.is_dirty
    assert window.document.etag == "etag-two"
finally:
    fileio.save_text_async = original_save
    window.destroy()

# A stale write completing after New must not touch the new document.
window = MdSplitWindow(application=app)
old_file = Gio.File.new_for_path("/tmp/opencode/stale-save.md")
window.document.load("old", old_file)
pending = []
fileio.save_text_async = fake_save
try:
    window.set_text("old edit")
    window.save_document()
    payload, finish_old = pending.pop(0)
    window._reset_document()
    finish_old(None, "stale-etag")
    assert payload == "old edit"
    assert window.get_text() == ""
    assert window.document.file is None
    assert window.document.etag is None
    assert not window.document.is_dirty
finally:
    fileio.save_text_async = original_save
    window._force_close = True
    window.destroy()

# Appearance changes apply immediately and default to the system preference.
app.settings.set_string("appearance", "dark")
assert (
    Adw.StyleManager.get_default().get_color_scheme()
    == Adw.ColorScheme.FORCE_DARK
)
app.settings.set_string("appearance", "light")
assert (
    Adw.StyleManager.get_default().get_color_scheme()
    == Adw.ColorScheme.FORCE_LIGHT
)
app.settings.set_string("appearance", "system")
assert (
    Adw.StyleManager.get_default().get_color_scheme()
    == Adw.ColorScheme.DEFAULT
)

# Formatting actions are registered with the documented accelerators.
assert [value.lower() for value in app.get_accels_for_action("app.format-bold")] == [
    "<control>b"
]
assert [
    value.lower()
    for value in app.get_accels_for_action("app.format-italic")
] == ["<control>i"]
assert [
    value.lower()
    for value in app.get_accels_for_action("app.format-underline")
] == ["<control>u"]
assert [
    value.lower()
    for value in app.get_accels_for_action("app.format-blockquote")
] == ["<control>t"]
assert [
    value.lower()
    for value in app.get_accels_for_action("app.format-code")
] == ["<control>grave"]

assert app.lookup_action("preferences") is not None
assert app.lookup_action("export-html") is not None
assert app.lookup_action("export-pdf") is not None
assert app.lookup_action("format-bold") is not None

# The preferences dialog reflects and updates the shared settings.
from src.preferences import MdSplitPreferencesDialog

parent = MdSplitWindow(application=app)
parent.present()
while GLib.MainContext.default().iteration(False):
    pass

dialog = MdSplitPreferencesDialog()
dialog.present(parent)
while GLib.MainContext.default().iteration(False):
    pass
assert dialog.appearance_row.get_selected() == 0, dialog.appearance_row.get_selected()
assert dialog.switch_sync_scroll.get_active()
assert dialog.switch_autocomplete_links.get_active()
dialog.switch_sync_scroll.set_active(False)
assert app.settings.get_boolean("sync-scroll") is False
dialog.appearance_row.set_selected(1)
assert app.settings.get_string("appearance") == "light"
dialog.switch_remote_images.set_active(True)
assert app.settings.get_boolean("remote-images") is True
app.settings.set_boolean("remote-images", False)
app.settings.set_string("appearance", "dark")
dialog.close()
while GLib.MainContext.default().iteration(False):
    pass

dialog = MdSplitPreferencesDialog()
dialog.present(parent)
while GLib.MainContext.default().iteration(False):
    pass
assert dialog.appearance_row.get_selected() == 2, dialog.appearance_row.get_selected()
app.settings.set_string("appearance", "system")
app.settings.set_boolean("sync-scroll", True)
app.settings.set_boolean("autocomplete-links", True)
dialog.close()
while GLib.MainContext.default().iteration(False):
    pass
parent._force_close = True
parent.destroy()
while GLib.MainContext.default().iteration(False):
    pass

# Startup loads the bundled demo as clean untitled content when enabled.
for existing in app.get_windows():
    existing._force_close = True
    existing.destroy()
while GLib.MainContext.default().iteration(False):
    pass

app.settings.set_boolean("load-demo-on-startup", True)
app.do_activate()
window = app.props.active_window
assert window is not None
assert window.get_text().startswith("# MD Split"), window.get_text()[:40]
assert not window.document.is_dirty
assert window.document.file is None
window._force_close = True
window.destroy()
while GLib.MainContext.default().iteration(False):
    pass

app.settings.set_boolean("load-demo-on-startup", False)
app.do_activate()
window = app.props.active_window
assert window is not None
assert window.get_text() == ""
window._force_close = True
window.destroy()
app.settings.set_boolean("load-demo-on-startup", True)

print("ok: application lifecycle")
