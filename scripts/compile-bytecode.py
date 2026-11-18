#!/usr/bin/env python3
# SPDX-License-Identifier: MIT

"""Meson install script: precompile the installed Python package.

Packaged installs (Flatpak, AppImage, /usr) are read-only, so without shipped
bytecode Python recompiles every module on every launch. Hash-based
``unchecked-hash`` pycs stay valid even when packaging resets file mtimes
(OSTree sets them to 0), and installed sources never change.
"""

from __future__ import annotations

import compileall
import os
import py_compile
import sys


def main() -> int:
    if os.environ.get("MESON_INSTALL_DRY_RUN"):
        return 0
    prefix = os.environ.get("MESON_INSTALL_DESTDIR_PREFIX")
    if not prefix or len(sys.argv) != 2:
        print("usage: compile-bytecode.py <dir relative to prefix>", file=sys.stderr)
        return 1
    target = os.path.join(prefix, sys.argv[1])
    ok = compileall.compile_dir(
        target,
        quiet=1,
        # Replace timestamp pycs left by earlier runs of a writable prefix.
        force=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
