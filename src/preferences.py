# SPDX-License-Identifier: MIT

"""Preferences dialog backed by GSettings."""

from __future__ import annotations

from gettext import gettext as _

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gio, Gtk

from . import APP_ID

_APPEARANCES = ("system", "light", "dark")


@Gtk.Template(resource_path="/com/james2doyle/MdSplit/preferences-dialog.ui")
class MdSplitPreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "MdSplitPreferencesDialog"

    appearance_row = Gtk.Template.Child("appearance_row")
    switch_load_demo = Gtk.Template.Child("switch_load_demo")
    switch_sync_scroll = Gtk.Template.Child("switch_sync_scroll")
    switch_autocomplete_links = Gtk.Template.Child("switch_autocomplete_links")
    switch_remote_images = Gtk.Template.Child("switch_remote_images")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._settings = Gio.Settings(schema_id=APP_ID)
        self._appearance_handler = 0
        self._updating_appearance = False
        self._bindings: list[tuple[Gtk.Widget, str]] = []

        self.appearance_row.set_model(
            Gtk.StringList.new([_("System"), _("Light"), _("Dark")])
        )
        self._sync_appearance()
        self._appearance_handler = self._settings.connect(
            "changed::appearance", self._on_appearance_changed
        )
        self.appearance_row.connect(
            "notify::selected", self._on_appearance_selected
        )

        for key, row in (
            ("load-demo-on-startup", self.switch_load_demo),
            ("sync-scroll", self.switch_sync_scroll),
            ("autocomplete-links", self.switch_autocomplete_links),
            ("remote-images", self.switch_remote_images),
        ):
            self._settings.bind(
                key, row, "active", Gio.SettingsBindFlags.DEFAULT
            )
            self._bindings.append((row, "active"))
        self.connect("closed", self._on_closed)

    def _appearance_index(self) -> int:
        value = self._settings.get_string("appearance")
        try:
            return _APPEARANCES.index(value)
        except ValueError:
            return 0

    def _sync_appearance(self) -> None:
        index = self._appearance_index()
        if self.appearance_row.get_selected() == index:
            return
        self._updating_appearance = True
        try:
            self.appearance_row.set_selected(index)
        finally:
            self._updating_appearance = False

    def _on_appearance_changed(self, _settings, _key) -> None:
        self._sync_appearance()

    def _on_appearance_selected(self, _row, _parameter) -> None:
        if self._updating_appearance:
            return
        index = self.appearance_row.get_selected()
        if 0 <= index < len(_APPEARANCES):
            self._settings.set_string("appearance", _APPEARANCES[index])

    def _on_closed(self, *_args) -> None:
        if self._appearance_handler:
            self._settings.disconnect(self._appearance_handler)
            self._appearance_handler = 0
        for row, prop in self._bindings:
            self._settings.unbind(row, prop)
        self._bindings.clear()
