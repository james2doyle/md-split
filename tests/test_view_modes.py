"""In-process tests for the three-way view mode and its actions."""

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

from src.main import MdSplitApplication
from src.window import MdSplitWindow

app = MdSplitApplication("test")
app.register(None)

window = MdSplitWindow(application=app)
window.present()
while GLib.MainContext.default().iteration(False):
    pass

assert app.settings.get_string("view-mode") == "both"
assert app.lookup_action("view-mode").get_state().get_string() == "both"
assert app.get_accels_for_action("app.cycle-view") == ["F9"]

assert window.view_mode == "both"
assert window.editor_pane.get_visible()
assert window.preview_container.get_visible()

window.set_view_mode("source")
assert window.view_mode == "source"
assert app.settings.get_string("view-mode") == "source"
assert app.lookup_action("view-mode").get_state().get_string() == "source"
assert window.editor_pane.get_visible()
assert not window.preview_container.get_visible()
assert window.preview._paused

window.set_view_mode("preview")
assert window.view_mode == "preview"
assert app.settings.get_string("view-mode") == "preview"
assert app.lookup_action("view-mode").get_state().get_string() == "preview"
assert not window.editor_pane.get_visible()
assert window.preview_container.get_visible()
assert not window.preview._paused

window.set_view_mode("both")
assert window.view_mode == "both"
assert window.editor_pane.get_visible()
assert window.preview_container.get_visible()

# The menu action selects a mode directly; F9 cycles through all three.
app.lookup_action("view-mode").activate(GLib.Variant.new_string("source"))
assert window.view_mode == "source"
app.lookup_action("cycle-view").activate()
assert window.view_mode == "preview"
app.lookup_action("cycle-view").activate()
assert window.view_mode == "both"
app.lookup_action("cycle-view").activate()
assert window.view_mode == "source"

# A launch-time override applies without changing the saved setting.
window.set_view_mode("both")
override = MdSplitWindow(application=app, initial_view_mode="preview")
override.present()
while GLib.MainContext.default().iteration(False):
    pass
assert override.view_mode == "preview"
assert not override.editor_pane.get_visible()
assert override.preview_container.get_visible()
assert app.settings.get_string("view-mode") == "both"

# A saved mode is restored in a new window.
window.set_view_mode("source")
restored = MdSplitWindow(application=app)
assert restored.view_mode == "source"
assert restored.editor_pane.get_visible()
assert not restored.preview_container.get_visible()
restored.destroy()
window.set_view_mode("both")

# Invalid launch overrides fall back to both panes.
invalid = MdSplitWindow(application=app, initial_view_mode="invalid")
assert invalid.view_mode == "both"
assert invalid.editor_pane.get_visible()
assert invalid.preview_container.get_visible()
invalid.destroy()

# Returning to both panes restores the previous split position.
window.paned.set_position(420)
while GLib.MainContext.default().iteration(False):
    pass
expected_position = window.paned.get_position()
assert expected_position > 0, expected_position
window.set_view_mode("source")
window.set_view_mode("both")
while GLib.MainContext.default().iteration(False):
    pass
assert window.paned.get_position() == expected_position

override._force_close = True
override.destroy()
window._force_close = True
window.destroy()
while GLib.MainContext.default().iteration(False):
    pass

print("ok: view modes")
