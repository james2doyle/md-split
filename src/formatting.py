# SPDX-License-Identifier: MIT

"""Pure Markdown source formatting.

The formatter works on source lines. It uses the shared GFM parser to find
fenced code, tables, headings, list items and block quotes, then normalizes
only the ranges it recognizes. Inline content, link destinations, front matter
and code block contents are never rewritten.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .markdown_parser import create_parser

# A manual format applies directly up to this many changed lines. Larger
# changes show a confirmation dialog with a diff preview.
CONFIRM_CHANGE_LINES = 6

_FRONT_MATTER_DELIMITERS = {"---", "..."}
_ATX_RE = re.compile(r"^( {0,3})(#{1,6})(?:[ \t]+(.*))?$")
_ATX_CLOSING_RE = re.compile(r"[ \t]+#+$")
_LIST_ITEM_RE = re.compile(
    r"^([ \t]*)([-+*]|\d{1,9}[.)])(?:([ \t]+)(.*))?$"
)
_TASK_RE = re.compile(r"^\[([ xX])\][ \t]+(.+)$")
_BLOCKQUOTE_RE = re.compile(r"^([ \t]*)((?:>[ \t]*)+)(.*)$")
_FENCE_OPEN_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})(.*)$")
_TABLE_DELIMITER_RE = re.compile(r"^:?-+:?$")

_PARSER = None


def _parser():
    global _PARSER
    if _PARSER is None:
        _PARSER = create_parser()
    return _PARSER


@dataclass(frozen=True)
class ChangeSummary:
    """A short description of changes between two source strings."""

    changed_lines: int
    preview: str

    @property
    def changed(self) -> bool:
        return self.changed_lines > 0


def _split_front_matter(lines: list[str]) -> tuple[list[str], list[str]]:
    if not lines or lines[0].strip() != "---":
        return [], lines
    for index in range(1, len(lines)):
        if lines[index].strip() in _FRONT_MATTER_DELIMITERS:
            return lines[: index + 1], lines[index + 1 :]
    return [], lines


def _longest_run(text: str, character: str) -> int:
    longest = 0
    for match in re.finditer(re.escape(character) + r"+", text):
        longest = max(longest, len(match.group(0)))
    return longest


def _normalize_fence(lines: list[str], start: int, end: int) -> None:
    opening = _FENCE_OPEN_RE.match(lines[start])
    if opening is None:
        return
    character = opening.group(2)[0]
    closing_index = None
    closing_pattern = re.compile(
        rf"^[ \t]*{re.escape(character)}{{3,}}[ \t]*$"
    )
    for index in range(end - 1, start, -1):
        if closing_pattern.match(lines[index]):
            closing_index = index
            break
    if closing_index is None:
        return
    longest = max(
        (
            _longest_run(lines[index], character)
            for index in range(start + 1, closing_index)
        ),
        default=0,
    )
    length = max(3, longest + 1)
    info = opening.group(3).strip()
    indent = opening.group(1)
    lines[start] = f"{indent}{character * length}{info}"
    closing_indent = re.match(r"^[ \t]*", lines[closing_index])
    assert closing_indent is not None
    lines[closing_index] = f"{closing_indent.group(0)}{character * length}"


def _normalize_heading(line: str) -> str:
    match = _ATX_RE.match(line)
    if match is None:
        return line
    title = (match.group(3) or "").strip()
    if title and re.fullmatch(r"#+", title):
        title = ""
    elif title:
        title = _ATX_CLOSING_RE.sub("", title).rstrip()
    if title:
        return f"{match.group(1)}{match.group(2)} {title}"
    return f"{match.group(1)}{match.group(2)}"


def _normalize_task(content: str) -> str:
    match = _TASK_RE.match(content)
    if match is None:
        return content
    marker = "x" if match.group(1).lower() == "x" else " "
    rest = match.group(2).strip()
    return f"[{marker}] {rest}"


def _normalize_list_item(line: str) -> str:
    match = _LIST_ITEM_RE.match(line)
    if match is None:
        return line
    indent, marker, _spacing, content = match.groups()
    content = content or ""
    if content:
        content = _normalize_task(content)
        return f"{indent}{marker} {content}"
    return f"{indent}{marker}"


def _normalize_blockquote(line: str) -> str:
    match = _BLOCKQUOTE_RE.match(line)
    if match is None:
        return line
    indent, prefix, content = match.groups()
    depth = prefix.count(">")
    content = content.strip()
    stripped = f"{'> ' * depth}".rstrip()
    return f"{indent}{stripped} {content}" if content else f"{indent}{stripped}"


def _display_width(text: str) -> int:
    width = 0
    for character in text:
        if unicodedata.combining(character):
            continue
        if unicodedata.east_asian_width(character) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def _split_table_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    cells: list[str] = []
    buffer: list[str] = []
    index = 0
    code_run = 0
    last_separator = False
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            buffer.append(character)
            buffer.append(text[index + 1])
            index += 2
            last_separator = False
            continue
        if character == "`":
            run = 1
            while index + run < len(text) and text[index + run] == "`":
                run += 1
            if code_run == 0:
                code_run = run
            elif code_run == run:
                code_run = 0
            buffer.append("`" * run)
            index += run
            last_separator = False
            continue
        if character == "|" and code_run == 0:
            cells.append("".join(buffer).strip())
            buffer = []
            index += 1
            last_separator = True
            continue
        buffer.append(character)
        index += 1
        last_separator = False
    cells.append("".join(buffer).strip())
    if last_separator and cells and cells[-1] == "":
        cells.pop()
    return cells


def _table_alignment(cell: str) -> str:
    left = cell.startswith(":")
    right = cell.endswith(":")
    if left and right:
        return "center"
    if left:
        return "left"
    if right:
        return "right"
    return "default"


def _pad_cell(text: str, width: int, alignment: str) -> str:
    padding = max(0, width - _display_width(text))
    if alignment == "right":
        return " " * padding + text
    if alignment == "center":
        left = padding // 2
        return " " * left + text + " " * (padding - left)
    return text + " " * padding


def _separator_cell(width: int, alignment: str) -> str:
    width = max(3, width)
    if alignment == "left":
        return ":" + "-" * (width - 1)
    if alignment == "right":
        return "-" * (width - 1) + ":"
    if alignment == "center":
        return ":" + "-" * (width - 2) + ":"
    return "-" * width


def _format_table(lines: list[str], start: int, end: int) -> None:
    if end - start < 2:
        return
    rows = [_split_table_row(lines[index]) for index in range(start, end)]
    if any(not cell for cell in rows[0]):
        return
    delimiters = rows[1]
    if not delimiters or len(delimiters) != len(rows[0]):
        return
    if any(
        _TABLE_DELIMITER_RE.fullmatch(cell) is None for cell in delimiters
    ):
        return
    alignments = [_table_alignment(cell) for cell in delimiters]
    columns = max(len(row) for row in rows)
    for row in rows:
        row.extend([""] * (columns - len(row)))
    widths = [
        max(3, max(_display_width(row[index]) for row in rows))
        for index in range(columns)
    ]
    indent = re.match(r"^[ \t]*", lines[start])
    assert indent is not None
    prefix = indent.group(0)
    rendered: list[str] = []
    for row_index, row in enumerate(rows):
        if row_index == 1:
            cells = [
                _separator_cell(widths[index], alignments[index])
                for index in range(columns)
            ]
        else:
            cells = [
                _pad_cell(row[index], widths[index], alignments[index])
                for index in range(columns)
            ]
        rendered.append(f"{prefix}| {' | '.join(cells)} |")
    lines[start:end] = rendered


def _trim_line(line: str) -> str:
    stripped = line.rstrip(" \t")
    trailing = line[len(stripped) :]
    # Two spaces are a Markdown hard break; preserve them and trim the rest.
    if stripped and trailing.count(" ") >= 2:
        return stripped + "  "
    return stripped


def _format_body(text: str, *, ensure_final_newline: bool) -> str:
    text = text.rstrip("\n")
    if not text.strip():
        return ""
    lines = text.split("\n")
    tokens = _parser().parse(text)

    protected = [False] * len(lines)
    fence_tokens = []
    table_tokens = []
    heading_lines: list[int] = []
    list_item_lines: list[int] = []
    blockquote_lines: set[int] = set()
    for token in tokens:
        if token.map is None:
            continue
        start, end = token.map
        start = max(0, start)
        end = min(len(lines), end)
        if token.type in ("fence", "code_block"):
            for index in range(start, end):
                protected[index] = True
            if token.type == "fence":
                fence_tokens.append((start, end))
        elif token.type == "table_open":
            table_tokens.append((start, end))
        elif token.type == "heading_open":
            heading_lines.append(start)
        elif token.type == "list_item_open":
            list_item_lines.append(start)
        elif token.type == "blockquote_open":
            blockquote_lines.update(range(start, end))

    for start, end in fence_tokens:
        if end > start:
            _normalize_fence(lines, start, end)
    for index in heading_lines:
        if not protected[index]:
            lines[index] = _normalize_heading(lines[index])
    for index in list_item_lines:
        if not protected[index]:
            lines[index] = _normalize_list_item(lines[index])
    for index in sorted(blockquote_lines):
        if not protected[index]:
            lines[index] = _normalize_blockquote(lines[index])
    for start, end in table_tokens:
        if any(
            lines[index].lstrip().startswith(">")
            for index in range(start, end)
        ):
            continue
        if any(protected[index] for index in range(start, end)):
            continue
        _format_table(lines, start, end)

    result: list[str] = []
    previous_blank = False
    for index, line in enumerate(lines):
        if protected[index]:
            result.append(line)
            previous_blank = False
            continue
        if not line.strip():
            if not result or previous_blank:
                continue
            result.append("")
            previous_blank = True
            continue
        result.append(_trim_line(line))
        previous_blank = False
    while result and result[-1] == "":
        result.pop()
    if not result:
        return ""
    formatted = "\n".join(result)
    if ensure_final_newline:
        formatted += "\n"
    return formatted


def format_markdown(
    text: str, *, ensure_final_newline: bool = True
) -> str:
    """Return a normalized version of ``text`` without changing its meaning.

    Selections are fragments, so callers pass ``ensure_final_newline`` from the
    selection's own trailing newline instead of always adding one.
    """
    if not text:
        return ""
    lines = text.split("\n")
    front_matter, body_lines = _split_front_matter(lines)
    body = _format_body(
        "\n".join(body_lines), ensure_final_newline=ensure_final_newline
    )
    if not front_matter:
        return body
    front = "\n".join(front_matter)
    if not body:
        return front + ("\n" if ensure_final_newline else "")
    return front + "\n\n" + body


def summarize_changes(before: str, after: str, *, limit: int = 12) -> ChangeSummary:
    """Count changed lines and build a short unified-diff preview."""
    if before == after:
        return ChangeSummary(0, "")
    import difflib  # only needed when formatting, not at startup

    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = difflib.SequenceMatcher(
        None, before_lines, after_lines, autojunk=False
    )
    changed = 0
    for tag, first_start, first_end, second_start, second_end in (
        matcher.get_opcodes()
    ):
        if tag != "equal":
            changed += max(first_end - first_start, second_end - second_start)
    diff = list(
        difflib.unified_diff(
            before_lines, after_lines, n=1, lineterm="", fromfile="", tofile=""
        )
    )
    preview_lines = [
        line for line in diff if not line.startswith(("---", "+++"))
    ]
    if len(preview_lines) > limit:
        preview_lines = preview_lines[:limit] + ["…"]
    return ChangeSummary(changed, "\n".join(preview_lines))
