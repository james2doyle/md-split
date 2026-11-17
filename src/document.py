# SPDX-License-Identifier: MIT

"""Document model for MD Split.

The model is deliberately independent of GTK widgets so it can be tested
headlessly. The window owns the GtkSource.Buffer and mirrors its text here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio

READING_WORDS_PER_MINUTE = 200

# CJK text has no word separators, so count ideographs and kana individually.
_CJK_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)
_WORD_PATTERN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def count_words(text: str) -> int:
    """Count words, treating each CJK character as a word."""
    if not text:
        return 0
    cjk = len(_CJK_PATTERN.findall(text))
    remaining = _CJK_PATTERN.sub(" ", text)
    return cjk + sum(1 for _match in _WORD_PATTERN.finditer(remaining))


def reading_time_minutes_for_words(words: int) -> int:
    """Round a word count up to whole minutes at 200 words per minute."""
    if words <= 0:
        return 0
    return max(1, math.ceil(words / READING_WORDS_PER_MINUTE))


def reading_time_minutes(text: str) -> int:
    return reading_time_minutes_for_words(count_words(text))


def text_statistics(text: str) -> tuple[int, int, int]:
    """Return (words, characters, reading minutes) for a text slice."""
    words = count_words(text)
    return words, len(text), reading_time_minutes_for_words(words)


@dataclass
class Document:
    """A Markdown document and the file it came from."""

    file: Gio.File | None = None
    text: str = ""
    saved_text: str = ""
    etag: str | None = None
    revision: int = 0

    @property
    def is_dirty(self) -> bool:
        return self.text != self.saved_text

    @property
    def display_name(self) -> str:
        if self.file is None:
            return _("Untitled.md")
        return self.file.get_basename() or _("Untitled.md")

    @property
    def directory(self) -> Path | None:
        if self.file is None:
            return None
        parent = self.file.get_parent()
        if parent is None:
            return None
        path = parent.get_path()
        return Path(path) if path else None

    @property
    def location_subtitle(self) -> str:
        if self.file is None:
            return _("Not saved")
        parent = self.file.get_parent()
        if parent is None:
            return _("Not saved")
        return parent.get_parse_name() or parent.get_uri() or _("Not saved")

    @property
    def word_count(self) -> int:
        return count_words(self.text)

    @property
    def character_count(self) -> int:
        return len(self.text)

    def set_text(self, text: str, *, changed: bool = False) -> None:
        """Mirror the editor text.

        ``changed`` lets a caller that already knows the content changed (the
        buffer "changed" signal) skip the full-text comparison.
        """
        if not changed:
            # A length change proves the content differs, so only compare the
            # full text when the lengths match (for example a replacement).
            if len(text) == len(self.text) and text == self.text:
                return
        self.text = text
        self.revision += 1

    def reset(self) -> None:
        self.file = None
        self.etag = None
        self.text = ""
        self.saved_text = ""
        self.revision += 1

    def load(self, text: str, file: Gio.File, etag: str | None = None) -> None:
        self.file = file
        self.etag = etag
        self.text = text
        self.saved_text = text
        self.revision += 1

    def load_demo(self, text: str) -> None:
        """Load bundled content as clean scratch text without a file."""
        self.file = None
        self.etag = None
        self.text = text
        self.saved_text = text
        self.revision += 1

    def mark_saved(
        self,
        file: Gio.File | None = None,
        *,
        saved_text: str | None = None,
        etag: str | None = None,
    ) -> None:
        """Record a completed write without assuming the current text was saved."""
        if file is not None:
            self.file = file
        self.etag = etag
        self.saved_text = self.text if saved_text is None else saved_text
