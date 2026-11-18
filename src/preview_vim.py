# SPDX-License-Identifier: MIT

"""Vim-style navigation and search for the native Markdown preview.

The preview is a read-only widget tree, so it gets a small viewer keymap
(scrolling, heading jumps, ``/`` search) instead of GtkSourceView's editing
emulation. ``PreviewKeyParser`` and ``find_matches`` are pure Python so they
can be tested headless; ``PreviewVim`` is the GTK glue.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from gettext import gettext as _

LINE_STEP = 40.0
MAX_COUNT = 9999

_HEADING_CLASSES = ("md-h1", "md-h2", "md-h3", "md-h4", "md-h5", "md-h6")


@dataclass(frozen=True)
class PreviewAction:
    """A parsed preview command. ``count`` is None when none was typed."""

    name: str
    count: int | None = None

    @property
    def repeat(self) -> int:
        return self.count or 1


PENDING = PreviewAction("pending")
# Returned for an unknown second key of a sequence: swallow it, like Vim.
PENDING_RESET = PreviewAction("cancel-sequence")

# Single keys without Ctrl.
_PLAIN = {
    "j": "scroll-down",
    "Down": "scroll-down",
    "k": "scroll-up",
    "Up": "scroll-up",
    "space": "page-down",
    "Page_Down": "page-down",
    "Page_Up": "page-up",
    "Home": "top",
    "End": "bottom",
    "G": "bottom",
    "/": "search-forward",
    "?": "search-backward",
    "n": "next-match",
    "N": "previous-match",
    "i": "focus-editor",
    "e": "focus-editor",
}

# Keys pressed with Ctrl.
_CTRL = {
    "d": "half-page-down",
    "u": "half-page-up",
    "f": "page-down",
    "b": "page-up",
    "e": "scroll-down",
    "y": "scroll-up",
}

# Second key of a two-key sequence, keyed by the first.
_SEQUENCES = {
    "g": {"g": "top"},
    "]": {"]": "next-heading"},
    "[": {"[": "previous-heading"},
    "ctrl-w": {
        "w": "focus-other",
        "W": "focus-other",
        "ctrl-w": "focus-other",
        "p": "focus-other",
        "h": "focus-editor",
        "ctrl-h": "focus-editor",
        "l": "focus-preview",
        "ctrl-l": "focus-preview",
    },
}


class PreviewKeyParser:
    """Turn key presses into preview actions, Vim style.

    ``feed`` takes a key name (a printable character such as ``"j"`` or
    ``"G"``, or a GDK key name such as ``"Escape"``, ``"space"`` or
    ``"Page_Down"``). It returns a ``PreviewAction``, ``PENDING`` while a
    count or sequence is incomplete, or ``None`` when the key is not a
    preview command and should propagate.
    """

    def __init__(self) -> None:
        self._count = ""
        self._prefix: str | None = None

    @property
    def pending(self) -> bool:
        return bool(self._count or self._prefix)

    def reset(self) -> None:
        self._count = ""
        self._prefix = None

    def _take_count(self) -> int | None:
        count = int(self._count) if self._count else None
        self.reset()
        if count is not None:
            count = min(count, MAX_COUNT)
        return count

    def feed(
        self, key: str, *, ctrl: bool = False, shift: bool = False
    ) -> PreviewAction | None:
        if key == "Escape" or (ctrl and key == "["):
            self.reset()
            return PreviewAction("cancel")

        token = f"ctrl-{key.lower()}" if ctrl else key

        if self._prefix is not None:
            name = _SEQUENCES[self._prefix].get(token)
            count = self._take_count()
            return PreviewAction(name, count) if name else PENDING_RESET

        if ctrl:
            if key.lower() == "w":
                self._prefix = "ctrl-w"
                return PENDING
            name = _CTRL.get(key.lower())
            if name is None:
                self.reset()
                return None
            return PreviewAction(name, self._take_count())

        if len(key) == 1 and key.isdigit() and (key != "0" or self._count):
            if len(self._count) < len(str(MAX_COUNT)):
                self._count += key
            return PENDING

        if key in _SEQUENCES:
            self._prefix = key
            return PENDING

        if key == "space" and shift:
            return PreviewAction("page-up", self._take_count())

        name = _PLAIN.get(key)
        if name is None:
            self.reset()
            return None
        count = self._take_count()
        if name == "bottom" and count is not None:
            return PreviewAction("goto-percent", count)
        return PreviewAction(name, count)


@dataclass(frozen=True)
class Match:
    label: int
    start: int
    end: int


def compile_query(query: str) -> re.Pattern[str] | None:
    """Compile a search query with smartcase; None when it is invalid."""
    if not query:
        return None
    flags = 0 if any(ch.isupper() for ch in query) else re.IGNORECASE
    try:
        return re.compile(query, flags)
    except re.error:
        return None


def find_matches(texts: list[str], query: str) -> list[Match]:
    """Return every non-empty match of ``query`` across ``texts`` in order."""
    pattern = compile_query(query)
    if pattern is None:
        return []
    matches = []
    for index, text in enumerate(texts):
        for found in pattern.finditer(text):
            if found.end() > found.start():
                matches.append(Match(index, found.start(), found.end()))
    return matches


# -- GTK glue ------------------------------------------------------------

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")

from gi.repository import Gdk, Gtk, Pango  # noqa: E402


def key_name(keyval: int) -> str | None:
    """Map a GDK keyval to the names ``PreviewKeyParser`` understands."""
    codepoint = Gdk.keyval_to_unicode(keyval)
    if codepoint == 0x20:
        return "space"
    if codepoint and chr(codepoint).isprintable():
        return chr(codepoint)
    return Gdk.keyval_name(keyval)


class PreviewVim:
    """Attach Vim navigation and ``/`` search to a ``MarkdownView``."""

    def __init__(
        self,
        view,
        *,
        prompt_revealer: Gtk.Revealer,
        prompt_prefix: Gtk.Label,
        prompt_entry: Gtk.Entry,
        on_status: Callable[[str], None],
        on_focus: Callable[[str], None],
    ) -> None:
        self._view = view
        self._revealer = prompt_revealer
        self._prefix = prompt_prefix
        self._entry = prompt_entry
        self._on_status = on_status
        self._on_focus = on_focus
        self._parser = PreviewKeyParser()
        self._enabled = False
        self._query = ""
        self._forward = True
        self._prompt_forward = True
        # (y, start) of the current match; None before the first jump.
        self._position: tuple[float, int] | None = None
        self._highlighted: Gtk.Label | None = None

        self._controller = Gtk.EventControllerKey()
        self._controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._controller.connect("key-pressed", self._on_key_pressed)

        self._entry_key = Gtk.EventControllerKey()
        self._entry_key.connect("key-pressed", self._on_entry_key_pressed)
        self._entry.add_controller(self._entry_key)
        self._entry_handlers = [
            self._entry.connect("activate", self._on_entry_activate),
        ]

    # -- lifecycle -------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            self._view.add_controller(self._controller)
        else:
            self._view.remove_controller(self._controller)
            self._parser.reset()
            self._close_prompt(refocus=False)
            self._clear_highlight()

    def shutdown(self) -> None:
        self.set_enabled(False)
        for handler in self._entry_handlers:
            self._entry.disconnect(handler)
        self._entry_handlers.clear()
        self._entry.remove_controller(self._entry_key)

    # -- keys ------------------------------------------------------------

    def _on_key_pressed(
        self, _controller, keyval: int, _keycode: int, state: Gdk.ModifierType
    ) -> bool:
        modifiers = state & Gtk.accelerator_get_default_mod_mask()
        if modifiers & (Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK):
            return False
        name = key_name(keyval)
        if name is None:
            return False
        action = self._parser.feed(
            name,
            ctrl=bool(modifiers & Gdk.ModifierType.CONTROL_MASK),
            shift=bool(modifiers & Gdk.ModifierType.SHIFT_MASK),
        )
        if action is None:
            return False
        self.perform(action)
        return True

    def perform(self, action: PreviewAction) -> None:
        adjustment = self._view.get_vadjustment()
        page = adjustment.get_page_size() if adjustment is not None else 0.0
        name = action.name
        if name in ("pending", "cancel-sequence"):
            return
        if name == "cancel":
            self._clear_highlight()
            self._on_status("")
        elif name == "scroll-down":
            self._view.scroll_by(LINE_STEP * action.repeat)
        elif name == "scroll-up":
            self._view.scroll_by(-LINE_STEP * action.repeat)
        elif name == "half-page-down":
            self._view.scroll_by(page / 2 * action.repeat)
        elif name == "half-page-up":
            self._view.scroll_by(-page / 2 * action.repeat)
        elif name == "page-down":
            self._view.scroll_by(page * 0.9 * action.repeat)
        elif name == "page-up":
            self._view.scroll_by(-page * 0.9 * action.repeat)
        elif name == "top":
            self._view.scroll_to_value(0.0)
        elif name == "bottom":
            if adjustment is not None:
                self._view.scroll_to_value(adjustment.get_upper())
        elif name == "goto-percent":
            if adjustment is not None:
                maximum = adjustment.get_upper() - page
                percent = min(action.repeat, 100) / 100
                self._view.scroll_to_value(maximum * percent)
        elif name in ("next-heading", "previous-heading"):
            for _step in range(action.repeat):
                self._jump_heading(forward=name == "next-heading")
        elif name in ("search-forward", "search-backward"):
            self.open_prompt(forward=name == "search-forward")
        elif name in ("next-match", "previous-match"):
            if not self._query:
                self._on_status(_("No previous search"))
                return
            forward = self._forward == (name == "next-match")
            for _step in range(action.repeat):
                if not self._step_match(forward):
                    break
        elif name == "focus-editor":
            self._on_focus("editor")
        elif name == "focus-preview":
            self._on_focus("preview")
        elif name == "focus-other":
            self._on_focus("other")

    # -- headings --------------------------------------------------------

    def _headings(self) -> Iterator[tuple[float, Gtk.Label]]:
        for label in self._view.iter_labels():
            if not any(label.has_css_class(c) for c in _HEADING_CLASSES):
                continue
            y = self._view.widget_y(label)
            if y is not None:
                yield y, label

    def _jump_heading(self, *, forward: bool) -> None:
        adjustment = self._view.get_vadjustment()
        if adjustment is None:
            return
        # Headings are placed 12 px below the top when jumped to.
        current = adjustment.get_value() + 12
        target = None
        for y, _label in self._headings():
            if forward and y > current + 1:
                target = y
                break
            if not forward and y < current - 1:
                target = y
        if target is not None:
            self._view.scroll_to_value(max(0.0, target - 12))

    # -- search ----------------------------------------------------------

    def open_prompt(self, *, forward: bool) -> None:
        self._parser.reset()
        self._prompt_forward = forward
        self._prefix.set_label("/" if forward else "?")
        self._entry.set_text("")
        self._revealer.set_visible(True)
        self._revealer.set_reveal_child(True)
        self._entry.grab_focus()

    @property
    def prompt_open(self) -> bool:
        return self._revealer.get_reveal_child()

    def _close_prompt(self, *, refocus: bool) -> None:
        if not self._revealer.get_reveal_child():
            return
        self._revealer.set_reveal_child(False)
        self._revealer.set_visible(False)
        if refocus:
            self._view.grab_focus()

    def _on_entry_key_pressed(
        self, _controller, keyval: int, _keycode: int, state: Gdk.ModifierType
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            self._close_prompt(refocus=True)
            return True
        if (
            keyval == Gdk.KEY_BackSpace
            and not self._entry.get_text()
        ):
            self._close_prompt(refocus=True)
            return True
        return False

    def _on_entry_activate(self, _entry) -> None:
        query = self._entry.get_text()
        self._close_prompt(refocus=True)
        if query:
            self.search(query, forward=self._prompt_forward)

    def search(self, query: str, *, forward: bool = True) -> bool:
        """Run a new search from the top of the viewport."""
        self._query = query
        self._forward = forward
        adjustment = self._view.get_vadjustment()
        top = adjustment.get_value() if adjustment is not None else 0.0
        # Start just above (forward) or just below (backward) the viewport
        # top so a match at the very top is found first.
        self._position = (top - 13, -1) if forward else (top + 13, -1)
        if compile_query(query) is None:
            self._on_status(_("Invalid pattern: {query}").format(query=query))
            return False
        return self._step_match(forward)

    def _collect(self) -> list[tuple[float, int, int, Gtk.Label]]:
        labels = [
            label
            for label in self._view.iter_labels()
            if label.get_mapped()
        ]
        found = []
        for match in find_matches(
            [label.get_text() for label in labels], self._query
        ):
            label = labels[match.label]
            y = self._view.widget_y(label)
            if y is None:
                continue
            found.append((y + _line_offset(label, match.start), match.start,
                          match.end, label))
        found.sort(key=lambda item: (item[0], item[1]))
        return found

    def _step_match(self, forward: bool) -> bool:
        matches = self._collect()
        if not matches:
            self._clear_highlight()
            self._on_status(
                _("Pattern not found: {query}").format(query=self._query)
            )
            return False
        position = self._position or (float("-inf"), -1)
        wrapped = False
        if forward:
            index = next(
                (
                    i
                    for i, item in enumerate(matches)
                    if (item[0], item[1]) > position
                ),
                None,
            )
            if index is None:
                index, wrapped = 0, True
        else:
            index = next(
                (
                    i
                    for i in range(len(matches) - 1, -1, -1)
                    if (matches[i][0], matches[i][1]) < position
                ),
                None,
            )
            if index is None:
                index, wrapped = len(matches) - 1, True
        y, start, end, label = matches[index]
        self._position = (y, start)
        self._highlight(label, start, end)
        adjustment = self._view.get_vadjustment()
        page = adjustment.get_page_size() if adjustment is not None else 0.0
        # Keep the match a third of the way down the viewport.
        self._view.scroll_to_value(max(0.0, y - page / 3))
        status = f"{'/' if self._forward else '?'}{self._query} [{index + 1}/{len(matches)}]"
        if wrapped:
            status += "  " + (
                _("search hit BOTTOM, continuing at TOP")
                if forward
                else _("search hit TOP, continuing at BOTTOM")
            )
        self._on_status(status)
        return True

    def _highlight(self, label: Gtk.Label, start: int, end: int) -> None:
        if self._highlighted is not None and self._highlighted is not label:
            self._clear_highlight()
        self._highlighted = label
        label.select_region(start, end)

    def _clear_highlight(self) -> None:
        label = self._highlighted
        self._highlighted = None
        if label is not None and label.get_parent() is not None:
            label.select_region(0, 0)


def _line_offset(label: Gtk.Label, char_offset: int) -> float:
    """Return the y of ``char_offset``'s line inside ``label`` in pixels."""
    text = label.get_text()
    byte_index = len(text[:char_offset].encode("utf-8"))
    try:
        rect = label.get_layout().index_to_pos(byte_index)
    except (TypeError, AttributeError):
        return 0.0
    return rect.y / Pango.SCALE
