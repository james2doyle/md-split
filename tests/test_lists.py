"""Headless tests for list continuation and empty-item exit."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src.editing import continue_list


def apply(text, edit):
    assert edit is not None
    return edit.apply(text)


# Return continues bullet, ordered, task, and nested list items.
edit = continue_list("- item", 6)
assert edit is not None
assert apply("- item", edit) == "- item\n- "
assert (edit.selection_start, edit.selection_end) == (9, 9)

edit = continue_list("1. item", 7)
assert edit is not None
assert apply("1. item", edit) == "1. item\n2. "

edit = continue_list("3) item", 7)
assert edit is not None
assert apply("3) item", edit) == "3) item\n4) "

edit = continue_list("- [x] done", 10)
assert edit is not None
assert apply("- [x] done", edit) == "- [x] done\n- [ ] "

edit = continue_list("  - nested", 10)
assert edit is not None
assert apply("  - nested", edit) == "  - nested\n  - "

for marker in ("*", "+"):
    source = f"{marker} item"
    edit = continue_list(source, len(source))
    assert edit is not None
    assert apply(source, edit) == f"{source}\n{marker} "

# Enter on an empty item removes it and leaves a blank line.
for source, cursor, expected in (
    ("- ", 2, "\n"),
    ("1. ", 3, "\n"),
    ("- [ ] ", 6, "\n"),
    ("- item\n- ", 9, "- item\n\n"),
    ("- item\n- \nnext", 9, "- item\n\nnext"),
):
    edit = continue_list(source, cursor)
    assert edit is not None, source
    assert apply(source, edit) == expected, source

# Cursor positions inside the marker or on non-list lines fall through.
assert continue_list("plain text", 10) is None
assert continue_list("- item", 1) is None
assert continue_list("", 0) is None
assert continue_list("-item", 5) is None

# Return in the middle of an item splits it and continues the list.
edit = continue_list("- one two", 4)
assert edit is not None
assert apply("- one two", edit) == "- on\n- e two"
assert (edit.selection_start, edit.selection_end) == (7, 7)

# Tabs, larger ordered numbers, and whitespace-only items are supported.
edit = continue_list("\t- item", 7)
assert edit is not None
assert apply("\t- item", edit) == "\t- item\n\t- "

# CRLF documents continue and exit items with CRLF line endings.
for source, cursor, expected in (
    ("- one\r\n- two\r\n", 5, "- one\r\n- \r\n- two\r\n"),
    ("- \r\n", 2, "\r\n"),
    ("- one\r\n- \r\nnext", 9, "- one\r\n\r\nnext"),
    ("1. one\r\n", 6, "1. one\r\n2. \r\n"),
):
    edit = continue_list(source, cursor)
    assert edit is not None, source
    assert apply(source, edit) == expected, (source, apply(source, edit))

edit = continue_list("10. item", 8)
assert edit is not None
assert apply("10. item", edit) == "10. item\n11. "

for source, cursor in (("-   ", 4), ("+   ", 4), ("- item\n-   ", 11)):
    edit = continue_list(source, cursor)
    assert edit is not None, source
    assert apply(source, edit) == ("- item\n\n" if "\n" in source else "\n")

print("ok: list continuation")
