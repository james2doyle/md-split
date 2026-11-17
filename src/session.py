# SPDX-License-Identifier: MIT

"""Helpers for restoring sessions and maintaining the recent-file list."""

from __future__ import annotations

from pathlib import Path

DEFAULT_RECENT_LIMIT = 10


def dedupe_paths(paths: list[str]) -> list[str]:
    """Drop empty and repeated entries while preserving order."""
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if not path or path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def prune_missing(paths: list[str]) -> tuple[list[str], list[str]]:
    """Return (existing, missing) paths from a saved session."""
    existing: list[str] = []
    missing: list[str] = []
    for path in dedupe_paths(paths):
        if Path(path).is_file():
            existing.append(path)
        else:
            missing.append(path)
    return existing, missing


def add_recent(
    paths: list[str], path: str, *, limit: int = DEFAULT_RECENT_LIMIT
) -> list[str]:
    """Move a path to the front of the recent list and cap its length."""
    if not path:
        return dedupe_paths(paths)[:limit]
    return dedupe_paths([path, *paths])[:limit]


def remove_recent(paths: list[str], path: str) -> list[str]:
    return [item for item in dedupe_paths(paths) if item != path]
