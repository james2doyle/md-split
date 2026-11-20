# SPDX-License-Identifier: MIT

"""Scrollable native Markdown preview built on MarkdownRenderer."""

from __future__ import annotations

import logging
from gettext import gettext as _
from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from . import launcher as launcher_mod

if TYPE_CHECKING:
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
        self._renderer: MarkdownRenderer | None = None
        self._dark = False
        self._remote_images = False
        self._paused = False
        self._text = ""
        self._base_dir: Path | None = None
        self._base_file: Gio.File | None = None
        self._render_cancellable: Gio.Cancellable | None = None
        self._restore_handler = 0
        self._restore_timeout = 0
        self._restore_fraction = 0.0
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
        fraction = self.get_scroll_fraction() or 0.0
        self._release_content_focus()

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

        cancellable = Gio.Cancellable()
        self._render_cancellable = cancellable
        content = self._ensure_renderer().render(
            text,
            dark=self._dark,
            base_dir=base_dir,
            base_file=base_file,
            allow_remote_images=self._remote_images,
            cancellable=cancellable,
            on_internal_link=self.scroll_to_anchor,
            on_external_link=self._open_external,
        )
        # Arm the restore before swapping children so allocation changes
        # emitted during the swap cannot be missed.
        self._wait_for_scroll_restore(fraction)
        self._clamp.set_child(content)
        self._stack.set_visible_child_name("content")

    def set_paused(self, paused: bool) -> None:
        """Stop rendering and release the widget tree while hidden.

        Resuming only clears the paused flag; the owner must call
        :meth:`set_markdown` with current text to rebuild the preview.
        """
        if paused == self._paused:
            return
        self._paused = paused
        if paused:
            self._cancel_render()
            self._cancel_restore()
            self._release_content_focus()
            self._clamp.set_child(None)
            self._stack.set_visible_child_name("empty")

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
        self._release_content_focus()
        self._clamp.set_child(None)
        if self._renderer is not None:
            self._renderer.shutdown()

    def _ensure_renderer(self) -> MarkdownRenderer:
        """Import and construct the parser-backed renderer on first use."""
        renderer = self._renderer
        if renderer is None:
            from .renderer import MarkdownRenderer

            renderer = MarkdownRenderer()
            self._renderer = renderer
        return renderer

    def _cancel_render(self) -> None:
        if self._render_cancellable is not None:
            self._render_cancellable.cancel()
            self._render_cancellable = None

    def _release_content_focus(self) -> None:
        """Move focus out before replacing the rendered widget tree."""
        root = self.get_root()
        focus = root.get_focus() if root is not None else None
        if focus is not None and focus is not self and focus.is_ancestor(self):
            adjustment = self.get_vadjustment()
            value = adjustment.get_value() if adjustment is not None else 0.0
            self.grab_focus()
            # Focus changes can scroll the view; keep the reader's position.
            if adjustment is not None:
                self._set_adjustment_value(value)

    def _cancel_restore(self) -> None:
        if self._restore_timeout:
            GLib.source_remove(self._restore_timeout)
            self._restore_timeout = 0
        if self._restore_handler:
            adjustment = self.get_vadjustment()
            if adjustment is not None:
                adjustment.disconnect(self._restore_handler)
            self._restore_handler = 0

    def set_dark(self, dark: bool) -> None:
        if dark == self._dark:
            return
        self._dark = dark
        if self._text.strip() and not self._paused:
            self.set_markdown(self._text, self._base_dir, self._base_file)

    @property
    def renderer(self) -> MarkdownRenderer:
        return self._ensure_renderer()

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

    def _wait_for_scroll_restore(self, fraction: float) -> None:
        """Restore the scroll fraction once the new content is allocated."""
        self._cancel_restore()
        self._restore_fraction = fraction
        adjustment = self.get_vadjustment()
        if adjustment is None:
            return
        self._restore_handler = adjustment.connect(
            "changed", self._on_restore_adjustment_changed
        )

    def _on_restore_adjustment_changed(self, _adjustment) -> None:
        if not self._restore_handler:
            return
        # Wait for the adjustment to stop changing before restoring.
        if self._restore_timeout:
            GLib.source_remove(self._restore_timeout)
        self._restore_timeout = GLib.timeout_add(
            50, self._restore_scroll_after_allocation
        )

    def _restore_scroll_after_allocation(self) -> bool:
        self._restore_timeout = 0
        self._cancel_restore()
        self._set_adjustment_value_for_fraction(self._restore_fraction)
        return False

    def _set_adjustment_value_for_fraction(self, fraction: float) -> None:
        adjustment = self.get_vadjustment()
        if adjustment is None:
            return
        maximum = adjustment.get_upper() - adjustment.get_page_size()
        if maximum > 0:
            self._set_adjustment_value(fraction * maximum)

    def scroll_to_anchor(self, name: str) -> None:
        renderer = self._renderer
        if renderer is None:
            return
        widget = renderer.get_anchor(name)
        if widget is not None:
            self.scroll_to_widget(widget, sync=False)

    # -- navigation helpers (used by Vim navigation) ---------------------

    def content_widget(self) -> Gtk.Widget | None:
        """Return the rendered content tree, or None when nothing is shown."""
        if self._stack.get_visible_child_name() != "content":
            return None
        return self._clamp.get_child()

    def iter_labels(self):
        """Yield the rendered labels in document order."""
        content = self.content_widget()
        if content is None:
            return
        stack = [content]
        while stack:
            widget = stack.pop()
            if isinstance(widget, Gtk.Label):
                yield widget
            children = []
            child = widget.get_first_child()
            while child is not None:
                children.append(child)
                child = child.get_next_sibling()
            stack.extend(reversed(children))

    def widget_y(self, widget: Gtk.Widget) -> float | None:
        """Return the top of ``widget`` in scrollable content coordinates."""
        try:
            success, rect = widget.compute_bounds(self._clamp)
        except (TypeError, AttributeError):
            return None
        if not success:
            return None
        return rect.get_y()

    def scroll_to_value(self, value: float, *, sync: bool = True) -> None:
        """Scroll to ``value``, clamped to the content.

        With ``sync`` the change is reported through
        ``scroll-fraction-changed`` like a user scroll.
        """
        adjustment = self.get_vadjustment()
        if adjustment is None:
            return
        self._cancel_restore()
        maximum = adjustment.get_upper() - adjustment.get_page_size()
        value = max(adjustment.get_lower(), min(value, max(0.0, maximum)))
        if sync:
            adjustment.set_value(value)
        else:
            self._set_adjustment_value(value)

    def scroll_by(self, delta: float) -> None:
        adjustment = self.get_vadjustment()
        if adjustment is not None:
            self.scroll_to_value(adjustment.get_value() + delta)

    def scroll_to_widget(
        self, widget: Gtk.Widget, offset: float = 0.0, *, sync: bool = True
    ) -> None:
        """Scroll so ``widget`` (plus ``offset`` pixels) sits near the top."""
        y = self.widget_y(widget)
        if y is not None:
            self.scroll_to_value(max(0.0, y + offset - 12), sync=sync)

    def _open_external(self, uri: str) -> None:
        # Local .md links open in a new MD Split instance; other file links
        # go through FileLauncher because Gtk.UriLauncher sends plain OpenURI
        # portal calls, which xdg-desktop-portal >= 1.21 rejects for file://
        # URIs ("The application launch failed"); FileLauncher passes a GFile
        # and uses the fd-based OpenFile path.
        if uri.startswith("file:"):
            file_uri = uri.split("#", 1)[0].split("?", 1)[0]
            if launcher_mod.spawn_markdown_instance(uri):
                return
            launcher = Gtk.FileLauncher.new(Gio.File.new_for_uri(file_uri))
            launcher.launch(self.get_root(), None, self._on_launch_finished, None)
            return
        launcher = Gtk.UriLauncher.new(uri)
        launcher.launch(
            self.get_root(), None, self._on_launch_finished, None
        )

    def _on_launch_finished(self, launcher, result, _data) -> None:
        try:
            launcher.launch_finish(result)
        except GLib.Error as error:
            log.warning("Could not open link: %s", error)
