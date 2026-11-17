# SPDX-License-Identifier: MIT

"""Recovery drafts and timestamped file backups."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")

from gi.repository import GLib


@dataclass
class Draft:
    key: str
    text: str
    path: str | None
    name: str
    updated: float


def state_directory(base: Path | None = None) -> Path:
    if base is None:
        override = os.environ.get("MD_SPLIT_STATE_DIR")
        base = (
            Path(override)
            if override
            else Path(GLib.get_user_state_dir()) / "md-split"
        )
    return Path(base)


def recovery_directory(base: Path | None = None) -> Path:
    return state_directory(base) / "recovery"


def backup_directory(base: Path | None = None) -> Path:
    return state_directory(base) / "backups"


def draft_key(path: str | None, token: str) -> str:
    """Return a stable draft key for a file path or an untitled token."""
    value = f"file:{Path(path).expanduser()}" if path else f"untitled:{token}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_draft(draft: Draft, directory: Path | None = None) -> Path:
    target = recovery_directory(directory)
    target.mkdir(parents=True, exist_ok=True)
    metadata = {
        "path": draft.path,
        "name": draft.name,
        "updated": draft.updated,
    }
    _atomic_write(
        target / f"{draft.key}.json",
        json.dumps(metadata).encode("utf-8"),
    )
    text_path = target / f"{draft.key}.md"
    _atomic_write(text_path, draft.text.encode("utf-8"))
    return text_path


def read_draft(key: str, directory: Path | None = None) -> Draft | None:
    target = recovery_directory(directory)
    metadata_path = target / f"{key}.json"
    text_path = target / f"{key}.md"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        text = text_path.read_text(encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return Draft(
        key=key,
        text=text,
        path=metadata.get("path"),
        name=metadata.get("name") or "Untitled.md",
        updated=float(metadata.get("updated") or 0),
    )


def list_drafts(directory: Path | None = None) -> list[Draft]:
    target = recovery_directory(directory)
    if not target.is_dir():
        return []
    drafts: list[Draft] = []
    for metadata_path in target.glob("*.json"):
        draft = read_draft(metadata_path.stem, directory)
        if draft is not None:
            drafts.append(draft)
    drafts.sort(key=lambda draft: draft.updated, reverse=True)
    return drafts


def clear_draft(key: str, directory: Path | None = None) -> None:
    target = recovery_directory(directory)
    (target / f"{key}.json").unlink(missing_ok=True)
    (target / f"{key}.md").unlink(missing_ok=True)


def write_backup(
    path: Path,
    text: str,
    *,
    directory: Path | None = None,
    retention: int = 5,
    now: float | None = None,
) -> Path | None:
    """Write a timestamped backup and delete older ones beyond retention."""
    target = backup_directory(directory)
    target.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime(
        "%Y%m%d-%H%M%S", time.gmtime(now if now is not None else time.time())
    )
    source = Path(path).expanduser()
    digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
    prefix = f"{source.stem}-{digest}"
    candidate = target / f"{prefix}-{timestamp}.md"
    suffix = 1
    while candidate.exists():
        candidate = target / f"{prefix}-{timestamp}-{suffix}.md"
        suffix += 1
    try:
        _atomic_write(candidate, text.encode("utf-8"))
    except OSError:
        return None
    backups = sorted(target.glob(f"{prefix}-*.md"))
    for stale in backups[: max(0, len(backups) - max(1, retention))]:
        stale.unlink(missing_ok=True)
    return candidate
