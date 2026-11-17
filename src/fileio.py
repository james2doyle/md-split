# SPDX-License-Identifier: MIT

"""Headless asynchronous UTF-8 file helpers.

These wrap GIO's async file APIs and deliberately do not import GTK, so the
save/load behaviour can be tested in a normal headless test.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from gettext import gettext as _

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")

from gi.repository import Gio, GLib

LoadCallback = Callable[[str | None, str | None, Exception | None], None]
SaveCallback = Callable[[Exception | None, str | None], None]

MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
READ_CHUNK_BYTES = 64 * 1024


class FileTooLargeError(Exception):
    """Raised when a file exceeds the editor's input limit."""


def _too_large_error() -> FileTooLargeError:
    return FileTooLargeError(
        _("File is larger than the {size} MiB limit").format(
            size=MAX_DOCUMENT_BYTES // (1024 * 1024)
        )
    )


def _decode_document(chunks: list[bytes], etag: str | None, deliver) -> None:
    """Join and decode a loaded document off the main loop."""
    try:
        text = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as error:
        GLib.idle_add(deliver, None, None, error)
        return
    GLib.idle_add(deliver, text.removeprefix("\ufeff"), etag, None)


def load_text_async(
    file: Gio.File,
    callback: LoadCallback,
    cancellable: Gio.Cancellable | None = None,
) -> None:
    """Read a bounded UTF-8 text file and call callback(text, etag, error)."""
    delivered = False

    def deliver(text: str | None, etag: str | None, error: Exception | None) -> None:
        nonlocal delivered
        if delivered:
            return
        delivered = True
        callback(text, etag, error)

    def finished_info(source: Gio.File, result, _data=None) -> None:
        try:
            info = source.query_info_finish(result)
        except GLib.Error as error:
            deliver(None, None, error)
            return

        etag = info.get_etag()
        if info.get_size() > MAX_DOCUMENT_BYTES:
            deliver(None, None, _too_large_error())
            return

        def finished_open(opened: Gio.File, open_result, _open_data=None) -> None:
            try:
                stream = opened.read_finish(open_result)
            except GLib.Error as error:
                deliver(None, None, error)
                return
            chunks: list[bytes] = []
            total = 0

            def read_next() -> None:
                stream.read_bytes_async(
                    READ_CHUNK_BYTES,
                    GLib.PRIORITY_DEFAULT,
                    cancellable,
                    finished_read,
                )

            def finished_read(stream_source, read_result, _read_data=None) -> None:
                nonlocal total
                try:
                    contents = stream_source.read_bytes_finish(read_result)
                except GLib.Error as error:
                    stream.close(None)
                    deliver(None, None, error)
                    return

                size = contents.get_size()
                if size == 0:
                    stream.close(None)
                    threading.Thread(
                        target=_decode_document,
                        args=(chunks, etag, deliver),
                        daemon=True,
                        name="md-split-decode",
                    ).start()
                    return

                total += size
                if total > MAX_DOCUMENT_BYTES:
                    stream.close(None)
                    deliver(None, None, _too_large_error())
                    return

                chunks.append(contents.get_data())
                read_next()

            read_next()

        source.read_async(GLib.PRIORITY_DEFAULT, cancellable, finished_open)

    file.query_info_async(
        f"{Gio.FILE_ATTRIBUTE_ETAG_VALUE},{Gio.FILE_ATTRIBUTE_STANDARD_SIZE}",
        Gio.FileQueryInfoFlags.NONE,
        GLib.PRIORITY_DEFAULT,
        cancellable,
        finished_info,
    )


def save_text_async(
    file: Gio.File,
    text: str,
    callback: SaveCallback,
    cancellable: Gio.Cancellable | None = None,
    etag: str | None = None,
) -> None:
    """Write UTF-8 text atomically and call callback(error, new_etag)."""
    payload = text.encode("utf-8")

    def finished(source: Gio.File, result, contents) -> None:
        # Keep `contents` in the callback data so the bytes object stays alive
        # until GIO has finished reading from it.
        del contents
        try:
            _success, new_etag = source.replace_contents_finish(result)
        except GLib.Error as error:
            callback(error, None)
            return
        callback(None, new_etag)

    file.replace_contents_async(
        payload,
        etag,
        False,
        Gio.FileCreateFlags.NONE,
        cancellable,
        finished,
        payload,
    )
