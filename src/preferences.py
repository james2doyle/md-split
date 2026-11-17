# SPDX-License-Identifier: MIT

"""Preferences dialog backed by GSettings."""

from __future__ import annotations

from gettext import gettext as _

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gdk, Gio, Gtk

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
    close_button = Gtk.Template.Child("close_button")

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
        self.close_button.connect("clicked", self._on_close_clicked)
        click = Gtk.GestureClick()
        click.set_button(Gdk.BUTTON_PRIMARY)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._on_background_clicked)
        self.add_controller(click)
        self._click_controller = click
        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key)
        self._key_controller = key

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

    def _on_close_clicked(self, _button) -> None:
        self.close()

    def _on_background_clicked(
        self, _gesture, _n_press: int, x: float, y: float
    ) -> None:
        child = self.get_child()
        if child is None:
            return
        success, bounds = child.compute_bounds(self)
        if not success:
            return
        if (
            bounds.get_x() <= x < bounds.get_x() + bounds.get_width()
            and bounds.get_y() <= y < bounds.get_y() + bounds.get_height()
        ):
            return
        self.close()

    def _on_key_pressed(
        self, _controller, keyval: int, _keycode: int, state: Gdk.ModifierType
    ) -> bool:
        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        blocked = (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.ALT_MASK
            | Gdk.ModifierType.SUPER_MASK
        )
        if keyval == Gdk.KEY_Escape and not (modifiers & blocked):
            self.close()
            return True
        return False

    def _on_closed(self, *_args) -> None:
        if self._appearance_handler:
            self._settings.disconnect(self._appearance_handler)
            self._appearance_handler = 0
        for row, prop in self._bindings:
            self._settings.unbind(row, prop)
        self._bindings.clear()
