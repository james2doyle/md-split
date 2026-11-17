# SPDX-License-Identifier: MIT

import logging
import os
import sys
from gettext import gettext as _

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import APP_ID, VIEW_MODES
from .logging_utils import install_known_gtk_warning_filter
from .preferences import MdSplitPreferencesDialog
from .window import MdSplitWindow

log = logging.getLogger(__name__)

STYLE_RESOURCE = "/com/james2doyle/MdSplit/style.css"
ICON_RESOURCE_PATH = "/com/james2doyle/MdSplit/icons"


class MdSplitApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self, version):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
            resource_base_path="/com/james2doyle/MdSplit",
        )
        self.version = version
        self.settings = Gio.Settings(schema_id=APP_ID)
        self._preferences_dialog = None
        self._cli_view_mode = None
        self._cli_color_scheme = None
        self._register_options()
        self.connect("handle-local-options", self._on_handle_local_options)
        self._apply_appearance()
        self.settings.connect("changed::appearance", self._on_appearance_changed)
        self.create_action("new", self.on_new_action, ["<control>n"])
        self.create_action("open", self.on_open_action, ["<control>o"])
        self.create_action("save", self.on_save_action, ["<control>s"])
        self.create_action(
            "save-as", self.on_save_as_action, ["<control><shift>s"]
        )
        self.create_action("export-html", self.on_export_html_action)
        self.create_action("export-pdf", self.on_export_pdf_action)
        for name, shortcut in (
            ("format-bold", "<control>b"),
            ("format-italic", "<control>i"),
            ("format-underline", "<control>u"),
            ("format-blockquote", "<control>t"),
            ("format-code", "<control>grave"),
        ):
            self.create_action(name, self.on_format_action, [shortcut])
        self.create_action(
            "view-mode",
            self.on_view_mode_action,
            parameter_type=GLib.VariantType.new("s"),
            state=GLib.Variant.new_string(
                self.settings.get_string("view-mode")
                if self.settings.get_string("view-mode") in VIEW_MODES
                else "both"
            ),
        )
        self.create_action("cycle-view", self.on_cycle_view_action, ["F9"])
        self.create_action(
            "remote-images",
            self.on_remote_images_action,
            state=GLib.Variant.new_boolean(
                self.settings.get_boolean("remote-images")
            ),
        )
        self.create_action(
            "preferences", self.on_preferences_action, ["<control>comma"]
        )
        self.create_action("quit", self.on_quit_action, ["<control>q"])
        self.create_action("about", self.on_about_action)
        self.settings.connect("changed::remote-images", self._sync_remote_action)

    def _register_options(self) -> None:
        for name, description in (
            ("no-source", _("Start with the preview pane only")),
            ("no-preview", _("Start with the source pane only")),
            ("source-only", _("Start with the source pane only")),
            ("preview-only", _("Start with the preview pane only")),
            ("light", _("Force light mode for this run")),
            ("dark", _("Force dark mode for this run")),
        ):
            self.add_main_option(
                name,
                0,
                GLib.OptionFlags.NONE,
                GLib.OptionArg.NONE,
                description,
                None,
            )

    def _on_handle_local_options(self, _app, options) -> int:
        source_only = options.contains("source-only") or options.contains(
            "no-preview"
        )
        preview_only = options.contains("preview-only") or options.contains(
            "no-source"
        )
        if source_only and preview_only:
            print(
                _("error: --source-only and --preview-only cannot be combined"),
                file=sys.stderr,
            )
            return 1

        light = options.contains("light")
        dark = options.contains("dark")
        if light and dark:
            print(
                _("error: --light and --dark cannot be combined"),
                file=sys.stderr,
            )
            return 1

        self._cli_view_mode = (
            "source" if source_only else "preview" if preview_only else None
        )
        if light:
            self._cli_color_scheme = Adw.ColorScheme.FORCE_LIGHT
        elif dark:
            self._cli_color_scheme = Adw.ColorScheme.FORCE_DARK
        else:
            self._cli_color_scheme = None
        self._apply_appearance()
        return -1

    def _apply_appearance(self) -> None:
        if self._cli_color_scheme is not None:
            scheme = self._cli_color_scheme
        else:
            value = self.settings.get_string("appearance")
            schemes = {
                "light": Adw.ColorScheme.FORCE_LIGHT,
                "dark": Adw.ColorScheme.FORCE_DARK,
            }
            scheme = schemes.get(value, Adw.ColorScheme.DEFAULT)
        Adw.StyleManager.get_default().set_color_scheme(scheme)

    def _on_appearance_changed(self, _settings, _key) -> None:
        self._cli_color_scheme = None
        self._apply_appearance()

    def do_startup(self):
        Adw.Application.do_startup(self)
        display = Gdk.Display.get_default()
        if display is not None:
            icon_theme = Gtk.IconTheme.get_for_display(display)
            icon_theme.add_resource_path(ICON_RESOURCE_PATH)
            provider = Gtk.CssProvider()
            provider.load_from_resource(STYLE_RESOURCE)
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def do_activate(self):
        win = self.props.active_window
        if win is None:
            win = self._new_window()
            if self.settings.get_boolean("load-demo-on-startup"):
                win.load_demo_document()
        win.present()

    def do_open(self, files, n_files, hint):
        if not files:
            self.do_activate()
            return

        first_window = self._ensure_window()
        windows = [(first_window, files[0])]
        for file in files[1:]:
            win = self._new_window()
            windows.append((win, file))

        for win, file in windows:
            win.open_file(file)
            win.present()

    def _new_window(self) -> MdSplitWindow:
        return MdSplitWindow(
            application=self, initial_view_mode=self._cli_view_mode
        )

    def _ensure_window(self) -> MdSplitWindow:
        win = self.props.active_window
        if win is None:
            win = self._new_window()
        return win

    # -- actions ---------------------------------------------------------

    def on_new_action(self, *_args):
        win = self.props.active_window
        if win is not None:
            win.new_document()

    def on_open_action(self, *_args):
        win = self.props.active_window
        if win is not None:
            win.open_document()

    def on_save_action(self, *_args):
        win = self.props.active_window
        if win is not None:
            win.save_document()

    def on_save_as_action(self, *_args):
        win = self.props.active_window
        if win is not None:
            win.save_as_document()

    def on_export_html_action(self, *_args):
        win = self.props.active_window
        if win is not None:
            win.export_html()

    def on_export_pdf_action(self, *_args):
        win = self.props.active_window
        if win is not None:
            win.export_pdf()

    def on_format_action(self, action, _parameter):
        win = self.props.active_window
        if win is not None and win.editor_view.has_focus():
            win.format_selection(action.get_name().removeprefix("format-"))

    def on_preferences_action(self, *_args):
        if self._preferences_dialog is not None:
            self._preferences_dialog.present(self.props.active_window)
            return
        dialog = MdSplitPreferencesDialog()
        dialog.connect("closed", self._on_preferences_closed)
        self._preferences_dialog = dialog
        dialog.present(self.props.active_window)

    def _on_preferences_closed(self, dialog) -> None:
        if self._preferences_dialog is dialog:
            self._preferences_dialog = None

    def on_view_mode_action(self, action, parameter):
        if parameter is None:
            return
        mode = parameter.get_string()
        if mode not in VIEW_MODES:
            return
        win = self.props.active_window
        if win is not None:
            win.set_view_mode(mode)
        else:
            self.settings.set_string("view-mode", mode)
            self.sync_view_mode(mode)

    def on_cycle_view_action(self, *_args):
        win = self.props.active_window
        if win is None:
            return
        index = VIEW_MODES.index(win.view_mode)
        win.set_view_mode(VIEW_MODES[(index + 1) % len(VIEW_MODES)])

    def sync_view_mode(self, mode: str) -> None:
        action = self.lookup_action("view-mode")
        if action is not None and action.get_state().get_string() != mode:
            action.set_state(GLib.Variant.new_string(mode))

    def on_remote_images_action(self, action, _parameter):
        enabled = not action.get_state().get_boolean()
        action.set_state(GLib.Variant.new_boolean(enabled))
        self.settings.set_boolean("remote-images", enabled)

    def _sync_remote_action(self, settings, _key):
        action = self.lookup_action("remote-images")
        if action is not None:
            action.set_state(
                GLib.Variant.new_boolean(settings.get_boolean("remote-images"))
            )

    def on_quit_action(self, *_args):
        windows = self.get_windows()
        if not windows:
            self.quit()
            return
        for win in windows:
            win.close()

    def on_about_action(self, *_args):
        about = Adw.AboutDialog(
            application_name="MD Split",
            application_icon=APP_ID,
            developer_name="James Doyle",
            version=self.version,
            comments=_(
                "A native GNOME Markdown editor with a live, "
                "GitHub-Flavored Markdown preview."
            ),
            website="https://github.com/james2doyle/md-split",
            issue_url="https://github.com/james2doyle/md-split/issues",
            license_type=Gtk.License.MIT_X11,
            translator_credits=_("translator-credits"),
            developers=["James Doyle"],
            copyright="© 2026 James Doyle",
        )
        about.present(self.props.active_window)

    def create_action(
        self,
        name,
        callback,
        shortcuts=None,
        state=None,
        parameter_type=None,
    ):
        if state is None:
            action = Gio.SimpleAction.new(name, parameter_type)
        else:
            action = Gio.SimpleAction.new_stateful(
                name, parameter_type, state
            )
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    """The application's entry point."""
    install_known_gtk_warning_filter()
    configured_level = os.environ.get("G_MESSAGES_DEBUG", "")
    level = logging.DEBUG if configured_level else logging.INFO
    logging.basicConfig(level=level, format="%(name)s: %(message)s")
    log.info("MD Split %s", version)
    app = MdSplitApplication(version)
    return app.run(sys.argv)
