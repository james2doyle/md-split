# SPDX-License-Identifier: MIT

"""Pure text-editing helpers for the Markdown editor.

The helpers return a :class:`TextEdit` describing a replacement instead of
touching a GtkTextBuffer directly. That keeps the behavior testable without a
display and lets the window apply an edit as one undoable user action.
"""

from __future__ import annotations

import re
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
class SearchQuery:
    """Options for an in-document text search."""

    text: str
    match_case: bool = False
    whole_word: bool = False
    regex: bool = False


def compile_search(query: SearchQuery) -> re.Pattern[str] | None:
    """Compile a query, returning ``None`` for empty or invalid patterns."""
    if not query.text:
        return None
    pattern = query.text if query.regex else re.escape(query.text)
    if query.whole_word:
        pattern = rf"\b(?:{pattern})\b"
    flags = 0 if query.match_case else re.IGNORECASE
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


def count_matches(text: str, query: SearchQuery) -> int:
    pattern = compile_search(query)
    if pattern is None:
        return 0
    return sum(1 for _match in pattern.finditer(text))


def replace_all_text(
    text: str, query: SearchQuery, replacement: str
) -> tuple[str, int]:
    """Replace all matches and return the new text and match count."""
    pattern = compile_search(query)
    if pattern is None:
        return text, 0
    return pattern.subn(replacement, text)


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
    end = min(end, len(text))
    # A selection that ends exactly on a line break belongs to the line before
    # it (the triple-click gesture); do not quote the following line.
    if start < end and text[end - 1] == "\n":
        end -= 1
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


_BULLET_ITEM = re.compile(r"^([ \t]*)([-+*])([ \t]+)(.*)$")
_TASK_MARKER = re.compile(r"^(\[[ xX]\][ \t]+)(.*)$")
_ORDERED_ITEM = re.compile(r"^([ \t]*)(\d+)([.)])([ \t]+)(.*)$")


def _line_ending(text: str, line_end: int) -> str:
    """Return the line ending that terminates (or precedes) a line."""
    if line_end < len(text) and text[line_end] == "\n":
        return "\r\n" if line_end > 0 and text[line_end - 1] == "\r" else "\n"
    previous = text.rfind("\n", 0, line_end)
    if previous > 0 and text[previous - 1] == "\r":
        return "\r\n"
    return "\n"


def continue_list(text: str, cursor: int) -> TextEdit | None:
    """Continue a list item, or exit an empty item, when Return is pressed."""
    if cursor < 0 or cursor > len(text):
        return None

    line_start = text.rfind("\n", 0, cursor) + 1
    newline = text.find("\n", cursor)
    line_end = len(text) if newline == -1 else newline
    eol = _line_ending(text, line_end)
    content_end = line_end
    if content_end > line_start and text[content_end - 1] == "\r":
        content_end -= 1
    line = text[line_start:content_end]
    relative = min(cursor - line_start, len(line))
    insert_at = line_start + relative

    bullet = _BULLET_ITEM.match(line)
    ordered = _ORDERED_ITEM.match(line)
    if bullet is not None:
        indent, marker, _spaces, rest = bullet.groups()
        marker_end = len(indent) + len(marker) + len(_spaces)
        task = _TASK_MARKER.match(rest)
        if task is not None:
            task_marker, content = task.groups()
            marker_end += len(task_marker)
            next_marker = f"{indent}{marker} [ ] "
        else:
            content = rest
            next_marker = f"{indent}{marker} "
    elif ordered is not None:
        indent, number, delimiter, _spaces, content = ordered.groups()
        marker_end = (
            len(indent) + len(number) + len(delimiter) + len(_spaces)
        )
        try:
            number = int(number) + 1
        except ValueError:
            return None
        next_marker = f"{indent}{number}{delimiter} "
    else:
        return None

    if relative < marker_end:
        return None

    if not content.strip():
        end = newline + 1 if newline != -1 else line_end
        return TextEdit(
            start=line_start,
            end=end,
            replacement=eol,
            selection_start=line_start + len(eol),
            selection_end=line_start + len(eol),
        )

    replacement = eol + next_marker
    return TextEdit(
        start=insert_at,
        end=insert_at,
        replacement=replacement,
        selection_start=insert_at + len(replacement),
        selection_end=insert_at + len(replacement),
    )
