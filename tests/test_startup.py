"""Headless checks that first-window imports stay lazy.

Run via ``meson test``; these subprocesses import the UI modules without a
display, so only module loading is exercised.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent
RESOURCE = os.environ.get("APP_RESOURCE")

if not RESOURCE or not os.path.exists(RESOURCE):
    print("SKIP: APP_RESOURCE is not set")
    sys.exit(77)

CODE = """
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

Gio.Resource.load(os.environ["APP_RESOURCE"])._register()

import src.window

lazy = ("src.renderer", "src.markdown_parser", "src.formatting")
loaded = sorted(name for name in lazy if name in sys.modules)
print(",".join(loaded))
"""

result = subprocess.run(
    [sys.executable, "-c", CODE],
    cwd=SOURCE_ROOT,
    env=os.environ,
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    sys.stderr.write(result.stderr)
    raise SystemExit(result.returncode)

loaded = result.stdout.strip()
assert loaded == "", f"startup imports should be lazy, loaded: {loaded}"

print("ok: lazy startup imports")
