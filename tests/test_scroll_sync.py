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

from src.markdown_view import MarkdownView
from src.window import MdSplitWindow


def pump_until(predicate, timeout_ms=3000):
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
    assert not state["timed_out"], "timed out waiting for allocation"


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

# Scroll restoration waits for the new preview content to be allocated.
host = Gtk.Window()
host.set_default_size(480, 360)
standalone = MarkdownView()
host.set_child(standalone)
host.present()
first_document = "\n\n".join(
    f"Paragraph {index} " + "word " * 30 for index in range(80)
)
standalone.set_markdown(first_document)
first_adjustment = standalone.get_vadjustment()
pump_until(
    lambda: first_adjustment.get_upper() > first_adjustment.get_page_size()
)
standalone.set_scroll_fraction(0.5)
assert abs((standalone.get_scroll_fraction() or 0) - 0.5) < 0.02
first_upper = first_adjustment.get_upper()

second_document = first_document + "\n\n" + "\n\n".join(
    f"Extra {index} " + "word " * 30 for index in range(80)
)
standalone.set_markdown(second_document)
pump_until(
    lambda: first_adjustment.get_upper() > first_upper
    and abs((standalone.get_scroll_fraction() or 0) - 0.5) < 0.02
)
assert abs((standalone.get_scroll_fraction() or 0) - 0.5) < 0.02
host.destroy()

window._force_close = True
window.destroy()
while GLib.MainContext.default().iteration(False):
    pass

print("ok: scroll sync")
