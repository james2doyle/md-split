"""In-process tests for command-line option handling."""

import contextlib
import io
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


def cli_options(**flags):
    return GLib.VariantDict.new(
        GLib.Variant(
            "a{sv}",
            {
                name: GLib.Variant.new_boolean(value)
                for name, value in flags.items()
            },
        )
    )


# CLI aliases map to the same source/preview view modes.
for flag, mode in (
    ("no-source", "preview"),
    ("no-preview", "source"),
    ("source-only", "source"),
    ("preview-only", "preview"),
):
    app._cli_view_mode = None
    assert app._on_handle_local_options(
        app, cli_options(**{flag: True})
    ) == -1
    assert app._cli_view_mode == mode, (flag, app._cli_view_mode)

with contextlib.redirect_stderr(io.StringIO()):
    assert app._on_handle_local_options(
        app, cli_options(**{"source-only": True, "preview-only": True})
    ) == 1
with contextlib.redirect_stderr(io.StringIO()):
    assert app._on_handle_local_options(
        app, cli_options(**{"no-source": True, "no-preview": True})
    ) == 1
app._cli_view_mode = None

# CLI appearance flags override the saved setting for this run.
assert app.settings.get_string("appearance") == "system"
app._cli_color_scheme = None
assert app._on_handle_local_options(app, cli_options(light=True)) == -1
assert (
    Adw.StyleManager.get_default().get_color_scheme()
    == Adw.ColorScheme.FORCE_LIGHT
)
assert app._on_handle_local_options(app, cli_options(dark=True)) == -1
assert (
    Adw.StyleManager.get_default().get_color_scheme()
    == Adw.ColorScheme.FORCE_DARK
)
with contextlib.redirect_stderr(io.StringIO()):
    assert app._on_handle_local_options(
        app, cli_options(light=True, dark=True)
    ) == 1
app._cli_color_scheme = None
app._apply_appearance()
assert (
    Adw.StyleManager.get_default().get_color_scheme()
    == Adw.ColorScheme.DEFAULT
)

# A CLI view mode applies to the first window without changing the setting.
app.settings.set_string("view-mode", "both")
app._cli_view_mode = "preview"
app.do_activate()
window = app.props.active_window
assert window is not None
assert window.view_mode == "preview"
assert app.settings.get_string("view-mode") == "both"
window._force_close = True
window.destroy()
app._cli_view_mode = None
while GLib.MainContext.default().iteration(False):
    pass
app.do_activate()
window = app.props.active_window
assert window is not None
assert window.view_mode == "both"
window._force_close = True
window.destroy()
while GLib.MainContext.default().iteration(False):
    pass

# Opening files applies the CLI mode and never loads the demo.
opened = []
demo_calls = []
original_open = MdSplitWindow.open_file
original_demo = MdSplitWindow.load_demo_document


def record_open(self, file, on_loaded=None):
    opened.append(self.view_mode)


def record_demo(self):
    demo_calls.append(True)


MdSplitWindow.open_file = record_open
MdSplitWindow.load_demo_document = record_demo
try:
    app._cli_view_mode = "source"
    app.do_open(
        [Gio.File.new_for_path("/tmp/opencode/cli-mode.md")], 1, ""
    )
    assert opened == ["source"]
    assert not demo_calls
    assert app.settings.get_string("view-mode") == "both"
    for existing in app.get_windows():
        existing._force_close = True
        existing.destroy()
finally:
    MdSplitWindow.open_file = original_open
    MdSplitWindow.load_demo_document = original_demo
    app._cli_view_mode = None

print("ok: CLI options")
