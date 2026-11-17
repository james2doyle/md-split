"""Headless tests for Markdown source formatting."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src.formatting import format_markdown, summarize_changes
from src.markdown_parser import create_parser

# Headings, list spacing, task markers and block quotes normalize in place.
source = "\n".join(
    [
        "#  Title  #",
        "",
        "trailing space ",
        "hard break  ",
        "",
        "* item",
        "+   item two",
        "1)   ordered",
        "- [X]  task",
        "- [ ]done",
        "- [X]",
        "",
        ">   quote",
        ">  > nested",
        ">no space",
        "",
        "paragraph with an [inline link](https://example.com/a_(b)).",
        "",
    ]
)
expected = "\n".join(
    [
        "# Title",
        "",
        "trailing space",
        "hard break  ",
        "",
        "* item",
        "+ item two",
        "1) ordered",
        "- [x] task",
        "- [ ]done",
        "- [X]",
        "",
        "> quote",
        "> > nested",
        "> no space",
        "",
        "paragraph with an [inline link](https://example.com/a_(b)).",
        "",
    ]
)
assert format_markdown(source) == expected, format_markdown(source)

# Blank lines collapse, leading/trailing blanks are removed and a final newline
# is ensured.
assert format_markdown("\n\nfirst\n\n\n\nsecond\n\n\n") == "first\n\nsecond\n"
assert format_markdown("") == ""
assert format_markdown("no newline") == "no newline\n"
assert (
    format_markdown("#  Heading  #", ensure_final_newline=False)
    == "# Heading"
)
assert (
    format_markdown("#  Heading  #\n", ensure_final_newline=True)
    == "# Heading\n"
)

# Fence length grows to contain backticks and shrinks when the content allows.
fence = "`````js\nconst fence = \"```\";\n`````\n"
fenced_expected = "````js\nconst fence = \"```\";\n````\n"
assert format_markdown(fence) == fenced_expected, format_markdown(fence)
assert (
    format_markdown("`````\nplain\n`````\n") == "```\nplain\n```\n"
)

# Unclosed fences and their contents stay byte-for-byte unchanged.
unclosed = "`````js\nconst value = 1;\n"
assert format_markdown(unclosed) == unclosed

# Fenced and indented code contents are not touched.
code_source = "\n".join(
    [
        "```python",
        "line with spaces   ",
        "",
        "",
        "x = 1",
        "```",
        "",
        "    indented code   ",
        "",
    ]
)
assert format_markdown(code_source) == code_source

# Front matter is preserved and separated from the body by one blank line.
front_matter = "\n".join(
    [
        "---",
        "title: Test",
        "tags:",
        "  - a",
        "---",
        "#Heading",
        "",
    ]
)
front_expected = "\n".join(
    [
        "---",
        "title: Test",
        "tags:",
        "  - a",
        "---",
        "",
        "#Heading",
        "",
    ]
)
assert format_markdown(front_matter) == front_expected, format_markdown(
    front_matter
)

# Tables align columns and separator rows without changing cell contents.
table = "\n".join(
    [
        "| Name | Value |",
        "|:--|--:|",
        "| a longer cell | 1 |",
        "",
    ]
)
table_expected = "\n".join(
    [
        "| Name          | Value |",
        "| :------------ | ----: |",
        "| a longer cell |     1 |",
        "",
    ]
)
assert format_markdown(table) == table_expected, format_markdown(table)

# Escaped pipes and pipes inside code spans stay in one cell.
escaped_table = "\n".join(
    [
        "| Code | Note |",
        "| --- | --- |",
        "| `a|b` | x \\| y |",
        "",
    ]
)
formatted = format_markdown(escaped_table)
assert "`a|b`" in formatted, formatted
assert "x \\| y" in formatted, formatted

# Formatting is idempotent and preserves the rendered HTML.
for document in (
    source,
    table,
    front_matter,
    code_source,
    escaped_table,
    "#  Title  #\n\n*   item\n",
):
    once = format_markdown(document)
    assert format_markdown(once) == once, document
    parser = create_parser()
    assert parser.render(once) == parser.render(document), document

# Change summaries count changed lines and include a short diff preview.
same = summarize_changes("# Title\n", "# Title\n")
assert not same.changed
assert same.changed_lines == 0
assert same.preview == ""

summary = summarize_changes("#  Title  #\n", "# Title\n")
assert summary.changed
assert summary.changed_lines == 1
assert "-#  Title  #" in summary.preview, summary.preview
assert "+# Title" in summary.preview, summary.preview

multi = summarize_changes("a\n\n\n\nb\n", "a\n\nb\n")
assert multi.changed
assert multi.changed_lines == 2, multi.changed_lines

print("ok: markdown formatting")
