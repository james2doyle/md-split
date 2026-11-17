"""Headless tests for the document model."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio

from src.document import (
    Document,
    count_words,
    reading_time_minutes,
    reading_time_minutes_for_words,
    text_statistics,
)

# Counts treat punctuation separately and count CJK characters as words.
assert count_words("") == 0
assert count_words("Hello world") == 2
assert count_words("Hello, world!") == 2
assert count_words("don't stop") == 2
assert count_words("你好 世界") == 4
assert count_words("Hello, 世界!") == 3

# Reading time is predictable and empty text takes no time.
assert reading_time_minutes("") == 0
assert reading_time_minutes("word " * 199) == 1
assert reading_time_minutes("word " * 200) == 1
assert reading_time_minutes("word " * 201) == 2
assert reading_time_minutes_for_words(0) == 0
assert reading_time_minutes_for_words(1) == 1

words, characters, minutes = text_statistics("Hello, 世界!")
assert (words, characters, minutes) == (3, 10, 1)

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
