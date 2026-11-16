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

print("ok: application lifecycle")
