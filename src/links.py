# SPDX-License-Identifier: MIT

"""Detect Markdown links in the editor's source text.

The preview gets links straight from markdown-it tokens. Inline tokens carry
no source offsets, so the editor scans the raw source of each inline block
instead. Code spans and fenced or indented code blocks are opaque: a link-like
string there is never a link.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_ANGLE_AUTOLINK = re.compile(
    r"<([A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*)>"
)
_ANGLE_EMAIL = re.compile(
    r"<([a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*)>",
    re.IGNORECASE,
)
_BARE_URL = re.compile(r"(?i)(?:https?://|www\.)")
_BARE_EMAIL = re.compile(
    r"(?i)[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)
_TRAILING_URL_PUNCTUATION = ".,;:!?'\""
_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")


@dataclass(frozen=True)
class SourceLink:
    """A link and the source range a pointer click may target."""

    start: int
    end: int
    destination: str
    label: str = ""


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    offsets.extend(match.end() for match in re.finditer("\n", text))
    if offsets[-1] != len(text):
        offsets.append(len(text))
    return offsets


def _escaped(text: str, index: int, floor: int = 0) -> bool:
    backslashes = 0
    position = index - 1
    while position >= floor and text[position] == "\\":
        backslashes += 1
        position -= 1
    return bool(backslashes % 2)


def _range_end(index: int, ranges: list[tuple[int, int]]) -> int | None:
    for start, end in ranges:
        if start <= index < end:
            return end
    return None


def _code_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Return inline code spans, including their backtick delimiters."""
    spans: list[tuple[int, int]] = []
    index = start
    while index < end:
        if text[index] != "`" or _escaped(text, index, start):
            index += 1
            continue
        opening = index
        cursor = index
        while cursor < end and text[cursor] == "`":
            cursor += 1
        length = cursor - opening
        search = cursor
        while search < end:
            if text[search] != "`":
                search += 1
                continue
            closing = search
            while closing < end and text[closing] == "`":
                closing += 1
            if closing - search == length:
                spans.append((opening, closing))
                index = closing
                break
            search = closing
        else:
            index = cursor
    return spans


def _match_bracket(
    text: str,
    opening: int,
    end: int,
    code_spans: list[tuple[int, int]],
) -> int | None:
    depth = 0
    index = opening
    while index < end:
        skipped = _range_end(index, code_spans)
        if skipped is not None:
            index = skipped
            continue
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _match_parenthesis(text: str, opening: int, end: int) -> int | None:
    depth = 0
    index = opening
    quote = ""
    while index < end:
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if quote:
            if character == quote:
                quote = ""
            index += 1
            continue
        if character == "<" and depth == 1:
            closing = text.find(">", index + 1, end)
            if closing == -1:
                return None
            index = closing + 1
            continue
        if (
            character in "\"'"
            and index > opening + 1
            and text[index - 1].isspace()
        ):
            quote = character
            index += 1
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _unescape(value: str) -> str:
    return html.unescape(_ESCAPE.sub(r"\1", value))


def _normalize_destination(value: str) -> str:
    from markdown_it.common.normalize_url import normalizeLink

    return normalizeLink(_unescape(value))


def _destination(text: str, opening: int, closing: int) -> str:
    inner = text[opening + 1 : closing].lstrip()
    if not inner:
        return ""
    if inner.startswith("<"):
        end = inner.find(">")
        if end == -1:
            return ""
        return inner[1:end]
    value: list[str] = []
    depth = 0
    index = 0
    while index < len(inner):
        character = inner[index]
        if character == "\\" and index + 1 < len(inner):
            value.append(inner[index : index + 2])
            index += 2
            continue
        if character.isspace() and depth == 0:
            break
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                break
            depth -= 1
        value.append(character)
        index += 1
    return "".join(value)


def _normalize_label(label: str) -> str:
    from markdown_it.common.utils import normalizeReference

    return normalizeReference(label)


def _trim_bare_url(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1] in _TRAILING_URL_PUNCTUATION:
        end -= 1
    while (
        end > start
        and text[end - 1] == ")"
        and text[start:end].count("(") < text[start:end].count(")")
    ):
        end -= 1
    while (
        end > start
        and text[end - 1] == "]"
        and text[start:end].count("[") < text[start:end].count("]")
    ):
        end -= 1
    return end


def _autolink_at(text: str, index: int, end: int) -> SourceLink | None:
    if _escaped(text, index):
        return None
    match = _ANGLE_AUTOLINK.match(text, index, end)
    if match is not None:
        destination = _normalize_destination(match.group(1))
        return SourceLink(index, match.end(), destination, match.group(1))
    match = _ANGLE_EMAIL.match(text, index, end)
    if match is not None:
        address = match.group(1)
        return SourceLink(index, match.end(), f"mailto:{address}", address)
    return None


def _bare_link_at(text: str, index: int, end: int) -> SourceLink | None:
    if index > 0 and (
        text[index - 1].isalnum()
        or text[index - 1] in "@._%+-<\\["
    ):
        return None
    match = _BARE_URL.match(text, index, end)
    if match is not None:
        stop = index
        while stop < end and not text[stop].isspace() and text[stop] not in "<>":
            stop += 1
        stop = _trim_bare_url(text, index, stop)
        raw = text[index:stop]
        if raw.lower().startswith("www.") and "." not in raw[4:]:
            return None
        destination = raw if "://" in raw else f"http://{raw}"
        return SourceLink(index, stop, destination, raw)
    match = _BARE_EMAIL.match(text, index, end)
    if match is not None:
        address = match.group(0)
        return SourceLink(index, match.end(), f"mailto:{address}", address)
    return None


def _bracket_link_at(
    text: str,
    index: int,
    end: int,
    code_spans: list[tuple[int, int]],
    definitions: dict[str, str],
) -> SourceLink | None:
    if _escaped(text, index):
        return None
    if index > 0 and text[index - 1] == "!" and not _escaped(text, index - 1):
        return None
    closing = _match_bracket(text, index, end, code_spans)
    if closing is None:
        return None
    label = text[index + 1 : closing]
    if not label.strip():
        return None
    following = closing + 1
    if following < end and text[following] == "(":
        parenthesis = _match_parenthesis(text, following, end)
        if parenthesis is None:
            return None
        destination = _destination(text, following, parenthesis)
        if not destination:
            return None
        return SourceLink(
            index,
            parenthesis + 1,
            _normalize_destination(destination),
            label,
        )
    if following < end and text[following] == "[":
        reference_end = _match_bracket(
            text, following, end, code_spans
        )
        if reference_end is not None:
            reference = text[following + 1 : reference_end]
            key = _normalize_label(reference or label)
            destination = definitions.get(key)
            if destination:
                return SourceLink(
                    index, reference_end + 1, destination, label
                )
            return None
    destination = definitions.get(_normalize_label(label))
    if destination:
        return SourceLink(index, closing + 1, destination, label)
    return None


def links_in_text(text: str) -> list[SourceLink]:
    """Return every Markdown link in ``text``, in document order."""
    from .markdown_parser import create_parser

    environment: dict = {}
    try:
        tokens = create_parser().parse(text, environment)
    except Exception:  # pragma: no cover - parser is defensive already
        return []
    offsets = _line_offsets(text)
    inline_blocks: list[tuple[int, int]] = []
    for token in tokens:
        if not token.map or token.type != "inline":
            continue
        start = offsets[min(token.map[0], len(offsets) - 1)]
        end = offsets[min(token.map[1], len(offsets) - 1)]
        inline_blocks.append((start, end))

    definitions = {
        label: reference.get("href", "")
        for label, reference in environment.get("references", {}).items()
        if reference.get("href")
    }
    found: list[SourceLink] = []
    for start, end in inline_blocks:
        code_spans = _code_spans(text, start, end)
        index = start
        while index < end:
            skipped = _range_end(index, code_spans)
            if skipped is not None:
                index = skipped
                continue
            character = text[index]
            candidate = None
            if character == "<":
                candidate = _autolink_at(text, index, end)
            elif character == "[":
                candidate = _bracket_link_at(
                    text, index, end, code_spans, definitions
                )
            else:
                candidate = _bare_link_at(text, index, end)
            if candidate is None:
                index += 1
                continue
            found.append(candidate)
            index = candidate.end
    return found


def link_at_offset(text: str, offset: int) -> SourceLink | None:
    """Return the Markdown link at ``offset``, or ``None``.

    The returned range covers the link construct (including markup) so a click
    anywhere on it opens the destination. Links inside code spans or code
    blocks, escaped brackets, images, and undefined references are ignored.
    """
    if offset < 0 or offset >= len(text):
        return None
    for link in links_in_text(text):
        if link.start <= offset < link.end:
            return link
    return None
