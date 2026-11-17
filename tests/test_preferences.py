"""In-process tests for the preferences dialog."""

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

parent = MdSplitWindow(application=app)
parent.set_default_size(1100, 720)
parent.present()
while GLib.MainContext.default().iteration(False):
    pass


def open_preferences():
    app.on_preferences_action()
    while GLib.MainContext.default().iteration(False):
        pass
    dialog = app._preferences_dialog
    assert dialog is not None
    return dialog


dialog = open_preferences()
assert dialog.close_button.get_visible()
assert app.settings.get_string("appearance") == "system"
assert dialog.switch_sync_scroll.get_active()
assert dialog.switch_autocomplete_links.get_active()
assert dialog.switch_restore_session.get_active()
assert dialog.switch_autosave.get_active()
assert dialog.spin_autosave_interval.get_value() == 30
assert not dialog.switch_backups.get_active()
assert dialog.spin_backup_retention.get_value() == 5

dialog.switch_restore_session.set_active(False)
assert app.settings.get_boolean("restore-session") is False
dialog.switch_restore_session.set_active(True)
dialog.spin_autosave_interval.set_value(45)
assert app.settings.get_int("autosave-interval") == 45
app.settings.set_int("autosave-interval", 20)
assert dialog.spin_autosave_interval.get_value() == 20
app.settings.set_int("autosave-interval", 30)

from src import spellcheck

if not spellcheck.backend_available():
    assert not dialog.switch_spell_check.get_sensitive()
    assert not dialog.combo_spell_language.get_sensitive()
else:
    assert dialog.switch_spell_check.get_sensitive()
    assert dialog.combo_spell_language.get_sensitive()
    assert dialog.combo_spell_language.get_model() is not None
    assert dialog._spell_choices
    index = min(1, len(dialog._spell_choices) - 1)
    dialog.combo_spell_language.set_selected(index)
    assert (
        app.settings.get_string("spell-language")
        == dialog._spell_choices[index][0]
    )
    app.settings.set_string("spell-language", "")

dialog.switch_sync_scroll.set_active(False)
assert app.settings.get_boolean("sync-scroll") is False
dialog.appearance_row.set_selected(1)
assert app.settings.get_string("appearance") == "light"
dialog.switch_remote_images.set_active(True)
assert app.settings.get_boolean("remote-images") is True
app.settings.set_boolean("remote-images", False)

# The gesture controller keeps the dialog open inside the content and closes
# it when the background is clicked.
success, content_bounds = dialog.get_child().compute_bounds(dialog)
assert success
dialog._click_controller.emit(
    "pressed", 1, content_bounds.get_x() + 1, content_bounds.get_y() + 1
)
assert dialog.get_mapped()
outside_x = (
    1
    if content_bounds.get_x() > 1
    else content_bounds.get_x() + content_bounds.get_width() + 2
)
outside_y = (
    1
    if content_bounds.get_y() > 1
    else content_bounds.get_y() + content_bounds.get_height() + 2
)
dialog._click_controller.emit("pressed", 1, outside_x, outside_y)
assert not dialog.get_mapped()
while GLib.MainContext.default().iteration(False):
    pass
assert app._preferences_dialog is None

# Escape closes the dialog and clears the application reference.
dialog = open_preferences()
assert dialog._on_key_pressed(None, Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
assert not dialog.get_mapped()
while GLib.MainContext.default().iteration(False):
    pass
assert app._preferences_dialog is None

# The close button closes the dialog and clears the application reference.
dialog = open_preferences()
assert dialog.appearance_row.get_selected() == 1
app.settings.set_string("appearance", "system")
app.settings.set_boolean("sync-scroll", True)
dialog.close_button.emit("clicked")
assert not dialog.get_mapped()
while GLib.MainContext.default().iteration(False):
    pass
assert app._preferences_dialog is None

parent._force_close = True
parent.destroy()
while GLib.MainContext.default().iteration(False):
    pass

print("ok: preferences dialog")
