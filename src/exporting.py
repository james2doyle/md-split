# SPDX-License-Identifier: MIT

"""Standalone HTML and styled PDF export."""

from __future__ import annotations

import base64
import html
import io
import math
import mimetypes
import os
import re
import tempfile
from dataclasses import dataclass
from gettext import gettext as _
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

import gi

gi.require_version("GLib", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")

from gi.repository import Gio, GLib, Pango, PangoCairo

try:
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
except (ImportError, ValueError):
    GdkPixbuf = None

import cairo

from .markdown_parser import create_parser, has_valid_underline_inline
from .paths import contained_file, document_root
from .renderer import MarkdownRenderer

if TYPE_CHECKING:
    from markdown_it.token import Token

_MAX_EMBED_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_EMBED_TOTAL_BYTES = 32 * 1024 * 1024
_MAX_PDF_IMAGE_PIXELS = 20_000_000
_ANCHOR_TAG = re.compile(r"</?a\b[^>]*>")

# One source of truth for the exported light theme. The HTML stylesheet is
# generated from these values and the PDF writer reads the same palette and
# type scale, so the two outputs cannot drift apart.
_TEXT_HEX = "#1b1b1f"
_MUTED_HEX = "#5e5c64"
_BORDER_HEX = "#d8d8dc"
_SURFACE_HEX = "#f4f5f6"
_ZEBRA_HEX = "#fafafb"
_ACCENT_HEX = "#1c71d8"
_CODE_BG_HEX = "#eceff1"
_QUOTE_BAR_HEX = "#c0bfbc"
_SUCCESS_HEX = "#2ec27e"
_WARNING_HEX = "#e5a50a"
_ERROR_HEX = "#c01c28"
_ACCENT_TINT_HEX = "#eef4fc"
_SUCCESS_TINT_HEX = "#eaf7f1"
_WARNING_TINT_HEX = "#fdf5e6"
_ERROR_TINT_HEX = "#fdeced"
_BODY_FONT_SIZE = 11.0
# Secondary sizes scale with the configurable body size instead of standing
# alone, so a larger export stays proportional.
_CODE_FONT_SCALE = 9.0 / 11.0
_TABLE_FONT_SCALE = 9.5 / 11.0
_CAPTION_FONT_SCALE = 9.0 / 11.0
_FOOTER_FONT_SCALE = 8.0 / 11.0
_HEADING_SCALES = {1: 2.0, 2: 1.55, 3: 1.27, 4: 1.09, 5: 1.0, 6: 1.0}

_PAGE_WIDTH = 595.276
_PAGE_HEIGHT = 841.89
_PAGE_MARGIN = 48
_TABLE_PAD_X = 7.0
_TABLE_PAD_Y = 5.0
_TABLE_MIN_COLUMN = 42.0
_TABLE_MARGIN_TOP = 8.0
_TABLE_MARGIN_BOTTOM = 8.0
_TABLE_LINE_WIDTH = 0.6
_CODE_PAD_X = 10.0
_CODE_PAD_Y = 7.0
_CODE_RADIUS = 6.0
_CODE_MARGIN_TOP = 6.0
_CODE_MARGIN_BOTTOM = 8.0


@dataclass(frozen=True)
class _TypeScale:
    """Export font sizes derived from one configurable body size."""

    body: float = _BODY_FONT_SIZE

    @property
    def code(self) -> float:
        return self.body * _CODE_FONT_SCALE

    @property
    def table(self) -> float:
        return self.body * _TABLE_FONT_SCALE

    @property
    def caption(self) -> float:
        return self.body * _CAPTION_FONT_SCALE

    @property
    def footer(self) -> float:
        return self.body * _FOOTER_FONT_SCALE

    def heading(self, level: int) -> float:
        return self.body * _HEADING_SCALES.get(level, 1.0)


def _css_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


_EXPORT_CSS = Path(__file__).with_name("export.css").read_text(encoding="utf-8")


def _rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


_TEXT_COLOR = _rgb(_TEXT_HEX)
_MUTED_COLOR = _rgb(_MUTED_HEX)
_BORDER_COLOR = _rgb(_BORDER_HEX)
_SURFACE_COLOR = _rgb(_SURFACE_HEX)
_ZEBRA_COLOR = _rgb(_ZEBRA_HEX)
_ACCENT_COLOR = _rgb(_ACCENT_HEX)
_SUCCESS_COLOR = _rgb(_SUCCESS_HEX)
_WARNING_COLOR = _rgb(_WARNING_HEX)
_ERROR_COLOR = _rgb(_ERROR_HEX)
_QUOTE_BAR_COLOR = _rgb(_QUOTE_BAR_HEX)


def _parsed(value: str):
    try:
        return urlparse(value.strip())
    except ValueError:
        return None


def _local_path(
    value: str, base_dir: Path | None, base_file: Gio.File | None
) -> Path | None:
    parsed = _parsed(value)
    if parsed is None or parsed.scheme or value.startswith("//"):
        return None
    root = document_root(base_dir, base_file)
    if root is None:
        return None
    path = Path(unquote(parsed.path))
    if not path.is_absolute():
        path = root / path
    return contained_file(path, root)


def _resolve_link(
    value: str, base_dir: Path | None, base_file: Gio.File | None
) -> str | None:
    parsed = _parsed(value)
    if parsed is None:
        return None
    scheme = parsed.scheme.lower()
    if scheme in {"javascript", "vbscript", "data"}:
        return None
    if scheme or value.startswith("#"):
        return value
    if value.startswith("//"):
        return None

    suffix = ""
    if parsed.query:
        suffix += f"?{parsed.query}"
    if parsed.fragment:
        suffix += f"#{parsed.fragment}"

    if base_dir is not None:
        return (base_dir / unquote(parsed.path)).resolve().as_uri() + suffix
    if base_file is not None:
        parent = base_file.get_parent()
        if parent is None:
            return value
        target = parent.resolve_relative_path(unquote(parsed.path))
        return (target.get_uri() or value) + suffix
    return value


def _image_source(
    value: str,
    base_dir: Path | None,
    base_file: Gio.File | None,
    budget: list[int] | None = None,
) -> str | None:
    parsed = _parsed(value)
    if parsed is None:
        return None
    scheme = parsed.scheme.lower()
    if scheme in {"javascript", "vbscript"}:
        return None
    if scheme in {"http", "https"}:
        return value
    if scheme or value.startswith("//"):
        return None

    path = _local_path(value, base_dir, base_file)
    if path is None or not path.is_file():
        return None
    mime, _encoding = mimetypes.guess_type(path.name)
    if mime is None or not mime.startswith("image/"):
        return None
    try:
        if path.stat().st_size > _MAX_EMBED_IMAGE_BYTES:
            return path.as_uri()
        data = path.read_bytes()
    except OSError:
        return None
    if budget is not None:
        if len(data) > budget[0]:
            return path.as_uri()
        budget[0] -= len(data)
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _underline_inlines(tokens: list[Token], link_allowed) -> None:
    """Mark text tokens whose inline block can promote <u> tags."""
    for token in tokens:
        if token.type == "inline" and has_valid_underline_inline(
            token, link_allowed=link_allowed
        ):
            for child in token.children or []:
                if child.type == "text":
                    child.meta["underline"] = True


def _text_rule(tokens, idx, options, _env):
    content = html.escape(tokens[idx].content, quote=True)
    if tokens[idx].meta.get("underline"):
        content = content.replace("&lt;u&gt;", "<u>").replace(
            "&lt;/u&gt;", "</u>"
        )
    return content


_HTML_COMMENT_OPEN = "<!--"
_HTML_COMMENT_CLOSE = "-->"


def _comment_ranges(children: list[Token]) -> list[tuple[int, int]]:
    """Return character ranges covered by complete inline HTML comments."""
    stream = "".join(
        child.content for child in children if child.type == "text"
    )
    ranges: list[tuple[int, int]] = []
    index = 0
    while True:
        start = stream.find(_HTML_COMMENT_OPEN, index)
        if start < 0:
            break
        close = stream.find(_HTML_COMMENT_CLOSE, start + 4)
        if close < 0:
            # An unclosed opener stays literal, like the preview shows it.
            break
        end = close + len(_HTML_COMMENT_CLOSE)
        ranges.append((start, end))
        index = end
    return ranges


def _strip_inline_comments(children: list[Token]) -> list[Token]:
    """Copy inline children with complete HTML comments removed.

    HTML is disabled in the parser, so comments arrive as text tokens. Markup
    inside a comment is dropped with it; code spans outside comments are left
    untouched.
    """
    ranges = _comment_ranges(children)
    if not ranges:
        return children
    kept: list[Token] = []
    offset = 0
    for child in children:
        if child.type == "text":
            start = offset
            end = start + len(child.content)
            offset = end
            pieces: list[str] = []
            cursor = start
            for comment_start, comment_end in ranges:
                if comment_end <= cursor or comment_start >= end:
                    continue
                if comment_start > cursor:
                    pieces.append(
                        child.content[cursor - start : comment_start - start]
                    )
                cursor = max(cursor, comment_end)
            if cursor < end:
                pieces.append(child.content[cursor - start :])
            text = "".join(pieces)
            if text:
                copy = child.copy()
                copy.content = text
                kept.append(copy)
        elif not any(
            comment_start < offset < comment_end
            for comment_start, comment_end in ranges
        ):
            kept.append(child)
    return kept


def _sole_image_inline(tokens: list[Token], index: int) -> Token | None:
    """Return the image token when a paragraph contains only that image."""
    if index < 0 or index + 1 >= len(tokens):
        return None
    if tokens[index].type != "paragraph_open":
        return None
    inline = tokens[index + 1]
    if inline.type != "inline":
        return None
    children = [
        child
        for child in inline.children or []
        if not (child.type == "text" and not child.content.strip())
    ]
    if len(children) == 1 and children[0].type == "image":
        return children[0]
    if (
        len(children) == 3
        and children[0].type == "link_open"
        and children[1].type == "image"
        and children[2].type == "link_close"
    ):
        return children[1]
    return None


def render_html(
    text: str,
    *,
    title: str,
    base_dir: Path | None = None,
    base_file: Gio.File | None = None,
    base_font_size: float = _BODY_FONT_SIZE,
) -> str:
    """Render a complete, standalone HTML document."""
    parser = create_parser()
    default_image = parser.renderer.rules["image"]
    embed_budget = [_MAX_EMBED_TOTAL_BYTES]

    def image_rule(tokens, idx, options, env):
        token = tokens[idx]
        token.attrSet(
            "src",
            _image_source(
                token.attrGet("src") or "",
                base_dir,
                base_file,
                embed_budget,
            )
            or "",
        )
        return default_image(tokens, idx, options, env)

    def link_rule(tokens, idx, options, env):
        token = tokens[idx]
        resolved = _resolve_link(
            token.attrGet("href") or "", base_dir, base_file
        )
        token.attrSet("href", resolved or "")
        return parser.renderer.renderToken(tokens, idx, options, env)

    def paragraph_open_rule(tokens, idx, options, env):
        if tokens[idx].hidden:
            return parser.renderer.renderToken(tokens, idx, options, env)
        if _sole_image_inline(tokens, idx) is not None:
            return "<figure>"
        return parser.renderer.renderToken(tokens, idx, options, env)

    def paragraph_close_rule(tokens, idx, options, env):
        if tokens[idx].hidden or tokens[idx - 2].hidden:
            return parser.renderer.renderToken(tokens, idx, options, env)
        image = _sole_image_inline(tokens, idx - 2)
        if image is None:
            return parser.renderer.renderToken(tokens, idx, options, env)
        alt = image.content or image.attrGet("alt") or ""
        caption = (
            f"<figcaption>{html.escape(alt, quote=False)}</figcaption>"
            if alt.strip()
            else ""
        )
        return f"{caption}</figure>"

    parser.renderer.rules["image"] = image_rule
    parser.renderer.rules["link_open"] = link_rule
    parser.renderer.rules["text"] = _text_rule
    parser.renderer.rules["paragraph_open"] = paragraph_open_rule
    parser.renderer.rules["paragraph_close"] = paragraph_close_rule

    tokens = parser.parse(text)

    def link_allowed(href: str) -> bool:
        return _resolve_link(href, base_dir, base_file) is not None

    _underline_inlines(tokens, link_allowed)
    body = parser.renderer.render(tokens, parser.options, {})

    escaped_title = html.escape(title, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escaped_title}</title>
<style>
{_export_css(base_font_size)}
</style>
</head>
<body>
<main class="md-document">
{body}
</main>
</body>
</html>
"""


def _export_css(base_font_size: float = _BODY_FONT_SIZE) -> str:
    variables = [
        ("text", _TEXT_HEX),
        ("muted", _MUTED_HEX),
        ("border", _BORDER_HEX),
        ("surface", _SURFACE_HEX),
        ("zebra", _ZEBRA_HEX),
        ("accent", _ACCENT_HEX),
        ("code-bg", _CODE_BG_HEX),
        ("quote-bar", _QUOTE_BAR_HEX),
        ("success", _SUCCESS_HEX),
        ("warning", _WARNING_HEX),
        ("error", _ERROR_HEX),
        ("accent-tint", _ACCENT_TINT_HEX),
        ("success-tint", _SUCCESS_TINT_HEX),
        ("warning-tint", _WARNING_TINT_HEX),
        ("error-tint", _ERROR_TINT_HEX),
        *(
            (f"h{level}", f"{_css_number(scale)}em")
            for level, scale in _HEADING_SCALES.items()
        ),
        ("print-size", f"{_css_number(base_font_size)}pt"),
    ]
    declarations = "\n".join(
        f"  --md-{name}: {value};" for name, value in variables
    )
    return (
        ":root {\n"
        "  color-scheme: light;\n"
        f"{declarations}\n"
        "}\n\n"
        f"{_EXPORT_CSS}"
    )


def _find_close(
    tokens: list[Token], start: int, open_type: str, close_type: str
) -> int:
    depth = 0
    for index in range(start, len(tokens)):
        if tokens[index].type == open_type:
            depth += 1
        elif tokens[index].type == close_type:
            depth -= 1
            if depth == 0:
                return index
    return len(tokens) - 1


def _cell_alignment(style: str) -> Pango.Alignment:
    if "center" in style:
        return Pango.Alignment.CENTER
    if "right" in style:
        return Pango.Alignment.RIGHT
    return Pango.Alignment.LEFT


@dataclass
class _TableCell:
    markup: str
    align: Pango.Alignment


@dataclass
class _TableRow:
    cells: list[_TableCell]
    header: bool


@dataclass
class _CellLines:
    cell: _TableCell
    width: float
    lines: list[tuple[Any, int, int, int]]
    # Pango layout lines are owned by their layout and become invalid when it
    # is finalized. Table rows retain lines across page breaks, so keep the
    # layout alive alongside them.
    layout: Any


class _PdfWriter:
    def __init__(
        self,
        surface: cairo.PDFSurface,
        *,
        base_dir: Path | None,
        base_file: Gio.File | None,
        title: str = "",
        base_font_size: float = _BODY_FONT_SIZE,
    ) -> None:
        self.surface = surface
        self.cr = cairo.Context(surface)
        self.base_dir = base_dir
        self.base_file = base_file
        self.title = title
        self.type = _TypeScale(base_font_size)
        self.parser = create_parser()
        self.renderer = MarkdownRenderer()
        self.page = 0
        self.started = False
        self.y = _PAGE_MARGIN
        self.content_width = _PAGE_WIDTH - 2 * _PAGE_MARGIN
        self._bars: list[dict[str, Any]] = []
        self._muted_depth = 0

    # -- page management -------------------------------------------------

    def start(self) -> None:
        self._new_page()

    def finish(self) -> None:
        self._draw_footer()

    def _new_page(self) -> None:
        if self.started:
            self._finish_page_bars()
            self._draw_footer()
            self.cr.show_page()
        self.started = True
        self.page += 1
        self.y = _PAGE_MARGIN
        for bar in self._bars:
            bar["start_y"] = self.y
        self._set_color(_TEXT_COLOR)

    def _draw_footer(self) -> None:
        baseline = _PAGE_HEIGHT - 34
        self.cr.save()
        self._set_color(_BORDER_COLOR)
        self.cr.set_line_width(0.5)
        self.cr.move_to(_PAGE_MARGIN, baseline - 10)
        self.cr.line_to(_PAGE_WIDTH - _PAGE_MARGIN, baseline - 10)
        self.cr.stroke()
        self._set_color(_MUTED_COLOR)
        if self.title:
            layout = self._layout(
                GLib.markup_escape_text(self.title),
                self.content_width - 40,
                size=self.type.footer,
            )
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            self.cr.move_to(_PAGE_MARGIN, baseline)
            PangoCairo.show_layout(self.cr, layout)
        layout = self._layout(
            str(self.page), self.content_width, size=self.type.footer
        )
        width, _height = layout.get_pixel_size()
        self.cr.move_to(_PAGE_WIDTH - _PAGE_MARGIN - width, baseline)
        PangoCairo.show_layout(self.cr, layout)
        self.cr.restore()

    def _set_color(self, color) -> None:
        self.cr.set_source_rgb(*color)

    def _ensure_space(self, height: float) -> None:
        if self.y + height > _PAGE_HEIGHT - _PAGE_MARGIN:
            self._new_page()

    def _draw_heading_rule(self, indent: float) -> None:
        self.y += 3
        self.cr.save()
        self._set_color(_BORDER_COLOR)
        self.cr.set_line_width(0.7)
        self.cr.move_to(_PAGE_MARGIN + indent, self.y)
        self.cr.line_to(_PAGE_WIDTH - _PAGE_MARGIN, self.y)
        self.cr.stroke()
        self.cr.restore()
        self.y += 3

    # -- text layout -----------------------------------------------------

    def _layout(
        self,
        markup: str,
        width: float,
        *,
        size: float | None = None,
        monospace: bool = False,
        bold: bool = False,
        align: Pango.Alignment = Pango.Alignment.LEFT,
    ):
        layout = PangoCairo.create_layout(self.cr)
        description = Pango.FontDescription()
        description.set_family("Monospace" if monospace else "Sans")
        description.set_size(int((size or self.type.body) * Pango.SCALE))
        if bold:
            description.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(description)
        layout.set_width(max(1, int(width * Pango.SCALE)))
        layout.set_alignment(align)
        layout.set_wrap(
            Pango.WrapMode.CHAR if monospace else Pango.WrapMode.WORD_CHAR
        )
        layout.set_markup(markup, -1)
        return layout

    def _draw_layout(
        self,
        layout,
        *,
        indent: float = 0,
        spacing_before: float = 0,
        spacing_after: float = 0,
        color: tuple[float, float, float] = _TEXT_COLOR,
    ) -> None:
        self.y += spacing_before
        _width, height = layout.get_pixel_size()
        available = _PAGE_HEIGHT - _PAGE_MARGIN - self.y
        lines = layout.get_lines()
        if height <= available or len(lines) <= 1:
            self._ensure_space(height)
            self._draw_layout_whole(layout, indent, color)
            self.y += spacing_after
            return

        for line in lines:
            logical = line.get_pixel_extents()[1]
            line_height = max(1, logical.height)
            if self.y + line_height > _PAGE_HEIGHT - _PAGE_MARGIN:
                self._new_page()
            self.cr.save()
            self._set_color(color)
            self.cr.move_to(
                _PAGE_MARGIN + indent, self.y - logical.y
            )
            PangoCairo.show_layout_line(self.cr, line)
            self.cr.restore()
            self.y += line_height
        self.y += spacing_after

    def _draw_layout_whole(
        self,
        layout,
        indent: float,
        color: tuple[float, float, float],
    ) -> None:
        _width, height = layout.get_pixel_size()
        self.cr.save()
        self._set_color(color)
        self.cr.move_to(_PAGE_MARGIN + indent, self.y)
        PangoCairo.show_layout(self.cr, layout)
        self.cr.restore()
        self.y += height

    def _draw_text(
        self,
        markup: str,
        *,
        indent: float = 0,
        size: float | None = None,
        monospace: bool = False,
        bold: bool = False,
        spacing_before: float = 0,
        spacing_after: float = 6,
        align: Pango.Alignment = Pango.Alignment.LEFT,
    ) -> None:
        layout = self._layout(
            markup,
            self.content_width - indent,
            size=size,
            monospace=monospace,
            bold=bold,
            align=align,
        )
        self._draw_layout(
            layout,
            indent=indent,
            spacing_before=spacing_before,
            spacing_after=spacing_after,
            color=_MUTED_COLOR if self._muted_depth else _TEXT_COLOR,
        )

    # -- blocks ----------------------------------------------------------

    def blocks(
        self,
        tokens: list[Token],
        start: int,
        end: int,
        *,
        indent: float = 0,
        first_prefix: str | None = None,
    ) -> int:
        index = start
        while index < end:
            token = tokens[index]
            kind = token.type

            if kind == "heading_open":
                inline = tokens[index + 1] if index + 1 < end else None
                if inline is not None and inline.type == "inline":
                    level = 1
                    if len(token.tag) == 2 and token.tag[0] == "h":
                        level = int(token.tag[1])
                    heading_size = self.type.heading(level)
                    markup = self._inline(inline)
                    if markup.strip():
                        self._ensure_space(heading_size * 1.6 + 24)
                        self._draw_text(
                            markup,
                            indent=indent,
                            size=heading_size,
                            bold=True,
                            spacing_before=14 if level <= 2 else 8,
                            spacing_after=2 if level <= 2 else 5,
                        )
                        if level <= 2:
                            self._draw_heading_rule(indent)
                index += 3
            elif kind == "paragraph_open":
                inline = tokens[index + 1] if index + 1 < end else None
                if inline is not None and inline.type == "inline":
                    image = self._sole_image(inline)
                    if image is not None:
                        self._draw_image(image, indent)
                    else:
                        prefix = first_prefix or ""
                        content = self._inline(inline)
                        if content.strip():
                            markup = (
                                GLib.markup_escape_text(prefix) + content
                            )
                            self._draw_text(markup, indent=indent)
                    first_prefix = None
                index += 3
            elif kind in ("bullet_list_open", "ordered_list_open"):
                index = self._list(tokens, index, indent)
                first_prefix = None
            elif kind == "blockquote_open":
                close = _find_close(
                    tokens, index, "blockquote_open", "blockquote_close"
                )
                self._start_bar(indent + 3)
                self._muted_depth += 1
                try:
                    self.blocks(
                        tokens, index + 1, close, indent=indent + 14
                    )
                finally:
                    self._muted_depth -= 1
                self._end_bar()
                index = close + 1
                first_prefix = None
            elif kind == "alert_open":
                close = _find_close(
                    tokens, index, "alert_open", "alert_close"
                )
                alert_kind = (
                    (token.meta or {}).get("kind") or token.info or "NOTE"
                ).upper()
                self._draw_text(
                    GLib.markup_escape_text(alert_kind.title()),
                    indent=indent,
                    size=10,
                    bold=True,
                    spacing_before=8,
                    spacing_after=3,
                )
                content_start = index + 1
                if (
                    index + 2 < close
                    and tokens[index + 1].type == "alert_title_open"
                ):
                    content_start = index + 4
                bar_color = {
                    "TIP": _SUCCESS_COLOR,
                    "WARNING": _WARNING_COLOR,
                    "CAUTION": _ERROR_COLOR,
                }.get(alert_kind, _ACCENT_COLOR)
                self._start_bar(indent + 3, bar_color)
                self.blocks(
                    tokens, content_start, close, indent=indent + 10
                )
                self._end_bar()
                index = close + 1
                first_prefix = None
            elif kind in ("fence", "code_block"):
                self._draw_code(token.content, indent)
                index += 1
                first_prefix = None
            elif kind == "hr":
                self._ensure_space(12)
                self.cr.save()
                self._set_color(_BORDER_COLOR)
                self.cr.set_line_width(0.8)
                self.cr.move_to(_PAGE_MARGIN + indent, self.y + 4)
                self.cr.line_to(
                    _PAGE_WIDTH - _PAGE_MARGIN, self.y + 4
                )
                self.cr.stroke()
                self.cr.restore()
                self.y += 14
                index += 1
                first_prefix = None
            elif kind == "table_open":
                index = self._table(tokens, index, indent)
                first_prefix = None
            elif kind == "footnote_block_open":
                index = self._footnotes(tokens, index, indent)
                first_prefix = None
            else:
                index += 1
        return index

    def _list(
        self, tokens: list[Token], start: int, indent: float
    ) -> int:
        opening = tokens[start]
        ordered = opening.type == "ordered_list_open"
        close = _find_close(
            tokens,
            start,
            opening.type,
            "ordered_list_close" if ordered else "bullet_list_close",
        )
        number = 1
        if ordered:
            try:
                number = int(opening.attrs.get("start", 1))
            except (TypeError, ValueError):
                number = 1

        index = start + 1
        while index < close:
            if tokens[index].type != "list_item_open":
                index += 1
                continue
            item_close = _find_close(
                tokens, index, "list_item_open", "list_item_close"
            )
            checked = (tokens[index].meta or {}).get("checked")
            if checked is True:
                marker = "\u2611 "
            elif checked is False:
                marker = "\u2610 "
            elif ordered:
                marker = f"{number}. "
                number += 1
            else:
                marker = "\u2022 "
            self.blocks(
                tokens,
                index + 1,
                item_close,
                indent=indent + 16,
                first_prefix=marker,
            )
            self.y += 2
            index = item_close + 1
        self.y += 4
        return close + 1

    def _table_rows(
        self, tokens: list[Token], start: int, close: int
    ) -> list[_TableRow]:
        rows: list[_TableRow] = []
        current: list[_TableCell] | None = None
        header = False
        index = start + 1
        while index < close:
            kind = tokens[index].type
            if kind == "tr_open":
                current = []
                header = False
            elif kind in ("th_open", "td_open"):
                inline = tokens[index + 1] if index + 1 < close else None
                if inline is not None and inline.type != "inline":
                    inline = None
                markup = (
                    self._inline(inline, plain_code=True)
                    if inline is not None
                    else ""
                )
                if kind == "th_open":
                    header = True
                    if markup.strip():
                        markup = f"<b>{markup}</b>"
                if current is None:
                    current = []
                align = _cell_alignment(
                    tokens[index].attrs.get("style", "")
                )
                current.append(_TableCell(markup, align))
            elif kind == "tr_close":
                if current is not None:
                    rows.append(_TableRow(current, header))
                current = None
            index += 1
        return rows

    def _natural_width(self, markup: str, size: float) -> int:
        layout = self._layout(markup or " ", self.content_width, size=size)
        layout.set_width(-1)
        width, _height = layout.get_pixel_size()
        return width

    def _table_column_widths(
        self, rows: list[_TableRow], columns: int, available: float
    ) -> list[float]:
        natural = [0.0] * columns
        for row in rows:
            for index, cell in enumerate(row.cells[:columns]):
                natural[index] = max(
                    natural[index],
                    float(
                        self._natural_width(cell.markup, self.type.table)
                        + 2 * _TABLE_PAD_X
                    ),
                )
        if columns <= 0:
            return []
        if _TABLE_MIN_COLUMN * columns >= available:
            return [available / columns] * columns
        widths = [max(_TABLE_MIN_COLUMN, value) for value in natural]
        total = sum(widths)
        if total < available:
            extra = available - total
            weights = [value if value > 0 else 1.0 for value in natural]
            weight_total = sum(weights) or float(columns)
            widths = [
                width + extra * weight / weight_total
                for width, weight in zip(widths, weights)
            ]
        elif total > available:
            # Keep narrow columns at their natural width and cap only the
            # wide ones, instead of shrinking every column proportionally.
            low = _TABLE_MIN_COLUMN
            high = max(widths)
            for _attempt in range(40):
                cap = (low + high) / 2
                if sum(min(width, cap) for width in widths) > available:
                    high = cap
                else:
                    low = cap
            widths = [min(width, low) for width in widths]
        total = sum(widths)
        if total <= 0:
            return [available / columns] * columns
        widths = [width * available / total for width in widths]
        widths[-1] += available - sum(widths)
        return widths

    def _table_row_layouts(
        self, row: _TableRow, widths: list[float]
    ) -> list[_CellLines]:
        result: list[_CellLines] = []
        for cell, width in zip(row.cells, widths):
            layout = self._layout(
                cell.markup or " ",
                max(1.0, width - 2 * _TABLE_PAD_X),
                size=self.type.table,
            )
            lines = []
            for line in layout.get_lines():
                logical = line.get_pixel_extents()[1]
                lines.append(
                    (
                        line,
                        max(1, logical.height),
                        logical.width,
                        -logical.y,
                    )
                )
            result.append(_CellLines(cell, width, lines, layout))
        return result

    def _table_slice_height(
        self, cells: list[_CellLines], start: int = 0, end: int | None = None
    ) -> float:
        heights = [
            sum(
                height
                for _line, height, _width, _top in cell.lines[start:end]
            )
            for cell in cells
        ]
        return max(heights, default=0) + 2 * _TABLE_PAD_Y

    def _table_row_height(self, cells: list[_CellLines]) -> float:
        return self._table_slice_height(cells)

    def _draw_table_grid(
        self,
        x: float,
        top: float,
        widths: list[float],
        height: float,
    ) -> None:
        right = x + sum(widths)
        self.cr.save()
        self._set_color(_BORDER_COLOR)
        self.cr.set_line_width(_TABLE_LINE_WIDTH)
        self.cr.move_to(x, top)
        self.cr.line_to(right, top)
        self.cr.move_to(x, top + height)
        self.cr.line_to(right, top + height)
        edge = x
        for width in widths:
            self.cr.move_to(edge, top)
            self.cr.line_to(edge, top + height)
            edge += width
        self.cr.move_to(edge, top)
        self.cr.line_to(edge, top + height)
        self.cr.stroke()
        self.cr.restore()

    def _draw_table_row(
        self,
        cells: list[_CellLines],
        widths: list[float],
        x: float,
        *,
        header: bool,
        zebra: bool,
        start: int = 0,
        end: int | None = None,
    ) -> None:
        height = self._table_slice_height(cells, start, end)
        top = self.y
        fill = _SURFACE_COLOR if header else (_ZEBRA_COLOR if zebra else None)
        if fill is not None:
            self.cr.save()
            self.cr.set_source_rgb(*fill)
            self.cr.rectangle(x, top, sum(widths), height)
            self.cr.fill()
            self.cr.restore()
        cell_x = x
        for cell in cells:
            content_width = max(1.0, cell.width - 2 * _TABLE_PAD_X)
            self.cr.save()
            self.cr.rectangle(cell_x, top, cell.width, height)
            self.cr.clip()
            self._set_color(
                _MUTED_COLOR if self._muted_depth else _TEXT_COLOR
            )
            line_y = top + _TABLE_PAD_Y
            for line, line_height, line_width, line_top in cell.lines[
                start:end
            ]:
                if cell.cell.align == Pango.Alignment.CENTER:
                    offset = max(0.0, (content_width - line_width) / 2)
                elif cell.cell.align == Pango.Alignment.RIGHT:
                    offset = max(0.0, content_width - line_width)
                else:
                    offset = 0.0
                self.cr.move_to(
                    cell_x + _TABLE_PAD_X + offset, line_y + line_top
                )
                PangoCairo.show_layout_line(self.cr, line)
                line_y += line_height
            self.cr.restore()
            cell_x += cell.width
        self._draw_table_grid(x, top, widths, height)
        self.y += height

    def _table(
        self, tokens: list[Token], start: int, indent: float
    ) -> int:
        close = _find_close(tokens, start, "table_open", "table_close")
        rows = self._table_rows(tokens, start, close)
        if not rows:
            return close + 1
        columns = max((len(row.cells) for row in rows), default=0)
        if columns == 0:
            return close + 1
        for row in rows:
            while len(row.cells) < columns:
                row.cells.append(_TableCell("", Pango.Alignment.LEFT))
        widths = self._table_column_widths(
            rows, columns, self.content_width - indent
        )
        x = _PAGE_MARGIN + indent
        bottom = _PAGE_HEIGHT - _PAGE_MARGIN
        self.y += _TABLE_MARGIN_TOP

        header_cells = None
        header_height = 0.0
        if rows[0].header:
            header_cells = self._table_row_layouts(rows[0], widths)
            header_height = self._table_row_height(header_cells)
            if self.y + header_height > bottom:
                self._new_page()

        for row_index, row in enumerate(rows):
            cells = self._table_row_layouts(row, widths)
            row_height = self._table_row_height(cells)
            is_header = row.header
            zebra = not is_header and row_index % 2 == 0
            if (
                self.y + row_height > bottom
                and self.y > _PAGE_MARGIN + 0.5
                and row_height <= bottom - _PAGE_MARGIN
            ):
                self._new_page()
                if header_cells is not None and not is_header:
                    self._draw_table_row(
                        header_cells, widths, x, header=True, zebra=False
                    )

            start_line = 0
            total_lines = max(
                (len(cell.lines) for cell in cells), default=1
            )
            while True:
                remaining = bottom - self.y
                if (
                    start_line == 0
                    and self._table_slice_height(cells) <= remaining
                ):
                    self._draw_table_row(
                        cells,
                        widths,
                        x,
                        header=is_header,
                        zebra=zebra,
                    )
                    break
                fit = 0
                for count in range(1, total_lines - start_line + 1):
                    if (
                        self._table_slice_height(
                            cells, start_line, start_line + count
                        )
                        <= remaining
                    ):
                        fit = count
                    else:
                        break
                if fit == 0:
                    minimum_y = _PAGE_MARGIN + 0.5
                    if header_cells is not None and not is_header:
                        minimum_y += header_height
                    if self.y > minimum_y:
                        self._new_page()
                        if header_cells is not None and not is_header:
                            self._draw_table_row(
                                header_cells,
                                widths,
                                x,
                                header=True,
                                zebra=False,
                            )
                        continue
                    fit = 1
                end_line = start_line + fit
                self._draw_table_row(
                    cells,
                    widths,
                    x,
                    header=is_header,
                    zebra=zebra,
                    start=start_line,
                    end=end_line,
                )
                start_line = end_line
                if start_line >= total_lines:
                    break
                self._new_page()
                if header_cells is not None and not is_header:
                    self._draw_table_row(
                        header_cells, widths, x, header=True, zebra=False
                    )

        self.y += _TABLE_MARGIN_BOTTOM
        return close + 1

    def _footnotes(
        self, tokens: list[Token], start: int, indent: float
    ) -> int:
        close = _find_close(
            tokens, start, "footnote_block_open", "footnote_block_close"
        )
        self._draw_text(
            _("Footnotes"),
            indent=indent,
            size=self.type.heading(3),
            bold=True,
            spacing_before=10,
            spacing_after=4,
        )
        index = start + 1
        while index < close:
            if tokens[index].type != "footnote_open":
                index += 1
                continue
            footnote_close = _find_close(
                tokens, index, "footnote_open", "footnote_close"
            )
            meta = tokens[index].meta or {}
            label = meta.get("label", str(meta.get("id", 0) + 1))
            self.blocks(
                tokens,
                index + 1,
                footnote_close,
                indent=indent + 12,
                first_prefix=f"[{label}] ",
            )
            index = footnote_close + 1
        return close + 1

    def _rounded_rect(
        self, x: float, y: float, width: float, height: float, radius: float
    ) -> None:
        radius = min(radius, width / 2, height / 2)
        cr = self.cr
        cr.new_sub_path()
        cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
        cr.arc(
            x + width - radius,
            y + height - radius,
            radius,
            0,
            math.pi / 2,
        )
        cr.arc(
            x + radius,
            y + height - radius,
            radius,
            math.pi / 2,
            math.pi,
        )
        cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _draw_rounded_box(
        self, x: float, y: float, width: float, height: float
    ) -> None:
        self.cr.save()
        self._rounded_rect(x, y, width, height, _CODE_RADIUS)
        self.cr.set_source_rgb(*_SURFACE_COLOR)
        self.cr.fill_preserve()
        self._set_color(_BORDER_COLOR)
        self.cr.set_line_width(0.8)
        self.cr.stroke()
        self.cr.restore()

    def _draw_code(self, text: str, indent: float) -> None:
        layouts: list[tuple[Any, float]] = []
        available = self.content_width - indent - 2 * _CODE_PAD_X
        for line in text.rstrip("\n").split("\n"):
            markup = GLib.markup_escape_text(line) or " "
            layout = self._layout(
                markup,
                available,
                size=self.type.code,
                monospace=True,
            )
            _width, height = layout.get_pixel_size()
            layouts.append((layout, max(height, 12.0)))

        self.y += _CODE_MARGIN_TOP
        index = 0
        while index < len(layouts):
            group: list[tuple[Any, float]] = []
            total = 0.0
            while index < len(layouts):
                layout, height = layouts[index]
                if (
                    group
                    and self.y + total + height + 2 * _CODE_PAD_Y
                    > _PAGE_HEIGHT - _PAGE_MARGIN
                ):
                    break
                group.append((layout, height))
                total += height
                index += 1
            box_height = total + 2 * _CODE_PAD_Y
            box_x = _PAGE_MARGIN + indent
            box_width = self.content_width - indent
            if (
                self.y + box_height > _PAGE_HEIGHT - _PAGE_MARGIN
                and self.y > _PAGE_MARGIN + 0.5
            ):
                self._new_page()
            self._draw_rounded_box(box_x, self.y, box_width, box_height)
            line_y = self.y + _CODE_PAD_Y
            for layout, height in group:
                self.cr.save()
                self.cr.rectangle(
                    box_x + _CODE_PAD_X,
                    self.y,
                    max(1.0, box_width - 2 * _CODE_PAD_X),
                    box_height,
                )
                self.cr.clip()
                self._set_color(
                    _MUTED_COLOR if self._muted_depth else _TEXT_COLOR
                )
                self.cr.move_to(box_x + _CODE_PAD_X, line_y)
                PangoCairo.show_layout(self.cr, layout)
                self.cr.restore()
                line_y += height
            self.y += box_height + _CODE_MARGIN_BOTTOM
            if index < len(layouts):
                self._new_page()
                self.y += _CODE_MARGIN_TOP

    def _draw_image(self, token: Token, indent: float) -> None:
        source = token.attrGet("src") or ""
        alt = token.content or token.attrGet("alt") or ""
        path = _local_path(source, self.base_dir, self.base_file)
        if GdkPixbuf is None or path is None or not path.is_file():
            label = f"{_('Image')}: {alt}" if alt else _("Image")
            self._draw_text(
                GLib.markup_escape_text(f"[{label}]"),
                indent=indent,
                spacing_before=4,
                spacing_after=6,
            )
            return

        try:
            info = GdkPixbuf.Pixbuf.get_file_info(str(path))
            width, height = info[1], info[2]
            if not width or not height or width * height > _MAX_PDF_IMAGE_PIXELS:
                raise ValueError("image is too large")
            scale = min(
                1.0,
                (self.content_width - indent) / width,
                320 / height,
            )
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                str(path),
                max(1, int(width * scale)),
                max(1, int(height * scale)),
                True,
            )
            _success, data = pixbuf.save_to_bufferv("png", [], [])
            surface = cairo.ImageSurface.create_from_png(io.BytesIO(data))
        except (GLib.Error, ValueError, OSError):
            label = f"{_('Image')}: {alt}" if alt else _("Image")
            self._draw_text(
                GLib.markup_escape_text(f"[{label}]"),
                indent=indent,
                spacing_before=4,
                spacing_after=6,
            )
            return

        image_width = surface.get_width()
        image_height = surface.get_height()
        caption_space = 24 if alt.strip() else 10
        self._ensure_space(image_height + caption_space)
        available = self.content_width - indent
        offset = max(0.0, (available - image_width) / 2)
        self.cr.save()
        self.cr.translate(_PAGE_MARGIN + indent + offset, self.y)
        self.cr.set_source_surface(surface, 0, 0)
        self.cr.paint()
        self.cr.restore()
        self.y += image_height + 8
        if alt.strip():
            self._draw_text(
                GLib.markup_escape_text(alt),
                indent=indent,
                size=self.type.caption,
                spacing_before=0,
                spacing_after=8,
                align=Pango.Alignment.CENTER,
            )

    def _start_bar(
        self,
        indent: float,
        color: tuple[float, float, float] = _QUOTE_BAR_COLOR,
    ) -> None:
        self._bars.append(
            {"indent": indent, "start_y": self.y, "color": color}
        )

    def _end_bar(self) -> None:
        bar = self._bars.pop()
        self._draw_bar(
            bar["indent"], bar["start_y"], self.y, bar["color"]
        )

    def _finish_page_bars(self) -> None:
        bottom = _PAGE_HEIGHT - _PAGE_MARGIN
        for bar in self._bars:
            self._draw_bar(
                bar["indent"], bar["start_y"], bottom, bar["color"]
            )

    def _draw_bar(
        self,
        indent: float,
        start_y: float,
        end_y: float,
        color: tuple[float, float, float] = _QUOTE_BAR_COLOR,
    ) -> None:
        if end_y <= start_y:
            return
        self.cr.save()
        self._set_color(color)
        self.cr.rectangle(
            _PAGE_MARGIN + indent, start_y, 2, end_y - start_y
        )
        self.cr.fill()
        self.cr.restore()

    def _inline(self, token: Token, *, plain_code: bool = False) -> str:
        children = _strip_inline_comments(token.children or [])
        if not children:
            return ""
        if children is not token.children:
            token = token.copy()
            token.children = children
        return _ANCHOR_TAG.sub(
            "",
            self.renderer.inline_token_markup(
                token,
                code_background=_CODE_BG_HEX,
                plain_code=plain_code,
            ),
        )

    def _sole_image(self, token: Token) -> Token | None:
        children = token.children or []
        if len(children) == 1 and children[0].type == "image":
            return children[0]
        return None


def _new_file_mode() -> int:
    """Return the mode a regular file created in this process would get."""
    current = os.umask(0)
    os.umask(current)
    return 0o666 & ~current


def write_pdf(
    text: str,
    path: str | Path,
    *,
    title: str,
    base_dir: Path | None = None,
    base_file: Gio.File | None = None,
    base_font_size: float = _BODY_FONT_SIZE,
) -> int:
    """Write a styled PDF and return the number of pages."""
    target = Path(path)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        surface = cairo.PDFSurface(
            str(temporary), _PAGE_WIDTH, _PAGE_HEIGHT
        )
        surface.set_metadata(cairo.PDF_METADATA_TITLE, title)
        surface.set_metadata(cairo.PDF_METADATA_CREATOR, "MD Split")
        surface.set_metadata(cairo.PDF_METADATA_SUBJECT, title)
        writer = _PdfWriter(
            surface,
            base_dir=base_dir,
            base_file=base_file,
            title=title,
            base_font_size=base_font_size,
        )
        tokens = writer.parser.parse(text)
        writer.start()
        writer.blocks(tokens, 0, len(tokens))
        writer.finish()
        surface.finish()
        # mkstemp creates 0600; give the exported file normal permissions.
        os.chmod(temporary, _new_file_mode())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return writer.page
