"""Headless tests for asynchronous UTF-8 file loading and saving."""

import os
import stat
import sys
import tempfile
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib

from src import fileio


def run_loop(loop):
    timed_out = []

    def on_timeout():
        timed_out.append(True)
        loop.quit()
        return False

    timeout = GLib.timeout_add_seconds(5, on_timeout)
    loop.run()
    if not timed_out:
        GLib.source_remove(timeout)
    assert not timed_out, "asynchronous file operation timed out"


def save(file, text, etag=None):
    result = {}
    loop = GLib.MainLoop()

    def saved(error, new_etag):
        result["error"] = error
        result["etag"] = new_etag
        loop.quit()

    fileio.save_text_async(file, text, saved, etag=etag)
    run_loop(loop)
    return result


def load(file):
    result = {}
    loop = GLib.MainLoop()

    def loaded(loaded_text, etag, error):
        result["text"] = loaded_text
        result["etag"] = etag
        result["error"] = error
        loop.quit()

    fileio.load_text_async(file, loaded)
    run_loop(loop)
    return result


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    path = root / "note.md"
    file = Gio.File.new_for_path(str(path))
    text = "# Saved\n\nNative paragraph.\n"

    saved = save(file, text)
    assert saved["error"] is None, saved["error"]
    assert path.read_text(encoding="utf-8") == text
    assert saved["etag"]

    loaded = load(file)
    assert loaded["error"] is None, loaded["error"]
    assert loaded["text"] == text
    assert loaded["etag"] == saved["etag"]

    path.write_bytes(b"\xef\xbb\xbfBOM text")
    loaded = load(file)
    assert loaded["error"] is None, loaded["error"]
    assert loaded["text"] == "BOM text"

    path.write_bytes(b"\xff\xfe\x00bad")
    loaded = load(file)
    assert isinstance(loaded["error"], UnicodeDecodeError)
    assert loaded["text"] is None

    target = root / "target.md"
    target.write_text("old", encoding="utf-8")
    target.chmod(0o600)
    link = root / "link.md"
    link.symlink_to(target)
    saved = save(Gio.File.new_for_path(str(link)), "new")
    assert saved["error"] is None, saved["error"]
    assert link.is_symlink(), "saving must not replace symlinks"
    assert target.read_text(encoding="utf-8") == "new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(link.stat().st_mode) == 0o600

    conflict_path = root / "conflict.md"
    conflict_path.write_text("one", encoding="utf-8")
    first = save(Gio.File.new_for_path(str(conflict_path)), "two")
    assert first["error"] is None, first["error"]
    conflict_path.write_text("external", encoding="utf-8")
    conflict = save(
        Gio.File.new_for_path(str(conflict_path)),
        "three",
        etag=first["etag"],
    )
    assert isinstance(conflict["error"], GLib.Error)
    assert conflict["error"].matches(
        Gio.io_error_quark(), Gio.IOErrorEnum.WRONG_ETAG
    )
    assert conflict_path.read_text(encoding="utf-8") == "external"

    limit_path = root / "too-large.md"
    limit_path.write_bytes(b"x" * 2048)
    original_limit = fileio.MAX_DOCUMENT_BYTES
    fileio.MAX_DOCUMENT_BYTES = 1024
    try:
        limited = load(Gio.File.new_for_path(str(limit_path)))
    finally:
        fileio.MAX_DOCUMENT_BYTES = original_limit
    assert isinstance(limited["error"], fileio.FileTooLargeError)

print("ok: headless file I/O")
