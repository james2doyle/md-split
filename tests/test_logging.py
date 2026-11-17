"""Headless tests for the known-GTK-warning filter."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from src.logging_utils import (
    _on_gtk_warning,
    install_known_gtk_warning_filter,
    is_known_gtk_warning,
)

# GtkTextView updates scrollbar adjustments during snapshot. This is a noisy
# upstream GTK warning (GNOME/gtk#6057), not a document error.
assert is_known_gtk_warning(
    "Gtk",
    "Trying to snapshot GtkGizmo 0x5652346ad190 "
    "without a current allocation",
)
assert is_known_gtk_warning(
    "Gtk",
    "Trying to snapshot GtkGizmo 0xabcDEF without a current allocation",
)

# Wayland text-input warns when a selection is larger than its 4 KiB
# surrounding-text window. It is harmless but noisy.
assert is_known_gtk_warning(
    "Gtk",
    "(../gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached",
)
assert is_known_gtk_warning(
    "Gtk",
    "(/build/gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached",
)

# The filter must stay narrow.
assert not is_known_gtk_warning("Gtk", "Some other GTK warning")
assert not is_known_gtk_warning(
    "Gtk", "Trying to snapshot GtkGizmo without a current allocation"
)
assert not is_known_gtk_warning(
    "Gtk", "Trying to snapshot GtkWidget 0x123 without a current allocation"
)
assert not is_known_gtk_warning(
    "Gdk", "Trying to snapshot GtkGizmo 0x123 without a current allocation"
)
assert not is_known_gtk_warning(
    "Gtk",
    "prefix: (../gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached",
)
assert not is_known_gtk_warning(
    "Gtk",
    "(../gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached: extra",
)

# The handler drops matching warnings and delegates everything else.
calls = []
original_handler = GLib.log_default_handler
GLib.log_default_handler = lambda *args: calls.append(args)
try:
    _on_gtk_warning(
        "Gtk",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "Trying to snapshot GtkGizmo 0x123 without a current allocation",
    )
    assert calls == []
    _on_gtk_warning(
        "Gtk",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "An unrelated GTK warning",
    )
    assert len(calls) == 1
finally:
    GLib.log_default_handler = original_handler

install_known_gtk_warning_filter()

print("ok: known GTK warning filter")
