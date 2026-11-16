# SPDX-License-Identifier: MIT

"""Scrollable native Markdown preview built on MarkdownRenderer."""

from __future__ import annotations

import logging
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from .renderer import MarkdownRenderer

log = logging.getLogger(__name__)

_MAX_PREVIEW_CHARS = 250_000
_MAX_PREVIEW_LINES = 10_000


class MarkdownView(Gtk.ScrolledWindow):
    """A native, selectable GFM preview with an empty state."""

    __gtype_name__ = "MdSplitMarkdownView"

    __gsignals__ = {
        "scroll-fraction-changed": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (float,),
        )
    }

    def __init__(self) -> None:
        super().__init__()
        self._renderer = MarkdownRenderer()
        self._dark = False
        self._remote_images = False
        self._paused = False
        self._text = ""
        self._base_dir: Path | None = None
        self._base_file: Gio.File | None = None
        self._render_cancellable: Gio.Cancellable | None = None
        self._restore_timeout = 0
        self._syncing_scroll = False

        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_hexpand(True)
        self.set_vexpand(True)
        adjustment = self.get_vadjustment()
        if adjustment is not None:
            adjustment.connect("value-changed", self._on_scroll_changed)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(120)
        self._stack.set_hexpand(True)
        self._stack.set_vexpand(True)

        self._clamp = Adw.Clamp()
        self._clamp.set_maximum_size(880)
        self._clamp.set_tightening_threshold(640)
        self._clamp.set_hexpand(True)

        empty_page = Adw.StatusPage()
        empty_page.set_icon_name("text-x-generic-symbolic")
        empty_page.set_title(_("Nothing to preview"))
        empty_page.set_description(_("Start typing Markdown in the editor."))
        self._empty_page = empty_page

        oversized_page = Adw.StatusPage()
        oversized_page.set_icon_name("dialog-warning-symbolic")
        oversized_page.set_title(_("Preview paused"))
        oversized_page.set_description(
            _("This document is too large to preview safely.")
        )
        self._oversized_page = oversized_page

        self._stack.add_named(empty_page, "empty")
        self._stack.add_named(oversized_page, "oversized")
        self._stack.add_named(self._clamp, "content")
        self._stack.set_visible_child_name("empty")
        self.set_child(self._stack)

    def set_markdown(
        self,
        text: str,
        base_dir: Path | None = None,
        base_file: Gio.File | None = None,
    ) -> None:
        """Render Markdown, preserving the reader's scroll position."""
        self._text = text
        self._base_dir = base_dir
        self._base_file = base_file
        self._cancel_render()

        if self._paused or not text.strip():
            self._cancel_restore()
            self._clamp.set_child(None)
            self._stack.set_visible_child_name("empty")
            return
        if len(text) > _MAX_PREVIEW_CHARS or text.count("\n") > _MAX_PREVIEW_LINES:
            self._cancel_restore()
            self._clamp.set_child(None)
            self._stack.set_visible_child_name("oversized")
            return

        fraction = self.get_scroll_fraction() or 0.0
        cancellable = Gio.Cancellable()
        self._render_cancellable = cancellable
        content = self._renderer.render(
            text,
            dark=self._dark,
            base_dir=base_dir,
            base_file=base_file,
            allow_remote_images=self._remote_images,
            cancellable=cancellable,
            on_internal_link=self._scroll_to_anchor,
            on_external_link=self._open_external,
        )
        self._clamp.set_child(content)
        self._stack.set_visible_child_name("content")
        self._cancel_restore()
        self._restore_timeout = GLib.timeout_add(40, self._restore_scroll, fraction)

    def set_paused(self, paused: bool) -> None:
        """Stop rendering and release the widget tree while hidden."""
        if paused == self._paused:
            return
        self._paused = paused
        if paused:
            self._cancel_render()
            self._cancel_restore()
            self._clamp.set_child(None)
            self._stack.set_visible_child_name("empty")
        elif self._text.strip():
            self.set_markdown(self._text, self._base_dir, self._base_file)

    def set_remote_images(self, enabled: bool) -> None:
        if enabled == self._remote_images:
            return
        self._remote_images = enabled
        if self._text.strip() and not self._paused:
            self.set_markdown(self._text, self._base_dir, self._base_file)

    def shutdown(self) -> None:
        self._paused = True
        self._text = ""
        self._cancel_render()
        self._cancel_restore()
        self._clamp.set_child(None)
        self._renderer.shutdown()

    def _cancel_render(self) -> None:
        if self._render_cancellable is not None:
            self._render_cancellable.cancel()
            self._render_cancellable = None

    def _cancel_restore(self) -> None:
        if self._restore_timeout:
            GLib.source_remove(self._restore_timeout)
            self._restore_timeout = 0

    def set_dark(self, dark: bool) -> None:
        if dark == self._dark:
            return
        self._dark = dark
        if self._text.strip() and not self._paused:
            self.set_markdown(self._text, self._base_dir, self._base_file)

    @property
    def renderer(self) -> MarkdownRenderer:
        return self._renderer

    def _on_scroll_changed(self, _adjustment) -> None:
        if not self._syncing_scroll and not self._paused:
            fraction = self.get_scroll_fraction()
            if fraction is not None:
                self.emit("scroll-fraction-changed", fraction)

    def get_scroll_fraction(self) -> float | None:
        adjustment = self.get_vadjustment()
        if adjustment is None:
            return None
        maximum = adjustment.get_upper() - adjustment.get_page_size()
        if maximum <= 0:
            return None
        return max(0.0, min(1.0, adjustment.get_value() / maximum))

    def set_scroll_fraction(self, fraction: float) -> None:
        """Set the vertical position without emitting a user-scroll signal."""
        self._cancel_restore()
        adjustment = self.get_vadjustment()
        if adjustment is None:
            return
        maximum = adjustment.get_upper() - adjustment.get_page_size()
        if maximum <= 0:
            return
        self._set_adjustment_value(
            max(0.0, min(1.0, fraction)) * maximum
        )

    def _set_adjustment_value(self, value: float) -> None:
        adjustment = self.get_vadjustment()
        if adjustment is None:
            return
        self._syncing_scroll = True
        try:
            adjustment.set_value(value)
        finally:
            self._syncing_scroll = False

    def _restore_scroll(self, fraction: float) -> bool:
        self._restore_timeout = 0
        self._set_adjustment_value_for_fraction(fraction)
        return False

    def _set_adjustment_value_for_fraction(self, fraction: float) -> None:
        adjustment = self.get_vadjustment()
        if adjustment is None:
            return
        maximum = adjustment.get_upper() - adjustment.get_page_size()
        if maximum > 0:
            self._set_adjustment_value(fraction * maximum)

    def _scroll_to_anchor(self, name: str) -> None:
        widget = self._renderer.get_anchor(name)
        if widget is None:
            return
        try:
            success, rect = widget.compute_bounds(self._clamp)
        except (TypeError, AttributeError):
            return
        if not success:
            return
        adjustment = self.get_vadjustment()
        if adjustment is not None:
            self._set_adjustment_value(max(0.0, rect.get_y() - 12))

    def _open_external(self, uri: str) -> None:
        launcher = Gtk.UriLauncher.new(uri)
        launcher.launch(
            self.get_root(), None, self._on_launch_finished, None
        )

    def _on_launch_finished(self, launcher: Gtk.UriLauncher, result, _data) -> None:
        try:
            launcher.launch_finish(result)
        except GLib.Error as error:
            log.warning("Could not open link: %s", error)
