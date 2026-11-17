# SPDX-License-Identifier: MIT

"""Containment helpers for document-relative Markdown paths.

Markdown files are untrusted input: a relative or absolute path in a document
must not be able to read or open files outside the directory that contains the
document. Preview links, preview images and export images all resolve through
these helpers.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio


def document_root(
    base_dir: Path | None, base_file: Gio.File | None
) -> Path | None:
    """Return the directory that document-relative paths are confined to."""
    if base_dir is not None:
        return base_dir.resolve()
    if base_file is not None:
        parent = base_file.get_parent()
        if parent is None:
            return None
        local = parent.get_path()
        if local:
            return Path(local).resolve()
    return None


def ensure_file_extension(path: Path, extension: str) -> Path:
    """Return ``path`` with the export extension appended when missing."""
    suffix = extension if extension.startswith(".") else f".{extension}"
    if path.suffix.lower() == suffix.lower():
        return path
    return path.with_name(path.name + suffix)


def contained_file(path: Path, root: Path | None) -> Path | None:
    """Resolve ``path`` and return it only when it stays inside ``root``.

    Symlinks are resolved before the check so a link inside the document
    directory cannot point at a file outside it.
    """
    resolved = path.resolve()
    if root is None:
        return resolved
    if resolved.is_relative_to(root):
        return resolved
    return None
