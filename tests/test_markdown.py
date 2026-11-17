"""Headless tests for Markdown parsing and Pango markup generation."""

import os
import sys
import time
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src.renderer import MarkdownRenderer

renderer = MarkdownRenderer()

markup = renderer.inline_markup(
    "A **bold**, *italic*, ~~strike~~ and `code` paragraph."
)
assert "<b>bold</b>" in markup
assert "<i>italic</i>" in markup
assert "<s>strike</s>" in markup
assert 'font_family="monospace"' in markup
assert ">code</span>" in markup

markup = renderer.inline_markup(
    "Bare https://gnome.org and www.example.org and me@example.com."
)
assert '<a href="https://gnome.org">https://gnome.org</a>' in markup
assert '<a href="http://www.example.org">www.example.org</a>' in markup
assert '<a href="mailto:me@example.com">me@example.com</a>' in markup

markup = renderer.inline_markup(
    "[link](https://example.com) and [bad](javascript:alert(1))"
)
assert '<a href="https://example.com">link</a>' in markup
assert '<a href="javascript:' not in markup

markup = renderer.inline_markup("![alt text](image.png)")
assert "[alt text]" in markup
assert "<img" not in markup

markup = renderer.inline_markup("A <u>native underline</u>.")
assert "<u>native underline</u>" in markup
markup = renderer.inline_markup("An <u>unclosed tag")
assert "&lt;u&gt;unclosed tag" in markup
markup = renderer.inline_markup("`<u>code</u>`")
assert "&lt;u&gt;code&lt;/u&gt;" in markup

# Duplicate heading anchors follow GitHub's -1, -2 numbering.
renderer._heading_slugs = {}
assert [renderer._unique_slug("Foo") for _ in range(3)] == [
    "foo",
    "foo-1",
    "foo-2",
]

# Underline tags are promoted only when they nest with the surrounding markup.
markup = renderer.inline_markup("**<u>bold</u>**")
assert "<b><u>bold</u></b>" in markup, markup
markup = renderer.inline_markup("<u>**bold**</u>")
assert "<u><b>bold</b></u>" in markup, markup

# A pair that crosses emphasis or link boundaries is not promoted.
crossed = "[<u>link](https://example.com) outside</u>"
markup = renderer.inline_markup(crossed)
assert '<a href="https://example.com">' in markup, markup
assert "&lt;u&gt;link" in markup, markup
assert "<u>" not in markup, markup
markup = renderer.inline_markup("**<u>bold**</u>")
assert "<b>&lt;u&gt;bold</b>&lt;/u&gt;" in markup, markup

dark_markup = renderer.inline_markup("`code`", dark=True)
assert 'background="#3d3f42"' in dark_markup

# Pathological autolink inputs must stay fast enough for the UI thread. The
# generous ceiling still catches the former multi-second quadratic behavior.
adversarial = {
    "colon-heavy": ":" * 16_000,
    "protocol-heavy": "a:" * 8_000,
    "email-heavy": "a@" * 8_000,
    "unmatched-parens": "http://a" + ")" * 64_000,
    "entities": "&" * 256_000,
}
for label, source in adversarial.items():
    started = time.perf_counter()
    renderer.inline_markup(source)
    elapsed = time.perf_counter() - started
    assert elapsed < 1.5, f"{label} took {elapsed:.3f}s"

renderer._base_dir = Path("/tmp/docs")
assert (
    renderer._resolve_link("guide.md?plain=1#L2")
    == "file:///tmp/docs/guide.md?plain=1#L2"
)
assert renderer._resolve_link("//example.com/path") is None
assert renderer._resolve_link("http://[") is None
assert renderer._resolve_image("http://[") is None

print("ok: headless Markdown markup")
