# SPDX-License-Identifier: MIT

"""Targeted filtering for known benign GTK and libenchant warnings.

Three upstream warnings are noisy but do not indicate a document or
data-loss problem:

- ``GtkTextView`` updates scrollbar adjustments during snapshot
  (GNOME/gtk#6057), producing ``Trying to snapshot GtkGizmo ...`` messages.
- The Wayland text-input context warns when a selection exceeds its 4 KiB
  surrounding-text window, producing ``notify_surrounding_text: code should
  not be reached``.
- libenchant warns about provider plugins that are not installed while it
  initializes the spelling backend. The dictionaries that are available still
  load through their working plugin.

The filter keeps unrelated warnings visible. Set
``MD_SPLIT_SHOW_WARNINGS=1`` to disable it while debugging.
"""

from __future__ import annotations

import os
import re

import gi

gi.require_version("GLib", "2.0")

from gi.repository import GLib

_SNAPSHOT_WARNING = re.compile(
    r"^Trying to snapshot GtkGizmo 0x[0-9a-fA-F]+ "
    r"without a current allocation$"
)
_WAYLAND_IM_WARNING = re.compile(
    r"^\(.*gtkimcontextwayland\.c:\d+\):"
    r"notify_surrounding_text: code should not be reached$"
)
_ENCHANT_PLUGIN_WARNING = re.compile(
    r"^broker\.vala:\d+: Error loading plugin: "
    r"lib[^:\s]+\.so(?:\.\d+)*: "
    r"cannot open shared object file: No such file or directory$"
)


def is_known_warning(domain: str | None, message: str | None) -> bool:
    """Return True for the known harmless GTK and libenchant messages."""
    if not message:
        return False
    if domain == "Gtk":
        return bool(
            _SNAPSHOT_WARNING.match(message)
            or _WAYLAND_IM_WARNING.match(message)
        )
    if domain == "libenchant":
        return bool(_ENCHANT_PLUGIN_WARNING.match(message))
    return False


def _on_known_warning(
    domain: str | None,
    level: GLib.LogLevelFlags,
    message: str | None,
    user_data: object = None,
) -> None:
    if bool(level & GLib.LogLevelFlags.LEVEL_WARNING) and is_known_warning(
        domain, message
    ):
        return
    GLib.log_default_handler(domain, level, message, user_data)


def install_known_warning_filter() -> None:
    """Install the narrow warning filter once for the application run."""
    if os.environ.get("MD_SPLIT_SHOW_WARNINGS") == "1":
        return
    for domain in ("Gtk", "libenchant"):
        GLib.log_set_handler(
            domain, GLib.LogLevelFlags.LEVEL_WARNING, _on_known_warning
        )
