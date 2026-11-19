"""Headless tests for the known-warning filter."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from src.logging_utils import (
    _on_known_warning,
    install_known_warning_filter,
    is_known_warning,
)

# GtkTextView updates scrollbar adjustments during snapshot. This is a noisy
# upstream GTK warning (GNOME/gtk#6057), not a document error.
assert is_known_warning(
    "Gtk",
    "Trying to snapshot GtkGizmo 0x5652346ad190 "
    "without a current allocation",
)
assert is_known_warning(
    "Gtk",
    "Trying to snapshot GtkGizmo 0xabcDEF without a current allocation",
)

# Wayland text-input warns when a selection is larger than its 4 KiB
# surrounding-text window. It is harmless but noisy.
assert is_known_warning(
    "Gtk",
    "(../gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached",
)
assert is_known_warning(
    "Gtk",
    "(/build/gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached",
)

# A compositor throttling hint can arrive while GDK is still preparing a
# frame. GTK logs its internal check as a warning.
assert is_known_warning(
    "Gdk",
    "(../gtk/gdk/gdkframetimings.c:443):"
    "gdk_frame_timings_throttling_hint: runtime check failed: "
    "(self->result != GDK_FRAME_PREPARING)",
)
assert is_known_warning(
    "Gdk",
    "(/build/gtk/gdk/gdkframetimings.c:443):"
    "gdk_frame_timings_throttling_hint: runtime check failed: "
    "(self->result != GDK_FRAME_PREPARING)",
)
assert is_known_warning(
    "Gdk",
    "Duplicate call to gdk_frame_timings_presented() with different "
    "values: presentation time is 50.5ms off from expected",
)
assert is_known_warning(
    "Gdk",
    "Duplicate call to gdk_frame_timings_presented() with different "
    "values: presentation time is 16.650ms off from expected",
)

# libenchant warns for provider plugins that are not installed. Other
# providers (for example hunspell) still supply dictionaries.
assert is_known_warning(
    "libenchant",
    "broker.vala:159: Error loading plugin: libaspell.so.15: "
    "cannot open shared object file: No such file or directory",
)
assert is_known_warning(
    "libenchant",
    "broker.vala:159: Error loading plugin: libnuspell.so.5: "
    "cannot open shared object file: No such file or directory",
)

# The filter must stay narrow.
assert not is_known_warning("Gtk", "Some other GTK warning")
assert not is_known_warning(
    "Gtk", "Trying to snapshot GtkGizmo without a current allocation"
)
assert not is_known_warning(
    "Gtk", "Trying to snapshot GtkWidget 0x123 without a current allocation"
)
assert not is_known_warning(
    "Gdk", "Trying to snapshot GtkGizmo 0x123 without a current allocation"
)
assert not is_known_warning(
    "Gtk",
    "prefix: (../gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached",
)
assert not is_known_warning(
    "Gtk",
    "(../gtk/gtk/gtkimcontextwayland.c:410):"
    "notify_surrounding_text: code should not be reached: extra",
)
assert not is_known_warning("Gdk", "Some other GDK warning")
assert not is_known_warning(
    "Gtk",
    "(../gtk/gdk/gdkframetimings.c:443):"
    "gdk_frame_timings_throttling_hint: runtime check failed: "
    "(self->result != GDK_FRAME_PREPARING)",
)
assert not is_known_warning(
    "Gdk",
    "(../gtk/gdk/gdkframetimings.c:443):"
    "gdk_frame_timings_throttling_hint: runtime check failed: "
    "(some other check)",
)
assert not is_known_warning(
    "Gdk",
    "Duplicate call to gdk_frame_timings_submitted() with different values.",
)
assert not is_known_warning(
    "Gdk",
    "Duplicate call to gdk_frame_timings_presented() with different "
    "values: presentation time is soon",
)
assert not is_known_warning(
    "Gtk",
    "Duplicate call to gdk_frame_timings_presented() with different "
    "values: presentation time is 50.5ms off from expected",
)
assert not is_known_warning(
    "libenchant",
    "broker.vala:159: Error loading plugin: libaspell.so.15: "
    "cannot open shared object file: Permission denied",
)
assert not is_known_warning(
    "libenchant",
    "broker.vala:159: Error loading plugin: libaspell.so.15",
)
assert not is_known_warning(
    "Gtk",
    "broker.vala:159: Error loading plugin: libaspell.so.15: "
    "cannot open shared object file: No such file or directory",
)

# The handler drops matching warnings and delegates everything else.
calls = []
original_handler = GLib.log_default_handler
GLib.log_default_handler = lambda *args: calls.append(args)
try:
    _on_known_warning(
        "Gtk",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "Trying to snapshot GtkGizmo 0x123 without a current allocation",
    )
    assert calls == []
    _on_known_warning(
        "libenchant",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "broker.vala:159: Error loading plugin: libaspell.so.15: "
        "cannot open shared object file: No such file or directory",
    )
    assert calls == []
    _on_known_warning(
        "Gdk",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "(../gtk/gdk/gdkframetimings.c:443):"
        "gdk_frame_timings_throttling_hint: runtime check failed: "
        "(self->result != GDK_FRAME_PREPARING)",
    )
    assert calls == []
    _on_known_warning(
        "Gdk",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "Duplicate call to gdk_frame_timings_presented() with different "
        "values: presentation time is 50.5ms off from expected",
    )
    assert calls == []
    _on_known_warning(
        "Gtk",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "An unrelated GTK warning",
    )
    assert len(calls) == 1
    _on_known_warning(
        "libenchant",
        GLib.LogLevelFlags.LEVEL_WARNING,
        "An unrelated libenchant warning",
    )
    assert len(calls) == 2
finally:
    GLib.log_default_handler = original_handler

install_known_warning_filter()

print("ok: known warning filter")
