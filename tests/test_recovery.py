"""Headless tests for autosave drafts, recovery and backups."""

import os
import sys
import tempfile
import time
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src.recovery import (
    Draft,
    clear_draft,
    draft_key,
    list_drafts,
    read_draft,
    write_backup,
    write_draft,
)

assert draft_key("/tmp/note.md", "one") == draft_key(
    "/tmp/note.md", "two"
)
assert draft_key(None, "one") != draft_key(None, "two")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    key = draft_key("/tmp/note.md", "token")
    draft = Draft(
        key=key,
        text="# Recovered\n",
        path="/tmp/note.md",
        name="note.md",
        updated=time.time(),
    )
    write_draft(draft, directory=root)
    loaded = read_draft(key, directory=root)
    assert loaded is not None
    assert loaded.text == draft.text
    assert loaded.path == draft.path
    assert loaded.name == draft.name
    assert [item.key for item in list_drafts(directory=root)] == [key]

    clear_draft(key, directory=root)
    assert read_draft(key, directory=root) is None
    assert list_drafts(directory=root) == []

    saved = Path(tmp) / "saved.md"
    saved.write_text("old", encoding="utf-8")
    first = write_backup(
        saved,
        "first",
        directory=root,
        retention=2,
        now=1_700_000_000,
    )
    assert first is not None
    assert first.read_text(encoding="utf-8") == "first"
    second = write_backup(
        saved,
        "second",
        directory=root,
        retention=2,
        now=1_700_000_100,
    )
    assert second is not None
    assert second.read_text(encoding="utf-8") == "second"
    third = write_backup(
        saved,
        "third",
        directory=root,
        retention=2,
        now=1_700_000_200,
    )
    assert third is not None
    assert third.read_text(encoding="utf-8") == "third"
    backups = sorted((root / "backups").glob("saved-*.md"))
    assert len(backups) == 2, backups
    assert first not in backups

print("ok: recovery helpers")
