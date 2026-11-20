# SPDX-License-Identifier: MIT

"""Open local Markdown links in new MD Split instances.

Links to ``.md`` files inside the document directory are handed to a fresh
``md_split --new-instance`` process instead of the system default handler;
everything else keeps the normal launcher behaviour.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

log = logging.getLogger(__name__)

_NEW_INSTANCE_FLAG = "--new-instance"


def _launcher_program() -> str | None:
    """Return the executable that can start another instance, if known."""
    candidates: list[str] = []
    if sys.argv:
        candidates.append(sys.argv[0])
    candidates.append("md_split")
    for candidate in candidates:
        program = (
            shutil.which(candidate)
            if not os.path.isabs(candidate)
            else candidate
        )
        if program and os.path.isfile(program):
            return program
    return None


def markdown_instance_command(uri: str) -> list[str] | None:
    """Build a command opening ``uri`` in a new instance, or ``None``.

    Only absolute ``file:`` URIs whose target exists and ends in ``.md``
    produce a command; everything else stays with the default handler.
    """
    try:
        parsed = urlparse(uri)
    except ValueError:
        return None
    if parsed.scheme.lower() != "file":
        return None
    path = Path(unquote(parsed.path))
    if path.suffix.lower() != ".md" or not path.is_file():
        return None
    program = _launcher_program()
    if program is None:
        return None
    return [program, _NEW_INSTANCE_FLAG, str(path)]


def spawn_markdown_instance(uri: str) -> bool:
    """Open a local ``.md`` ``uri`` in a new MD Split instance.

    Returns ``True`` when a new process was started; ``False`` means the
    caller should fall back to the regular file launcher.
    """
    command = markdown_instance_command(uri)
    if command is None:
        return False
    try:
        subprocess.Popen(
            command,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        log.warning("Could not start new instance: %s", error)
        return False
    return True
