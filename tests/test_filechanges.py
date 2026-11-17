"""Headless tests for external file-change decisions."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from src.filechanges import change_action, classify_event

assert classify_event(Gio.FileMonitorEvent.CHANGED) == "changed"
assert classify_event(Gio.FileMonitorEvent.CHANGES_DONE_HINT) == "changed"
assert classify_event(Gio.FileMonitorEvent.CREATED) == "changed"
assert classify_event(Gio.FileMonitorEvent.MOVED_IN) == "changed"
assert classify_event(Gio.FileMonitorEvent.DELETED) == "deleted"
assert classify_event(Gio.FileMonitorEvent.MOVED_OUT) == "deleted"
assert classify_event(Gio.FileMonitorEvent.PRE_UNMOUNT) == "ignore"

assert (
    change_action(
        "changed",
        dirty=False,
        self_saved=False,
        etag_changed=True,
        exists=True,
    )
    == "prompt"
)
assert (
    change_action(
        "changed",
        dirty=True,
        self_saved=False,
        etag_changed=True,
        exists=True,
    )
    == "conflict"
)
assert (
    change_action(
        "changed",
        dirty=True,
        self_saved=True,
        etag_changed=True,
        exists=True,
    )
    == "ignore"
)
assert (
    change_action(
        "changed",
        dirty=False,
        self_saved=False,
        etag_changed=False,
        exists=True,
    )
    == "ignore"
)
assert (
    change_action(
        "deleted",
        dirty=False,
        self_saved=False,
        etag_changed=False,
        exists=False,
    )
    == "deleted"
)
assert (
    change_action(
        "deleted",
        dirty=True,
        self_saved=True,
        etag_changed=True,
        exists=False,
    )
    == "deleted"
)

print("ok: external file changes")
