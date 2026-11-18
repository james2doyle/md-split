"""Headless tests for the preview's Vim key parser and search matcher."""

import os
import sys

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src.preview_vim import (
    PENDING,
    PENDING_RESET,
    Match,
    PreviewAction,
    PreviewKeyParser,
    compile_query,
    find_matches,
)


def feed(parser, *keys, ctrl=False, shift=False):
    result = None
    for key in keys:
        result = parser.feed(key, ctrl=ctrl, shift=shift)
    return result


p = PreviewKeyParser()

# Single keys.
assert feed(p, "j") == PreviewAction("scroll-down")
assert feed(p, "k") == PreviewAction("scroll-up")
assert feed(p, "Down") == PreviewAction("scroll-down")
assert feed(p, "G") == PreviewAction("bottom")
assert feed(p, "space") == PreviewAction("page-down")
assert feed(p, "space", shift=True) == PreviewAction("page-up")
assert feed(p, "/") == PreviewAction("search-forward")
assert feed(p, "?") == PreviewAction("search-backward")
assert feed(p, "n") == PreviewAction("next-match")
assert feed(p, "N") == PreviewAction("previous-match")

# Ctrl motions.
assert feed(p, "d", ctrl=True) == PreviewAction("half-page-down")
assert feed(p, "u", ctrl=True) == PreviewAction("half-page-up")
assert feed(p, "f", ctrl=True) == PreviewAction("page-down")
assert feed(p, "b", ctrl=True) == PreviewAction("page-up")
assert feed(p, "e", ctrl=True) == PreviewAction("scroll-down")

# Unknown keys propagate so app shortcuts still work.
assert feed(p, "s", ctrl=True) is None
assert feed(p, "q") is None
assert feed(p, "Tab") is None
assert not p.pending

# Counts.
assert feed(p, "5") is PENDING
assert p.pending
assert feed(p, "j") == PreviewAction("scroll-down", 5)
assert PreviewAction("scroll-down", 5).repeat == 5
assert PreviewAction("scroll-down").repeat == 1
assert feed(p, "1", "2", "k") == PreviewAction("scroll-up", 12)
assert feed(p, "1", "0", "j") == PreviewAction("scroll-down", 10)
assert feed(p, "0") is None  # a bare 0 is not a count
assert feed(p, "9", "9", "9", "9", "9", "j") == PreviewAction("scroll-down", 9999)
assert feed(p, "3", "d", ctrl=False) is None  # unknown key clears the count
assert not p.pending

# {count}G jumps to that percentage.
assert feed(p, "5", "0", "G") == PreviewAction("goto-percent", 50)

# Two-key sequences.
assert feed(p, "g") is PENDING
assert feed(p, "g") == PreviewAction("top")
assert feed(p, "]", "]") == PreviewAction("next-heading")
assert feed(p, "[", "[") == PreviewAction("previous-heading")
assert feed(p, "2", "]", "]") == PreviewAction("next-heading", 2)
assert feed(p, "g", "x") is PENDING_RESET
assert not p.pending

# Ctrl+W window commands.
assert feed(p, "w", ctrl=True) is PENDING
assert feed(p, "w") == PreviewAction("focus-other")
assert feed(p, "w", ctrl=True) is PENDING
assert feed(p, "w", ctrl=True) == PreviewAction("focus-other")
assert feed(p, "w", ctrl=True) is PENDING
assert feed(p, "h") == PreviewAction("focus-editor")
assert feed(p, "w", ctrl=True) is PENDING
assert feed(p, "l") == PreviewAction("focus-preview")
assert feed(p, "i") == PreviewAction("focus-editor")

# Escape cancels pending input.
feed(p, "4")
feed(p, "g")
assert p.pending
assert feed(p, "Escape") == PreviewAction("cancel")
assert not p.pending
assert feed(p, "[", ctrl=True) == PreviewAction("cancel")

# Smartcase: lowercase queries ignore case, any uppercase is exact.
texts = ["Hello world", "say hello", "HELLO"]
assert find_matches(texts, "hello") == [
    Match(0, 0, 5),
    Match(1, 4, 9),
    Match(2, 0, 5),
]
assert find_matches(texts, "Hello") == [Match(0, 0, 5)]

# Regex queries and several matches in one text.
assert find_matches(["a1 b22 c333"], r"\d+") == [
    Match(0, 1, 2),
    Match(0, 4, 6),
    Match(0, 8, 11),
]

# Invalid and empty patterns match nothing; empty matches are skipped.
assert compile_query("[") is None
assert find_matches(["abc"], "[") == []
assert find_matches(["abc"], "") == []
assert find_matches(["abc"], "x*") == []

print("ok: preview vim helpers")
