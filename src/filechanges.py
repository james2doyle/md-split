# SPDX-License-Identifier: MIT

"""Decide how the editor reacts to external file events."""

from __future__ import annotations

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio

_CHANGED_EVENTS = {
    Gio.FileMonitorEvent.CHANGED,
    Gio.FileMonitorEvent.CHANGES_DONE_HINT,
    Gio.FileMonitorEvent.CREATED,
    Gio.FileMonitorEvent.MOVED_IN,
    Gio.FileMonitorEvent.RENAMED,
}
_DELETED_EVENTS = {
    Gio.FileMonitorEvent.DELETED,
    Gio.FileMonitorEvent.MOVED_OUT,
}


def classify_event(event_type: Gio.FileMonitorEvent) -> str:
    """Map a Gio event to ``changed``, ``deleted`` or ``ignore``."""
    if event_type in _DELETED_EVENTS:
        return "deleted"
    if event_type in _CHANGED_EVENTS:
        return "changed"
    return "ignore"


def change_action(
    kind: str,
    *,
    dirty: bool,
    self_saved: bool,
    etag_changed: bool,
    exists: bool,
) -> str:
    """Return ``ignore``, ``prompt``, ``conflict`` or ``deleted``."""
    if not exists:
        return "deleted"
    if kind == "ignore" or self_saved:
        return "ignore"
    if kind == "deleted":
        return "deleted"
    if not etag_changed:
        return "ignore"
    return "conflict" if dirty else "prompt"
