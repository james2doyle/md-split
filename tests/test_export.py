"""Headless tests for HTML and PDF export."""

import os
import stat
import struct
import sys
import tempfile
import zlib
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src import exporting as exporting_module
from src.exporting import render_html, write_pdf
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
    assert "<style>" in html and "@media print" in html
    assert "Tiny dot" in html

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

    long_pdf = root / "long.pdf"
    long_pages = write_pdf(
        "\n\n".join(f"Paragraph {index} " + "text " * 40 for index in range(80)),
        long_pdf,
        title="Long document",
    )
    assert long_pages > 1, long_pages
    assert long_pdf.read_bytes().startswith(b"%PDF")
    assert not (root / ".long.pdf.tmp").exists()

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

print("ok: HTML and PDF export")
