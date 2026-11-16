# SPDX-License-Identifier: MIT

"""Standalone HTML and styled PDF export."""

from __future__ import annotations

import base64
import html
import io
import mimetypes
import re
from gettext import gettext as _
from pathlib import Path
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
from markdown_it.token import Token

from .markdown_parser import create_parser, has_valid_underline_markup
from .renderer import MarkdownRenderer

_MAX_EMBED_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_EMBED_TOTAL_BYTES = 32 * 1024 * 1024
_MAX_PDF_IMAGE_PIXELS = 20_000_000
_ANCHOR_TAG = re.compile(r"</?a\b[^>]*>")
_PAGE_WIDTH = 595.276
_PAGE_HEIGHT = 841.89
_PAGE_MARGIN = 48
_TEXT_COLOR = (0.10, 0.10, 0.11)
_MUTED_COLOR = (0.42, 0.42, 0.44)


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
    path = Path(unquote(parsed.path))
    if path.is_absolute():
        return path
    if base_dir is not None:
        return (base_dir / path).resolve()
    if base_file is not None:
        parent = base_file.get_parent()
        if parent is None:
            return None
        local = parent.get_path()
        if local:
            return (Path(local) / path).resolve()
    return None


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


def _underline_chunks(tokens: list[Token]):
    for token in tokens:
        if token.type == "text":
            yield token.content
        for child in token.children or []:
            yield from _underline_chunks([child])


def _text_rule(tokens, idx, options, env):
    content = html.escape(tokens[idx].content, quote=True)
    if env.get("underline"):
        content = content.replace("&lt;u&gt;", "<u>").replace(
            "&lt;/u&gt;", "</u>"
        )
    return content


def render_html(
    text: str,
    *,
    title: str,
    base_dir: Path | None = None,
    base_file: Gio.File | None = None,
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

    parser.renderer.rules["image"] = image_rule
    parser.renderer.rules["link_open"] = link_rule
    parser.renderer.rules["text"] = _text_rule

    tokens = parser.parse(text)
    underline = has_valid_underline_markup(
        "".join(_underline_chunks(tokens))
    )
    body = parser.renderer.render(tokens, parser.options, {"underline": underline})

    escaped_title = html.escape(title, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escaped_title}</title>
<style>
{_EXPORT_CSS}
</style>
</head>
<body>
<main class="md-document">
{body}
</main>
</body>
</html>
"""


_EXPORT_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0;
  color: #1b1b1f;
  background: #ffffff;
  font-family: Cantarell, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.55;
}
.md-document {
  max-width: 860px;
  margin: 0 auto;
  padding: 40px 28px 64px;
}
h1, h2, h3, h4, h5, h6 { line-height: 1.25; margin: 1.2em 0 0.45em; }
h1, h2 { border-bottom: 1px solid #d8d8dc; padding-bottom: 0.25em; }
h1 { font-size: 2em; }
h2 { font-size: 1.55em; }
h3 { font-size: 1.3em; }
p, ul, ol, blockquote, pre, table { margin: 0.7em 0; }
a { color: #1c71d8; }
code {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  background: #eceff1;
  border-radius: 4px;
  padding: 0.1em 0.3em;
  font-size: 0.9em;
}
pre {
  background: #f4f5f6;
  border: 1px solid #d8d8dc;
  border-radius: 8px;
  padding: 14px 16px;
  overflow-x: auto;
}
pre code { background: transparent; padding: 0; }
blockquote {
  border-left: 3px solid #c0bfbc;
  color: #5e5c64;
  padding: 0.1em 0 0.1em 14px;
}
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #d8d8dc; padding: 7px 10px; text-align: left; }
th { background: #f4f5f6; }
img { max-width: 100%; height: auto; }
hr { border: none; border-top: 1px solid #d8d8dc; margin: 1.5em 0; }
@media print {
  body { background: #ffffff; }
  .md-document { max-width: none; padding: 0; }
  a { color: inherit; text-decoration: underline; }
  pre, blockquote, table, img { break-inside: avoid; }
}
"""


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


class _PdfWriter:
    def __init__(
        self,
        surface: cairo.PDFSurface,
        *,
        base_dir: Path | None,
        base_file: Gio.File | None,
    ) -> None:
        self.surface = surface
        self.cr = cairo.Context(surface)
        self.base_dir = base_dir
        self.base_file = base_file
        self.parser = create_parser()
        self.renderer = MarkdownRenderer()
        self.page = 0
        self.started = False
        self.y = _PAGE_MARGIN
        self.content_width = _PAGE_WIDTH - 2 * _PAGE_MARGIN

    # -- page management -------------------------------------------------

    def start(self) -> None:
        self._new_page()

    def finish(self) -> None:
        self._draw_footer()

    def _new_page(self) -> None:
        if self.started:
            self._draw_footer()
            self.cr.show_page()
        self.started = True
        self.page += 1
        self.y = _PAGE_MARGIN
        self._set_color(_TEXT_COLOR)

    def _draw_footer(self) -> None:
        layout = PangoCairo.create_layout(self.cr)
        layout.set_font_description(Pango.FontDescription("Sans 8"))
        layout.set_text(str(self.page), -1)
        width, _height = layout.get_pixel_size()
        self.cr.save()
        self._set_color(_MUTED_COLOR)
        self.cr.move_to((_PAGE_WIDTH - width) / 2, _PAGE_HEIGHT - 30)
        PangoCairo.show_layout(self.cr, layout)
        self.cr.restore()

    def _set_color(self, color) -> None:
        self.cr.set_source_rgb(*color)

    def _ensure_space(self, height: float) -> None:
        if self.y + height > _PAGE_HEIGHT - _PAGE_MARGIN:
            self._new_page()

    # -- text layout -----------------------------------------------------

    def _layout(
        self,
        markup: str,
        width: float,
        *,
        size: float = 11,
        monospace: bool = False,
        bold: bool = False,
    ):
        layout = PangoCairo.create_layout(self.cr)
        description = Pango.FontDescription()
        description.set_family("Monospace" if monospace else "Sans")
        description.set_size(int(size * Pango.SCALE))
        if bold:
            description.set_weight(Pango.Weight.BOLD)
        layout.set_font_description(description)
        layout.set_width(max(1, int(width * Pango.SCALE)))
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
        background: bool = False,
    ) -> None:
        self.y += spacing_before
        _width, height = layout.get_pixel_size()
        available = _PAGE_HEIGHT - _PAGE_MARGIN - self.y
        lines = layout.get_lines()
        if height <= available or len(lines) <= 1:
            self._ensure_space(height)
            self._draw_layout_whole(layout, indent, background)
            self.y += spacing_after
            return

        for line in lines:
            logical = line.get_pixel_extents()[1]
            line_height = max(1, logical.height)
            if self.y + line_height > _PAGE_HEIGHT - _PAGE_MARGIN:
                self._new_page()
            if background:
                self._draw_background(indent, line_height + 2)
            self.cr.save()
            self.cr.move_to(_PAGE_MARGIN + indent, self.y)
            PangoCairo.show_layout_line(self.cr, line)
            self.cr.restore()
            self.y += line_height
        self.y += spacing_after

    def _draw_layout_whole(self, layout, indent: float, background: bool) -> None:
        _width, height = layout.get_pixel_size()
        if background:
            self._draw_background(indent, height + 4)
        self.cr.save()
        self.cr.move_to(_PAGE_MARGIN + indent, self.y)
        PangoCairo.show_layout(self.cr, layout)
        self.cr.restore()
        self.y += height

    def _draw_background(self, indent: float, height: float) -> None:
        self.cr.save()
        self.cr.set_source_rgb(0.94, 0.945, 0.95)
        self.cr.rectangle(
            _PAGE_MARGIN + indent - 6,
            self.y - 2,
            self.content_width - indent + 12,
            height,
        )
        self.cr.fill()
        self.cr.restore()

    def _draw_text(
        self,
        markup: str,
        *,
        indent: float = 0,
        size: float = 11,
        monospace: bool = False,
        bold: bool = False,
        spacing_before: float = 0,
        spacing_after: float = 6,
        background: bool = False,
    ) -> None:
        layout = self._layout(
            markup,
            self.content_width - indent,
            size=size,
            monospace=monospace,
            bold=bold,
        )
        self._draw_layout(
            layout,
            indent=indent,
            spacing_before=spacing_before,
            spacing_after=spacing_after,
            background=background,
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
                    sizes = {1: 22, 2: 17, 3: 14, 4: 12, 5: 11, 6: 11}
                    self._draw_text(
                        self._inline(inline),
                        indent=indent,
                        size=sizes.get(level, 11),
                        bold=True,
                        spacing_before=12 if level <= 2 else 7,
                        spacing_after=5,
                    )
                index += 3
            elif kind == "paragraph_open":
                inline = tokens[index + 1] if index + 1 < end else None
                if inline is not None and inline.type == "inline":
                    image = self._sole_image(inline)
                    if image is not None:
                        self._draw_image(image, indent)
                    else:
                        prefix = first_prefix or ""
                        markup = GLib.markup_escape_text(prefix) + self._inline(
                            inline
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
                start_y = self.y
                self.blocks(tokens, index + 1, close, indent=indent + 14)
                self._draw_bar(indent + 3, start_y, self.y)
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
                start_y = self.y
                self.blocks(
                    tokens, content_start, close, indent=indent + 10
                )
                self._draw_bar(indent + 3, start_y, self.y)
                index = close + 1
                first_prefix = None
            elif kind in ("fence", "code_block"):
                self._draw_code(token.content, indent)
                index += 1
                first_prefix = None
            elif kind == "hr":
                self._ensure_space(12)
                self.cr.save()
                self.cr.set_source_rgb(0.75, 0.75, 0.78)
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

    def _table(
        self, tokens: list[Token], start: int, indent: float
    ) -> int:
        close = _find_close(tokens, start, "table_open", "table_close")
        rows: list[list[str]] = []
        current: list[str] | None = None
        header = False
        index = start + 1
        while index < close:
            kind = tokens[index].type
            if kind == "tr_open":
                current = []
                header = False
            elif kind in ("th_open", "td_open"):
                inline = tokens[index + 1] if index + 1 < close else None
                if inline is not None and inline.type == "inline":
                    markup = self._inline(inline)
                    if kind == "th_open":
                        markup = f"<b>{markup}</b>"
                        header = True
                    current = current if current is not None else []
                    current.append(markup)
                index += 1
            elif kind == "tr_close":
                if current:
                    rows.append(current)
                current = None
            index += 1

        for row in rows:
            markup = "   |   ".join(row)
            self._draw_text(
                markup,
                indent=indent,
                size=9.5,
                spacing_before=2,
                spacing_after=2,
            )
            if header:
                self._ensure_space(6)
                self.cr.save()
                self.cr.set_source_rgb(0.75, 0.75, 0.78)
                self.cr.set_line_width(0.6)
                self.cr.move_to(_PAGE_MARGIN + indent, self.y)
                self.cr.line_to(_PAGE_WIDTH - _PAGE_MARGIN, self.y)
                self.cr.stroke()
                self.cr.restore()
                header = False
        self.y += 6
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
            size=13,
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

    def _draw_code(self, text: str, indent: float) -> None:
        self.y += 6
        for line in text.rstrip("\n").split("\n"):
            markup = GLib.markup_escape_text(line) or " "
            layout = self._layout(
                markup,
                self.content_width - indent - 16,
                size=9,
                monospace=True,
            )
            _width, height = layout.get_pixel_size()
            height = max(height, 12)
            if self.y + height + 4 > _PAGE_HEIGHT - _PAGE_MARGIN:
                self._new_page()
            self.cr.save()
            self.cr.set_source_rgb(0.94, 0.945, 0.95)
            self.cr.rectangle(
                _PAGE_MARGIN + indent,
                self.y - 2,
                self.content_width - indent,
                height + 4,
            )
            self.cr.fill()
            self.cr.restore()
            self.cr.save()
            self.cr.move_to(_PAGE_MARGIN + indent + 8, self.y)
            PangoCairo.show_layout(self.cr, layout)
            self.cr.restore()
            self.y += height + 2
        self.y += 8

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
        self._ensure_space(image_height + 10)
        self.cr.save()
        self.cr.translate(_PAGE_MARGIN + indent, self.y)
        self.cr.set_source_surface(surface, 0, 0)
        self.cr.paint()
        self.cr.restore()
        self.y += image_height + 8

    def _draw_bar(self, indent: float, start_y: float, end_y: float) -> None:
        if end_y <= start_y:
            return
        self.cr.save()
        self.cr.set_source_rgb(0.72, 0.72, 0.75)
        self.cr.rectangle(
            _PAGE_MARGIN + indent, start_y, 2, end_y - start_y
        )
        self.cr.fill()
        self.cr.restore()

    def _inline(self, token: Token) -> str:
        return _ANCHOR_TAG.sub(
            "", self.renderer.inline_token_markup(token)
        )

    def _sole_image(self, token: Token) -> Token | None:
        children = token.children or []
        if len(children) == 1 and children[0].type == "image":
            return children[0]
        return None


def write_pdf(
    text: str,
    path: str | Path,
    *,
    title: str,
    base_dir: Path | None = None,
    base_file: Gio.File | None = None,
) -> int:
    """Write a styled PDF and return the number of pages."""
    target = Path(path)
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        surface = cairo.PDFSurface(
            str(temporary), _PAGE_WIDTH, _PAGE_HEIGHT
        )
        surface.set_metadata(cairo.PDF_METADATA_TITLE, title)
        writer = _PdfWriter(surface, base_dir=base_dir, base_file=base_file)
        tokens = writer.parser.parse(text)
        writer.start()
        writer.blocks(tokens, 0, len(tokens))
        writer.finish()
        surface.finish()
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return writer.page
