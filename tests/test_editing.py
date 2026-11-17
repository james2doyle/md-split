"""Headless tests for text editing helpers used by the editor."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src.editing import (
    TextEdit,
    complete_link,
    format_code,
    format_inline,
    surround_selection,
    toggle_blockquote,
)


def apply(text, edit):
    assert edit is not None
    return edit.apply(text)


# Surround mappings include brackets, braces, parentheses, backticks and
# ASCII/typographic quotes.
for opening in ("[", "(", "{", "`", '"', "'", "\u2018", "\u201c"):
    edit = surround_selection("hello", 1, 4, opening)
    assert edit is not None, opening
    wrapped = apply("hello", edit)
    assert wrapped.startswith("h" + opening), (opening, wrapped)
    assert wrapped.endswith(edit.replacement[-1] + "o"), (opening, wrapped)
    assert "ell" in wrapped

assert apply("hello", surround_selection("hello", 1, 4, "[")) == "h[ell]o"
assert apply("hello", surround_selection("hello", 1, 4, "]")) == "h[ell]o"
assert surround_selection("hello", 2, 2, "[") is None
assert surround_selection("hello", 1, 4, "x") is None

# The selection remains selected inside the new pair.
edit = surround_selection("hello", 1, 4, "[")
assert edit is not None
assert (edit.selection_start, edit.selection_end) == (2, 5)

# Inline formatting wraps the selected text or inserts a cursor placeholder.
edit = format_inline("hello", 1, 4, "**", "**")
assert (edit.selection_start, edit.selection_end) == (3, 6)
assert apply("hello", edit) == "h**ell**o"

edit = format_inline("hello", 2, 2, "**", "**")
assert apply("hello", edit) == "he****llo"
assert (edit.selection_start, edit.selection_end) == (4, 4)

edit = format_inline("hello", 0, 5, "<u>", "</u>")
assert apply("hello", edit) == "<u>hello</u>"

# Inline code uses one backtick per side; multi-line selections use a fence.
edit = format_code("hello", 1, 4)
assert apply("hello", edit) == "h`ell`o"

edit = format_code("a\nb", 0, 3)
assert apply("a\nb", edit) == "```\na\nb\n```"

edit = format_code("hello", 2, 2)
assert apply("hello", edit) == "he``llo"
assert (edit.selection_start, edit.selection_end) == (3, 3)

# Block quotes add a marker to every line and toggle it back off.
edit = toggle_blockquote("one\ntwo", 0, 7)
assert apply("one\ntwo", edit) == "> one\n> two"

quoted = apply("one\ntwo", edit)
edit = toggle_blockquote(quoted, 0, len(quoted))
assert apply(quoted, edit) == "one\ntwo"

# A selection ending on a line break only quotes the line it ends in.
edit = toggle_blockquote("first\nsecond\nthird", 0, 6)
assert apply("first\nsecond\nthird", edit) == "> first\nsecond\nthird"
edit = toggle_blockquote("first\nsecond\nthird", 0, 7)
assert apply("first\nsecond\nthird", edit) == "> first\n> second\nthird"

# Ctrl+` uses a fence when the selection already spans multiple lines.
edit = format_code("a\nb", 0, 3)
assert apply("a\nb", edit).startswith("```\n")

# Typing ] after an empty [ completes a link and places the cursor in ().
edit = complete_link("abc [", 5)
assert edit is not None
completed = apply("abc [", edit)
assert completed == "abc []()"
assert (edit.selection_start, edit.selection_end) == (7, 7)
assert complete_link("abc", 3) is None
assert complete_link("abc [x", 6) is None
assert complete_link("abc  [", 6) is not None

# Edits are immutable and carry an explicit replacement range.
edit = TextEdit(1, 2, "X", 2, 2)
assert edit.apply("abc") == "aXc"

print("ok: editing helpers")
