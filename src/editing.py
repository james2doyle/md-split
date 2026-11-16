# SPDX-License-Identifier: MIT

"""Pure text-editing helpers for the Markdown editor.

The helpers return a :class:`TextEdit` describing a replacement instead of
touching a GtkTextBuffer directly. That keeps the behavior testable without a
display and lets the window apply an edit as one undoable user action.
"""

from __future__ import annotations

from dataclasses import dataclass

SURROUND_PAIRS = {
    "[": ("[", "]"),
    "]": ("[", "]"),
    "(": ("(", ")"),
    ")": ("(", ")"),
    "{": ("{", "}"),
    "}": ("{", "}"),
    "`": ("`", "`"),
    '"': ('"', '"'),
    "'": ("'", "'"),
    "\u2018": ("\u2018", "\u2019"),
    "\u2019": ("\u2018", "\u2019"),
    "\u201c": ("\u201c", "\u201d"),
    "\u201d": ("\u201c", "\u201d"),
}


@dataclass(frozen=True)
class TextEdit:
    """A replacement range and the selection to restore afterward."""

    start: int
    end: int
    replacement: str
    selection_start: int
    selection_end: int

    def apply(self, text: str) -> str:
        return text[: self.start] + self.replacement + text[self.end :]


def surround_selection(
    text: str, start: int, end: int, character: str
) -> TextEdit | None:
    """Wrap a non-empty selection with the pair for ``character``."""
    if start == end:
        return None
    pair = SURROUND_PAIRS.get(character)
    if pair is None:
        return None

    start, end = sorted((start, end))
    opening, closing = pair
    selected = text[start:end]
    return TextEdit(
        start=start,
        end=end,
        replacement=f"{opening}{selected}{closing}",
        selection_start=start + len(opening),
        selection_end=start + len(opening) + len(selected),
    )


def complete_link(text: str, cursor: int) -> TextEdit | None:
    """Complete a bare ``[`` with ``]()`` and place the cursor in the parens."""
    if cursor <= 0 or cursor > len(text):
        return None
    if text[cursor - 1 : cursor] != "[":
        return None
    return TextEdit(
        start=cursor,
        end=cursor,
        replacement="]()",
        selection_start=cursor + 2,
        selection_end=cursor + 2,
    )


def format_inline(
    text: str, start: int, end: int, opening: str, closing: str
) -> TextEdit:
    """Wrap a selection, or insert an empty pair at the cursor."""
    start, end = sorted((start, end))
    selected = text[start:end]
    return TextEdit(
        start=start,
        end=end,
        replacement=f"{opening}{selected}{closing}",
        selection_start=start + len(opening),
        selection_end=start + len(opening) + len(selected),
    )


def format_code(text: str, start: int, end: int) -> TextEdit:
    """Use inline code for one line and a fenced block for multiple lines."""
    start, end = sorted((start, end))
    selected = text[start:end]
    if "\n" in selected:
        return TextEdit(
            start=start,
            end=end,
            replacement=f"```\n{selected}\n```",
            selection_start=start + 4,
            selection_end=start + 4 + len(selected),
        )
    return format_inline(text, start, end, "`", "`")


def toggle_blockquote(text: str, start: int, end: int) -> TextEdit:
    """Toggle a ``> `` prefix on the lines touched by the selection."""
    start, end = sorted((start, end))
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)

    lines = text[line_start:line_end].split("\n")
    content_lines = [line for line in lines if line.strip()]
    quoted = bool(content_lines) and all(
        line.startswith("> ") for line in content_lines
    )
    if quoted:
        updated = [
            line[2:] if line.startswith("> ") else line for line in lines
        ]
    else:
        updated = ["> " + line if line.strip() else ">" for line in lines]

    replacement = "\n".join(updated)
    return TextEdit(
        start=line_start,
        end=line_end,
        replacement=replacement,
        selection_start=line_start,
        selection_end=line_start + len(replacement),
    )
