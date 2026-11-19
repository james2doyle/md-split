"""Headless tests for HTML and PDF export."""

import gc
import os
import stat
import struct
import sys
import tempfile
import zlib
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import cairo
import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib

from src import exporting as exporting_module
from src.exporting import render_html, write_pdf
from src.markdown_parser import create_parser
from src.paths import ensure_file_extension

assert ensure_file_extension(Path("/tmp/report"), ".pdf") == Path(
    "/tmp/report.pdf"
)
assert ensure_file_extension(Path("/tmp/report.HTML"), ".html") == Path(
    "/tmp/report.HTML"
)
assert ensure_file_extension(Path("/tmp/report.md"), ".pdf") == Path(
    "/tmp/report.md.pdf"
)

markdown_it_file = sys.modules["markdown_it"].__file__
assert markdown_it_file is not None
assert Path(markdown_it_file).resolve().is_relative_to(
    Path(SOURCE_ROOT) / "src" / "vendor"
), markdown_it_file


def make_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / "dot.png").write_bytes(make_png(8, 8))
    (root / "guide.md").write_text("# Guide", encoding="utf-8")

    html = render_html(
        "# Export title\n\n"
        "A **bold**, *italic* and <u>underlined</u> paragraph.\n\n"
        "A [relative link](guide.md) and a local image:\n\n"
        "A [query link](guide.md?plain=1#L2).\n\n"
        "![Tiny dot](dot.png)\n\n"
        "<script>alert('no')</script>\n",
        title="Export title",
        base_dir=root,
    )

    assert html.startswith("<!doctype html>"), html[:80]
    assert "<h1>Export title</h1>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<u>underlined</u>" in html
    assert "file://" in html and "guide.md" in html
    assert "guide.md?plain=1#L2" in html
    assert "data:image/png;base64," in html
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html
    assert "<style>" in html and "@media (prefers-color-scheme: dark)" in html
    assert "Adapted from new.css" in html
    assert "Copyright (c) 2020 Brendan Hersh" in html
    assert "MIT License" in html
    assert (
        "--nc-font-sans: system-ui, -apple-system, BlinkMacSystemFont, "
        '"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;'
    ) in html
    assert (
        "--nc-font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, "
        'Consolas, "Liberation Mono", "Courier New", monospace;'
    ) in html
    assert "font-family: var(--nc-font-mono)" in html
    assert "code,kbd,pre,samp" in html
    assert "Tiny dot" in html
    assert "<figure><img" in html
    assert "<figcaption>Tiny dot</figcaption></figure>" in html
    assert "@media print" not in html
    assert "@page" not in html
    assert "break-inside: avoid" not in html
    assert "nth-child(2n)" in html
    assert "color-scheme: dark;" in html
    assert "--md-accent: #1c71d8;" in html
    inline_image = render_html(
        "Text before ![Tiny dot](dot.png) after",
        title="Inline image",
        base_dir=root,
    )
    assert "<figure>" not in inline_image, inline_image
    assert "<p>Text before" in inline_image, inline_image

    unsafe = render_html(
        "[bad](javascript:alert)\n\n"
        "![remote](https://example.com/pic.png)\n\n"
        "![missing](missing.png)\n",
        title="Unsafe",
        base_dir=root,
    )
    assert 'href="javascript:' not in unsafe
    assert "javascript:" in unsafe
    assert "https://example.com/pic.png" in unsafe
    assert 'src=""' in unsafe
    assert "missing" in unsafe

    # Images outside the document directory are never embedded.
    outside = Path(tmp).parent / f"md-split-outside-{os.getpid()}.png"
    outside.write_bytes(make_png(4, 4))
    try:
        escaped = render_html(
            f"![sibling](../{outside.name})\n\n"
            f"![absolute]({outside})\n\n"
            f"![encoded](%2E%2E/{outside.name})\n",
            title="Escaped",
            base_dir=root,
        )
    finally:
        outside.unlink()
    assert "data:image/png;base64," not in escaped, escaped
    for alt in ("sibling", "absolute", "encoded"):
        assert f'alt="{alt}"' in escaped, escaped

    # Underline promotion follows the same per-inline-token nesting rules as
    # the preview, and balanced pairs in other blocks stay promoted.
    underline = render_html(
        "**<u>bold</u>**\n\n"
        "<u>**bold**</u>\n\n"
        "[<u>link](https://example.com) outside</u>\n\n"
        "<u>ok</u>\n\n"
        "<u>unclosed\n",
        title="Underline",
    )
    assert "<strong><u>bold</u></strong>" in underline, underline
    assert "<u><strong>bold</strong></u>" in underline, underline
    assert '<a href="https://example.com"><u>link</a>' not in underline
    assert "&lt;u&gt;link" in underline, underline
    assert "<p><u>ok</u></p>" in underline, underline
    assert "&lt;u&gt;unclosed" in underline, underline

    pdf = root / "export.pdf"
    pages = write_pdf(
        "# PDF title\n\n"
        "A paragraph with **bold**, *italic* and <u>underlined</u> text.\n\n"
        "- first\n"
        "- second\n\n"
        "> quoted\n\n"
        "| Name | Value |\n"
        "|------|------:|\n"
        "| Alpha | 1 |\n"
        "| Beta | 2 |\n\n"
        "```\ncode block\n```\n\n"
        "> [!NOTE]\n"
        "> An alert with a footnote.[^note]\n\n"
        "[^note]: Footnote text.\n\n"
        "![Tiny dot](dot.png)\n",
        pdf,
        title="PDF title",
        base_dir=root,
    )
    data = pdf.read_bytes()
    assert pages >= 1
    assert data.startswith(b"%PDF"), data[:8]
    assert len(data) > 500

    # A configurable base size scales every derived size and changes layout.
    default_scale = exporting_module._TypeScale()
    assert default_scale.body == exporting_module._BODY_FONT_SIZE
    assert abs(default_scale.code - 9.0) < 1e-9
    assert abs(default_scale.table - 9.5) < 1e-9
    assert abs(default_scale.caption - 9.0) < 1e-9
    assert abs(default_scale.footer - 8.0) < 1e-9
    large_scale = exporting_module._TypeScale(16.0)
    assert large_scale.body == 16.0
    assert abs(large_scale.code - 16.0 * 9 / 11) < 1e-9
    assert abs(large_scale.table - 16.0 * 9.5 / 11) < 1e-9
    assert large_scale.heading(1) == 32.0
    assert abs(large_scale.heading(3) - 16.0 * 1.27) < 1e-9

    long_text = "\n\n".join(
        f"Paragraph {index} with enough text to wrap across the page."
        for index in range(24)
    )
    small_pages = write_pdf(
        long_text,
        root / "small.pdf",
        title="Small",
        base_font_size=8.0,
    )
    large_pages = write_pdf(
        long_text,
        root / "large.pdf",
        title="Large",
        base_font_size=18.0,
    )
    assert small_pages < large_pages, (small_pages, large_pages)

    # HTML comments are literal text with HTML disabled; PDF export drops them
    # without touching code spans, code blocks or the surrounding text.
    comment_pdf = root / "comments.pdf"
    drawn: list[str] = []
    original_text = exporting_module._PdfWriter._draw_text
    original_code = exporting_module._PdfWriter._draw_code

    def record_text(self, markup, **kwargs):
        drawn.append(markup)
        return original_text(self, markup, **kwargs)

    def record_code(self, text, indent):
        drawn.append(text)
        return original_code(self, text, indent)

    exporting_module._PdfWriter._draw_text = record_text
    exporting_module._PdfWriter._draw_code = record_code
    try:
        write_pdf(
            "# Visible heading <!-- hidden heading text -->\n\n"
            "before <!-- secret comment --> after\n\n"
            "<!-- comment only -->\n\n"
            "before\n<!-- multi\nline secret -->\nafter\n\n"
            "`<!-- kept code -->`\n\n"
            "```\n<!-- kept fence -->\n```\n\n"
            "    <!-- kept indent -->\n",
            comment_pdf,
            title="Comments",
            base_dir=root,
        )
    finally:
        exporting_module._PdfWriter._draw_text = original_text
        exporting_module._PdfWriter._draw_code = original_code
    drawn_text = "\n".join(drawn)
    assert "hidden heading text" not in drawn_text, drawn_text
    assert "secret comment" not in drawn_text, drawn_text
    assert "comment only" not in drawn_text, drawn_text
    assert "line secret" not in drawn_text, drawn_text
    assert "Visible heading" in drawn_text, drawn_text
    assert "before" in drawn_text and "after" in drawn_text, drawn_text
    assert "&lt;!-- kept code --&gt;" in drawn_text, drawn_text
    assert "<!-- kept fence -->" in drawn_text, drawn_text
    assert "<!-- kept indent -->" in drawn_text, drawn_text
    assert comment_pdf.read_bytes().startswith(b"%PDF")

    # Tables become a real grid: full content width, header fill and
    # borders, per-column alignment, and a repeated header on later pages.
    probe_surface = exporting_module.cairo.PDFSurface(
        str(root / "probe.pdf"),
        exporting_module._PAGE_WIDTH,
        exporting_module._PAGE_HEIGHT,
    )
    probe = exporting_module._PdfWriter(
        probe_surface, base_dir=root, base_file=None, title="Probe"
    )
    probe_tokens = probe.parser.parse(
        "| Name | Value |\n| :--- | ---: |\n| Alpha | 1 |\n"
    )
    probe_rows = probe._table_rows(probe_tokens, 0, len(probe_tokens))
    assert probe_rows[0].header and not probe_rows[1].header
    assert (
        probe_rows[1].cells[1].align
        == exporting_module.Pango.Alignment.RIGHT
    )
    probe_widths = probe._table_column_widths(
        probe_rows, 2, probe.content_width
    )
    assert abs(sum(probe_widths) - probe.content_width) < 0.01
    probe_surface.finish()

    grids = []
    original_grid = exporting_module._PdfWriter._draw_table_grid

    def record_grid(self, x, top, widths, height):
        grids.append((x, top, list(widths), height))
        return original_grid(self, x, top, widths, height)

    exporting_module._PdfWriter._draw_table_grid = record_grid
    try:
        grid_pdf = root / "grid.pdf"
        write_pdf(
            "| Name | Value |\n"
            "|------|------:|\n"
            "| Alpha | 1 |\n"
            "| Beta | 2 |\n",
            grid_pdf,
            title="Grid",
        )
    finally:
        exporting_module._PdfWriter._draw_table_grid = original_grid
    assert grids
    for x, _top, grid_widths, height in grids:
        assert height > 0
        assert abs(sum(grid_widths) - probe.content_width) < 0.01
        assert abs(x - exporting_module._PAGE_MARGIN) < 0.01

    long_rows = "\n".join(
        f"| Row {index} | {'text ' * 8} |" for index in range(80)
    )
    long_table = (
        "| Name | Value |\n|------|------|\n" + long_rows + "\n"
    )
    header_pages = []
    original_row = exporting_module._PdfWriter._draw_table_row

    def record_row(self, cells, widths, x, **kwargs):
        if kwargs.get("header"):
            header_pages.append(self.page)
        return original_row(self, cells, widths, x, **kwargs)

    exporting_module._PdfWriter._draw_table_row = record_row
    try:
        table_pdf = root / "table.pdf"
        table_pages = write_pdf(
            long_table, table_pdf, title="Long table"
        )
    finally:
        exporting_module._PdfWriter._draw_table_row = original_row
    assert table_pages > 1, table_pages
    assert len(set(header_pages)) > 1, header_pages

    # A single cell taller than a page is split instead of overflowing.
    huge_row = " ".join(f"word{index}" for index in range(1200))
    huge_pdf = root / "huge-table.pdf"
    huge_pages = write_pdf(
        f"| Name | Value |\n|------|------|\n| {huge_row} | 1 |\n",
        huge_pdf,
        title="Huge row",
    )
    assert huge_pages > 1, huge_pages

    long_pdf = root / "long.pdf"
    long_pages = write_pdf(
        "\n\n".join(f"Paragraph {index} " + "text " * 40 for index in range(80)),
        long_pdf,
        title="Long document",
    )
    assert long_pages > 1, long_pages
    assert long_pdf.read_bytes().startswith(b"%PDF")
    assert not (root / ".long.pdf.tmp").exists()
    assert not list(root.glob(".long.pdf.*.tmp"))

    # A blockquote that crosses a page break keeps its bar on every page.
    bars = []
    original_bar = exporting_module._PdfWriter._draw_bar

    def record_bar(self, indent, start_y, end_y, color=None):
        bars.append((self.page, start_y, end_y))
        if color is None:
            return original_bar(self, indent, start_y, end_y)
        return original_bar(self, indent, start_y, end_y, color)

    exporting_module._PdfWriter._draw_bar = record_bar
    try:
        quote_pdf = root / "quote.pdf"
        quote_pages = write_pdf(
            "\n".join(
                "> " + "quoted text " * 12 + "\n>" for _ in range(120)
            ),
            quote_pdf,
            title="Quote",
        )
    finally:
        exporting_module._PdfWriter._draw_bar = original_bar
    assert quote_pages > 1, quote_pages
    segments = [
        (page, start_y, end_y)
        for page, start_y, end_y in bars
        if end_y > start_y
    ]
    assert len(segments) >= 2, bars
    assert len({page for page, _start, _end in segments}) >= 2, segments

    # A planted .<name>.tmp symlink is never followed or overwritten.
    victim = root / "victim.txt"
    victim.write_text("keep me", encoding="utf-8")
    planted = root / ".planted.pdf.tmp"
    planted.symlink_to(victim)
    planted_pdf = root / "planted.pdf"
    write_pdf("# Planted", planted_pdf, title="Planted")
    assert victim.read_text(encoding="utf-8") == "keep me"
    assert planted_pdf.read_bytes().startswith(b"%PDF")
    assert planted.is_symlink() and planted.resolve() == victim

    # The exported file keeps the permissions a normal file creation gets.
    umask = os.umask(0)
    os.umask(umask)
    assert stat.S_IMODE(pdf.stat().st_mode) == 0o666 & ~umask

    # A failed write removes its temporary file and leaves no target.
    from src import exporting

    original_blocks = exporting._PdfWriter.blocks

    def fail_blocks(self, *_args, **_kwargs):
        raise RuntimeError("boom")

    exporting._PdfWriter.blocks = fail_blocks
    failed = root / "failed.pdf"
    try:
        try:
            write_pdf("content", failed, title="Failed")
        except RuntimeError:
            pass
        else:
            raise AssertionError("write_pdf should have failed")
    finally:
        exporting._PdfWriter.blocks = original_blocks
    assert not (root / ".failed.pdf.tmp").exists()
    assert not list(root.glob(".failed.pdf.*.tmp"))
    assert not failed.exists()

    # Pango layout lines are only valid while their layout stays alive. Table
    # rows keep lines for later page breaks, so the layout must be retained.
    surface = cairo.PDFSurface(
        str(root / "cell-layout.pdf"), 595.276, 841.89
    )
    writer = exporting_module._PdfWriter(
        surface, base_dir=None, base_file=None, title="Layout"
    )
    tokens = create_parser().parse(
        "| Code | Value |\n| :--- | ---: |\n| `x` | 1 |\n"
    )
    table_start = next(
        index
        for index, token in enumerate(tokens)
        if token.type == "table_open"
    )
    table_close = next(
        index
        for index, token in enumerate(tokens)
        if token.type == "table_close"
    )
    rows = writer._table_rows(tokens, table_start, table_close)
    widths = writer._table_column_widths(
        rows, len(rows[0].cells), writer.content_width
    )
    cells = writer._table_row_layouts(rows[1], widths)
    gc.collect()
    messages = []

    def capture(_domain, _level, message):
        messages.append(message)

    handler = GLib.log_set_handler(
        "Pango",
        GLib.LogLevelFlags.LEVEL_WARNING
        | GLib.LogLevelFlags.LEVEL_CRITICAL,
        capture,
    )
    try:
        for cell in cells:
            for line, _height, _width, _top in cell.lines:
                line.get_pixel_extents()
    finally:
        GLib.log_remove_handler("Pango", handler)
    assert not messages, messages
    surface.finish()

print("ok: HTML and PDF export")
