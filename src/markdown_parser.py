# SPDX-License-Identifier: MIT

"""Shared Markdown parser configuration for preview and export."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.gfm import gfm_plugin

_UNDERLINE_TAG = re.compile(r"<(/?)u>")

# Markup that the preview and export emit for inline constructs. `<u>` tags are
# only promoted when they interleave with these without crossing them.
_STRUCTURAL_TAGS = {
    "em_open": "i",
    "em_close": "/i",
    "strong_open": "b",
    "strong_close": "/b",
    "s_open": "s",
    "s_close": "/s",
}


def has_valid_underline_inline(
    token: Token,
    *,
    link_allowed: Callable[[str], bool] | None = None,
) -> bool:
    """Return True when an inline token can promote its <u> tags safely.

    Balanced pairs are promoted only when they nest correctly with emphasis,
    strikethrough and links. A pair that opens inside a link or strong span and
    closes outside it would produce misnested Pango markup, so it is left as
    literal text instead.
    """
    stack: list[str] = []
    links: list[bool] = []
    saw_tag = False
    for child in token.children or []:
        kind = child.type
        if kind == "text":
            for match in _UNDERLINE_TAG.finditer(child.content):
                saw_tag = True
                if match.group(1):
                    if not stack or stack[-1] != "u":
                        return False
                    stack.pop()
                else:
                    stack.append("u")
            continue
        if kind == "link_open":
            opens = link_allowed is None or link_allowed(
                child.attrs.get("href", "")
            )
            links.append(opens)
            if opens:
                stack.append("a")
            continue
        if kind == "link_close":
            opens = links.pop() if links else True
            if opens:
                if not stack or stack[-1] != "a":
                    return False
                stack.pop()
            continue
        tag = _STRUCTURAL_TAGS.get(kind)
        if tag is None:
            continue
        if tag.startswith("/"):
            name = tag[1:]
            if not stack or stack[-1] != name:
                return False
            stack.pop()
        else:
            stack.append(tag)
    return saw_tag and not stack


def create_parser() -> MarkdownIt:
    """Create the GFM parser used by the preview and both exporters."""
    parser = MarkdownIt(
        "commonmark",
        {
            "html": False,
            "linkify": False,
            "typographer": False,
            "breaks": False,
        },
    )
    gfm_plugin(parser, tasklists_editable=False)
    return parser
