"""In-process tests for editor/preview scroll synchronization."""

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


class FakePreview:
    def __init__(self):
        self.fraction = None

    def set_scroll_fraction(self, fraction):
        self.fraction = fraction


window = MdSplitWindow()
window._settings.set_boolean("sync-scroll", True)
window.set_view_mode("both")
assert window.preview_container.get_visible()

preview = window._preview
preview_adjustment = preview.get_vadjustment()
preview_adjustment.set_upper(2000)
preview_adjustment.set_page_size(100)
preview.set_scroll_fraction(0.5)
assert abs(preview_adjustment.get_value() - 950) < 1

# Programmatic scroll restoration does not emit a user-scroll signal.
events = []
handler = preview.connect(
    "scroll-fraction-changed", lambda *args: events.append(args)
)
preview.set_scroll_fraction(0.25)
assert not events
preview.disconnect(handler)

editor_adjustment = Gtk.Adjustment(
    value=450,
    lower=0,
    upper=1000,
    step_increment=1,
    page_increment=10,
    page_size=100,
)
window.editor_scroller.get_vadjustment = lambda: editor_adjustment
fake_preview = FakePreview()
window._preview = fake_preview  # type: ignore[assignment]

window._on_editor_scrolled()
assert fake_preview.fraction == 0.5, fake_preview.fraction
editor_adjustment.set_value(0)
window._on_preview_scrolled(preview, 0.25)
assert abs(editor_adjustment.get_value() - 225) < 1

# Disabling and re-enabling sync must not move the editor unexpectedly.
window._settings.set_boolean("sync-scroll", False)
fake_preview.fraction = None
window._on_editor_scrolled()
assert fake_preview.fraction is None
window._settings.set_boolean("sync-scroll", True)
assert fake_preview.fraction == 0.25, fake_preview.fraction
assert abs(editor_adjustment.get_value() - 225) < 1

# A preview restore while sync is enabled must leave the editor alone.
window._preview = preview  # type: ignore[assignment]
editor_adjustment.set_value(225)
preview.set_scroll_fraction(0.75)
assert abs(editor_adjustment.get_value() - 225) < 1

window._force_close = True
window.destroy()
while GLib.MainContext.default().iteration(False):
    pass

print("ok: scroll sync")
