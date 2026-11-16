#!/usr/bin/env python3
"""Run Meson tests with a sanitized environment.

Meson records the caller's environment in its test logs. Running tests
directly from a shell that contains API keys or tokens therefore copies those
secrets into build/meson-logs. This wrapper passes only the variables needed
by the build and GUI tests.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_FILES = (
    ROOT / "build/meson-logs/testlog.txt",
    ROOT / "build/meson-logs/testlog.json",
    ROOT / "build/meson-logs/testlog.junit.xml",
)
SAFE_ENV = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
    "GDK_BACKEND",
    "GTK_IM_MODULE",
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_WORKSPACE",
)


def main() -> int:
    for path in LOG_FILES:
        path.unlink(missing_ok=True)

    env = {
        key: os.environ[key]
        for key in SAFE_ENV
        if key in os.environ
    }
    env.update(
        {
            "GSETTINGS_BACKEND": "memory",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    command = sys.argv[1:] or ["-C", "build", "--print-errorlogs"]
    return subprocess.run(
        ["meson", "test", *command],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
