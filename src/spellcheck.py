# SPDX-License-Identifier: MIT

"""Optional libspelling integration.

The app keeps working when libspelling or its dictionaries are unavailable;
callers receive ``None`` and leave spell checking disabled.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import gi

log = logging.getLogger(__name__)
_warned = False

_DICTIONARY_DIRS = (
    Path("/usr/share/hunspell"),
    Path("/usr/share/myspell"),
    Path("/usr/share/aspell"),
    Path("/usr/share/nuspell"),
    Path.home() / ".local/share/hunspell",
    Path.home() / ".local/share/myspell",
)
_DICTIONARY_SUFFIXES = {".dic", ".aff", ".rws", ".wl"}

try:
    gi.require_version("Spelling", "1")
    from gi.repository import Spelling
except (ImportError, ValueError):
    Spelling = None


def _warn_unavailable(reason: str) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    log.warning("Spell checking disabled: %s", reason)


def has_dictionary_sources(
    directories: tuple[Path, ...] | list[Path] | None = None,
) -> bool:
    """Check for dictionary files before loading libenchant.

    Loading the provider without any dictionary plugins makes libenchant print
    warnings for every missing backend. A forced-availability escape hatch is
    available for layouts that keep dictionaries elsewhere.
    """
    if os.environ.get("MD_SPLIT_SPELLCHECK") == "1":
        return True
    for directory in directories or _DICTIONARY_DIRS:
        try:
            entries = directory.iterdir()
        except OSError:
            continue
        for entry in entries:
            if entry.suffix.lower() in _DICTIONARY_SUFFIXES:
                return True
    return False


def language_choices() -> list[tuple[str, str]]:
    """Return ``(code, name)`` pairs exposed by the system provider."""
    if Spelling is None:
        _warn_unavailable(
            "the libspelling GI namespace is not available"
        )
        return []
    if not has_dictionary_sources():
        _warn_unavailable(
            "no dictionary sources found; install hunspell, aspell, or "
            "nuspell dictionaries"
        )
        return []
    try:
        Spelling.init()
        checker = Spelling.Checker.get_default()
        provider = checker.get_provider()
        if provider is None:
            _warn_unavailable("the provider is not available")
            return []
        model = provider.list_languages()
        choices: list[tuple[str, str]] = []
        for index in range(model.get_n_items()):
            language = model.get_item(index)
            code = language.get_code()
            if code:
                choices.append((code, language.get_name() or code))
        if not choices:
            _warn_unavailable(
                "the provider lists no usable dictionaries"
            )
        return choices
    except Exception as error:  # pragma: no cover - backend specific
        _warn_unavailable(f"backend error: {error}")
        return []


def backend_available() -> bool:
    if Spelling is None:
        return False
    return bool(language_choices())


def choose_language(
    choices: list[tuple[str, str]], preferred: str
) -> str:
    """Pick the preferred language, falling back to the first available."""
    codes = [code for code, _name in choices]
    if not codes:
        return ""
    if preferred in codes:
        return preferred
    return codes[0]


def create_adapter(buffer) -> Any | None:
    """Create a ``Spelling.TextBufferAdapter`` when a dictionary exists."""
    if not backend_available():
        return None
    assert Spelling is not None
    try:
        checker = Spelling.Checker.get_default()
        return Spelling.TextBufferAdapter.new(buffer, checker)
    except Exception as error:  # pragma: no cover - backend specific
        log.warning("Could not create spell-check adapter: %s", error)
        return None
