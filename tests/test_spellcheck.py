"""Headless tests for spell-check availability and language choice."""

import logging
import os
import sys
import tempfile
from pathlib import Path

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

from src import spellcheck

with tempfile.TemporaryDirectory() as tmp:
    empty = Path(tmp)
    assert not spellcheck.has_dictionary_sources([empty])
    (empty / "en_US.dic").write_text("word", encoding="utf-8")
    assert spellcheck.has_dictionary_sources([empty])

choices = [("en_US", "English (United States)"), ("fr_FR", "French")]
assert spellcheck.choose_language(choices, "fr_FR") == "fr_FR"
assert spellcheck.choose_language(choices, "xx") == "en_US"
assert spellcheck.choose_language(choices, "", "") == "en_US"
assert spellcheck.choose_language(choices, "", "fr_FR") == "fr_FR"
assert spellcheck.choose_language(choices, "", "xx") == "en_US"
assert spellcheck.choose_language([], "") == ""
original_default = spellcheck._default_code
spellcheck._default_code = "fr_FR"
try:
    assert spellcheck.choose_language(choices, "") == "fr_FR"
finally:
    spellcheck._default_code = original_default

original = spellcheck.Spelling
original_warned = spellcheck._warned
spellcheck.Spelling = None
spellcheck._warned = True
try:
    assert spellcheck.backend_available() is False
    assert spellcheck.language_choices() == []
finally:
    spellcheck.Spelling = original
    spellcheck._warned = original_warned

# A missing backend is reported once, not silently ignored on every call.
messages = []


class CaptureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        messages.append(record.getMessage())


handler = CaptureHandler()
spellcheck.log.addHandler(handler)
original_dirs = spellcheck._DICTIONARY_DIRS
original_warned = spellcheck._warned
spellcheck._DICTIONARY_DIRS = ()
spellcheck._warned = False
try:
    assert spellcheck.language_choices() == []
    assert spellcheck.language_choices() == []
finally:
    spellcheck._DICTIONARY_DIRS = original_dirs
    spellcheck._warned = original_warned
    spellcheck.log.removeHandler(handler)
assert len(messages) == 1, messages
assert "Spell checking disabled" in messages[0], messages
# Dictionaries are checked before libspelling loads, so that is the reason.
assert "dictionary" in messages[0].lower(), messages
# Without dictionaries the GI namespace is never imported.
assert spellcheck.Spelling is spellcheck._UNLOADED or spellcheck.Spelling is None

print("ok: spell checking helpers")
