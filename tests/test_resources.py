"""Headless tests for packaged gresource content."""

import os
import sys

RESOURCE = os.environ.get("APP_RESOURCE")

if not RESOURCE or not os.path.exists(RESOURCE):
    print("SKIP: APP_RESOURCE is not set")
    sys.exit(77)

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

resource = Gio.Resource.load(RESOURCE)


def contents(path: str) -> bytes:
    return resource.lookup_data(path, Gio.ResourceLookupFlags.NONE).get_data()


demo = contents("/com/james2doyle/MdSplit/demo.md").decode("utf-8")
assert demo.startswith("# MD Split"), demo[:40]
assert len(demo) > 200

preferences = contents(
    "/com/james2doyle/MdSplit/preferences-dialog.ui"
).decode("utf-8")
assert "close_button" in preferences

window = contents("/com/james2doyle/MdSplit/window.ui").decode("utf-8")
assert "view_menu" in window
assert "toast_overlay" in window

assert contents("/com/james2doyle/MdSplit/style.css")

icon = contents(
    "/com/james2doyle/MdSplit/icons/scalable/apps/com.james2doyle.MdSplit.svg"
).decode("utf-8")
assert 'id="background"' in icon
assert 'width="128"' in icon

symbolic = contents(
    "/com/james2doyle/MdSplit/icons/symbolic/apps/"
    "com.james2doyle.MdSplit-symbolic.svg"
).decode("utf-8")
assert "<svg" in symbolic
assert 'fill="#2e3436"' in symbolic

print("ok: packaged resources")
