"""Headless tests for the document model."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from src.document import Document

doc = Document()
assert doc.display_name == "Untitled.md"
assert doc.directory is None
assert not doc.is_dirty
assert doc.word_count == 0
assert doc.character_count == 0

doc.set_text("Hello world\n\nSecond paragraph.")
assert doc.is_dirty
assert doc.word_count == 4
assert doc.character_count == len("Hello world\n\nSecond paragraph.")

file = Gio.File.new_for_path("/tmp/example.md")
doc.load("Saved text", file)
assert doc.display_name == "example.md"
assert doc.directory is not None
assert not doc.is_dirty
assert doc.file is file

doc.set_text("Changed text")
assert doc.is_dirty
doc.mark_saved()
assert not doc.is_dirty
assert doc.file is file

doc.reset()
assert doc.file is None
assert doc.text == ""
assert not doc.is_dirty

print("ok: document model")
