"""Headless tests for session and recent-file helpers."""

import os
import sys
import tempfile
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src.session import (
    add_recent,
    dedupe_paths,
    prune_missing,
    remove_recent,
)

assert dedupe_paths(["", "/a", "/a", "/b", "/b"]) == ["/a", "/b"]

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    first = root / "first.md"
    second = root / "second.md"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    existing, missing = prune_missing(
        [str(first), "", str(second), str(first)]
    )
    assert existing == [str(first), str(second)]
    assert missing == []

    existing, missing = prune_missing(
        [str(first), str(root / "gone.md"), str(second)]
    )
    assert existing == [str(first), str(second)]
    assert missing == [str(root / "gone.md")]

assert add_recent(["/b", "/a"], "/c") == ["/c", "/b", "/a"]
assert add_recent(["/a", "/b"], "/b") == ["/b", "/a"]
assert add_recent(["/a", "/b", "/c"], "/d", limit=2) == ["/d", "/a"]
assert remove_recent(["/a", "/b"], "/a") == ["/b"]
assert remove_recent(["/a"], "/missing") == ["/a"]

print("ok: session helpers")
