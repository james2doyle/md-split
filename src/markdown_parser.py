# SPDX-License-Identifier: MIT

"""Shared Markdown parser configuration for preview and export."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

from markdown_it import MarkdownIt
from mdit_py_plugins.gfm import gfm_plugin

_UNDERLINE_TAG = re.compile(r"<(/?)u>")


def has_valid_underline_markup(text: str) -> bool:
    """Return True when text contains balanced, correctly nested <u> tags."""
    depth = 0
    saw_tag = False
    for match in _UNDERLINE_TAG.finditer(text):
        saw_tag = True
        if match.group(1):
            if depth == 0:
                return False
            depth = 0
        else:
            if depth:
                return False
            depth = 1
    return saw_tag and depth == 0



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
