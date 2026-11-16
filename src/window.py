# SPDX-License-Identifier: MIT

"""Main window for MD Split: a native GFM editor and preview."""

from __future__ import annotations

import logging
from collections.abc import Callable
from gettext import gettext as _
from gettext import ngettext
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gio, GLib, Gtk, GtkSource

from . import fileio
from .document import Document
from .markdown_view import MarkdownView

log = logging.getLogger(__name__)

APP_ID = "com.james2doyle.MdSplit"


def _io_error_matches(error: Exception, code: Gio.IOErrorEnum) -> bool:
    matches = getattr(error, "matches", None)
    return bool(
        matches and matches(Gio.io_error_quark(), code)
    )

_MAX_WORD_COUNT_CHARS = 2_000_000

_gtksource_types_ready = False


def _ensure_gtksource_types() -> None:
    """Force GtkSource GTypes to register before GtkBuilder parses the template.

    PyGObject registers namespace types lazily, and GtkBuilder needs
    GtkSourceView to exist when it builds window.ui.
    """
    global _gtksource_types_ready
    if _gtksource_types_ready:
        return
    GtkSource.View()
    _gtksource_types_ready = True


@Gtk.Template(resource_path="/com/james2doyle/MdSplit/window.ui")
class MdSplitWindow(Adw.ApplicationWindow):
    __gtype_name__ = "MdSplitWindow"

    window_title = Gtk.Template.Child("window_title")
    button_preview = Gtk.Template.Child("button_preview")
    editor_view = Gtk.Template.Child("editor_view")
    paned = Gtk.Template.Child("paned")
    preview_container = Gtk.Template.Child("preview_container")
    placeholder_label = Gtk.Template.Child("placeholder_label")
    label_cursor = Gtk.Template.Child("label_cursor")
    label_stats = Gtk.Template.Child("label_stats")

    def __init__(self, **kwargs):
        _ensure_gtksource_types()
        super().__init__(**kwargs)
        self._settings = Gio.Settings(schema_id=APP_ID)
        self._document = Document()
        self._loading = False
        self._preview_timeout = 0
        self._stats_timeout = 0
        self._file_dialog = None
        self._confirm_dialog = None
        self._error_dialog = None
        self._load_cancellable = None
        self._load_generation = 0
        self._document_epoch = 0
        self._save_queue: list[
            tuple[Gio.File, Callable[[], None] | None, int]
        ] = []
        self._save_active = False
        self._destroyed = False
        self._force_close = False
        self._focused_once = False
        self._signal_handlers: list[tuple[object, int]] = []

        self.set_icon_name(APP_ID)
        self._preview = MarkdownView()
        self.preview_container.set_child(self._preview)

        self._setup_editor()
        self._setup_window()
        self._connect_signals()
        self._update_ui(render_preview=True)

    # -- setup -----------------------------------------------------------

    def _setup_editor(self) -> None:
        self._buffer = GtkSource.Buffer()
        language = GtkSource.LanguageManager.get_default().get_language("markdown")
        if language is not None:
            self._buffer.set_language(language)
        self._buffer.set_highlight_syntax(True)
        self.editor_view.set_buffer(self._buffer)
        self._apply_editor_scheme()

    def _setup_window(self) -> None:
        width = self._settings.get_int("window-width")
        height = self._settings.get_int("window-height")
        if width >= 600 and height >= 400:
            self.set_default_size(width, height)

        position = self._settings.get_int("paned-position")
        if position > 0:
            GLib.idle_add(self._apply_paned_position, position)

        show_preview = self._settings.get_boolean("show-preview")
        self.preview_container.set_visible(show_preview)
        self._preview.set_paused(not show_preview)
        app = self.get_application()
        if app is not None:
            app.set_preview_visible(show_preview)

        style_manager = Adw.StyleManager.get_default()
        self._style_handler = style_manager.connect(
            "notify::dark", self._on_dark_changed
        )
        self._preview.set_dark(style_manager.get_dark())
        self._preview.set_remote_images(
            self._settings.get_boolean("remote-images")
        )
        self._settings_handler = self._settings.connect(
            "changed::remote-images", self._on_remote_images_changed
        )

    def _connect_signals(self) -> None:
        self._signal_handlers.extend(
            [
                (
                    self._buffer,
                    self._buffer.connect("changed", self._on_buffer_changed),
                ),
                (
                    self._buffer,
                    self._buffer.connect(
                        "notify::cursor-position", self._on_cursor_moved
                    ),
                ),
                (self, self.connect("close-request", self._on_close_request)),
                (self, self.connect("destroy", self._on_destroy)),
                (self, self.connect("map", self._on_map)),
            ]
        )

    def _apply_editor_scheme(self) -> None:
        scheme_id = "Adwaita-dark" if Adw.StyleManager.get_default().get_dark() else "Adwaita"
        scheme = GtkSource.StyleSchemeManager.get_default().get_scheme(scheme_id)
        if scheme is not None:
            self._buffer.set_style_scheme(scheme)

    def _apply_paned_position(self, position: int) -> bool:
        self.paned.set_position(position)
        return False

    def _on_map(self, *_args) -> None:
        if not self._focused_once:
            self._focused_once = True
            self.editor_view.grab_focus()

    # -- public API ------------------------------------------------------

    @property
    def document(self) -> Document:
        return self._document

    @property
    def preview(self) -> MarkdownView:
        return self._preview

    def get_text(self) -> str:
        start, end = self._buffer.get_bounds()
        return self._buffer.get_text(start, end, True)

    def set_text(self, text: str) -> None:
        self._set_buffer_text(text)
        self._document.set_text(text)
        self._update_ui()
        self.flush_preview()

    def flush_preview(self) -> None:
        self._cancel_preview_timeout()
        self._render_preview()

    def new_document(self) -> None:
        self._confirm_discard(
            _("Save changes before creating a new document?"),
            self._reset_document,
        )

    def open_document(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Open Markdown File"))
        dialog.set_accept_label(_("Open"))
        filters, default_filter = self._make_filters()
        dialog.set_filters(filters)
        dialog.set_default_filter(default_filter)
        folder = self._initial_folder()
        if folder is not None:
            dialog.set_initial_folder(folder)
        self._file_dialog = dialog
        dialog.open(self, None, self._on_open_finished)

    def open_file(self, file: Gio.File, on_loaded=None) -> None:
        if self._document.is_dirty:
            self._confirm_discard(
                _("Save changes before opening another file?"),
                lambda: self._load_file(file, on_loaded),
            )
        else:
            self._load_file(file, on_loaded)

    def save_document(self) -> None:
        self.save_document_then(None)

    def save_document_then(self, callback) -> None:
        self._document.set_text(self.get_text())
        if self._document.file is not None:
            self._write_file(self._document.file, callback)
        else:
            self._save_as(callback)

    def save_as_document(self) -> None:
        self._save_as(None)

    def set_preview_visible(self, visible: bool) -> None:
        self.preview_container.set_visible(visible)
        self._preview.set_paused(not visible)
        self._settings.set_boolean("show-preview", visible)
        if visible:
            self.flush_preview()
        else:
            self._cancel_preview_timeout()

    # -- editor signals --------------------------------------------------

    def _on_buffer_changed(self, *_args) -> None:
        if self._loading:
            return
        self._document.set_text(self.get_text())
        self._update_ui(update_stats=False)
        self._schedule_stats()
        self._schedule_preview()

    def _on_cursor_moved(self, *_args) -> None:
        insert = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        line = insert.get_line() + 1
        column = insert.get_line_offset() + 1
        self.label_cursor.set_label(
            _("Ln {line}, Col {column}").format(line=line, column=column)
        )

    def _on_dark_changed(self, *_args) -> None:
        self._apply_editor_scheme()
        self._preview.set_dark(Adw.StyleManager.get_default().get_dark())

    def _on_remote_images_changed(self, settings, _key) -> None:
        self._preview.set_remote_images(settings.get_boolean("remote-images"))
        if self.preview_container.get_visible():
            self.flush_preview()

    # -- UI updates ------------------------------------------------------

    def _update_ui(
        self, render_preview: bool = False, update_stats: bool = True
    ) -> None:
        name = self._document.display_name
        dirty_marker = " \u2022" if self._document.is_dirty else ""
        self.window_title.set_title(f"{name}{dirty_marker}")
        self.window_title.set_subtitle(self._document.location_subtitle)
        self.set_title(f"{name}{dirty_marker} \u2014 MD Split")
        if update_stats:
            self._cancel_stats_timeout()
            self._update_stats()
        self._update_placeholder()
        self._on_cursor_moved()
        if render_preview:
            self.flush_preview()

    def _update_stats(self) -> None:
        characters = self._document.character_count
        character_text = ngettext(
            "{n} character", "{n} characters", characters
        ).format(n=characters)
        if characters > _MAX_WORD_COUNT_CHARS:
            self.label_stats.set_label(
                _("{characters} \u00b7 word count paused for large document").format(
                    characters=character_text
                )
            )
            return
        words = self._document.word_count
        word_text = ngettext("{n} word", "{n} words", words).format(n=words)
        self.label_stats.set_label(f"{word_text} \u00b7 {character_text}")

    def _update_placeholder(self) -> None:
        self.placeholder_label.set_visible(self._buffer.get_char_count() == 0)

    def _schedule_stats(self) -> None:
        self._cancel_stats_timeout()
        self._stats_timeout = GLib.timeout_add(120, self._update_stats_now)

    def _cancel_stats_timeout(self) -> None:
        if self._stats_timeout:
            GLib.source_remove(self._stats_timeout)
            self._stats_timeout = 0

    def _update_stats_now(self) -> bool:
        self._stats_timeout = 0
        if not self._destroyed:
            self._update_stats()
        return False

    def _schedule_preview(self) -> None:
        self._cancel_preview_timeout()
        if not self.preview_container.get_visible():
            return
        self._preview_timeout = GLib.timeout_add(180, self._render_preview)

    def _cancel_preview_timeout(self) -> None:
        if self._preview_timeout:
            GLib.source_remove(self._preview_timeout)
            self._preview_timeout = 0

    def _render_preview(self) -> bool:
        self._preview_timeout = 0
        if self.preview_container.get_visible() and not self._destroyed:
            self._preview.set_markdown(
                self.get_text(),
                self._document.directory,
                base_file=self._document.file,
            )
        return False

    def _set_buffer_text(self, text: str) -> None:
        self._loading = True
        self._buffer.set_text(text)
        self._loading = False

    def _reset_document(self) -> None:
        self._invalidate_file_operations()
        self._document.reset()
        self._set_buffer_text("")
        self._update_ui(render_preview=True)
        self.editor_view.grab_focus()

    # -- file operations -------------------------------------------------

    def _make_filters(self):
        markdown_filter = Gtk.FileFilter()
        markdown_filter.set_name(_("Markdown files"))
        for pattern in ("*.md", "*.markdown", "*.mdown", "*.mkd"):
            markdown_filter.add_pattern(pattern)
        markdown_filter.add_mime_type("text/markdown")
        markdown_filter.add_mime_type("text/x-markdown")

        all_filter = Gtk.FileFilter()
        all_filter.set_name(_("All files"))
        all_filter.add_pattern("*")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(markdown_filter)
        filters.append(all_filter)
        return filters, markdown_filter

    def _initial_folder(self) -> Gio.File | None:
        directory = self._document.directory
        if directory is not None and directory.is_dir():
            return Gio.File.new_for_path(str(directory))
        last_folder = self._settings.get_string("last-folder")
        if last_folder and Path(last_folder).is_dir():
            return Gio.File.new_for_path(last_folder)
        return None

    def _remember_folder(self, file: Gio.File) -> None:
        parent = file.get_parent()
        path = parent.get_path() if parent is not None else None
        if path:
            self._settings.set_string("last-folder", path)

    def _on_open_finished(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error as error:
            if not self._is_dismissed(error):
                self._show_error(_("Could not open file"), error.message)
            return
        if file is not None:
            self.open_file(file)

    def _save_as(self, callback) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Save Markdown File"))
        dialog.set_accept_label(_("Save"))
        filters, default_filter = self._make_filters()
        dialog.set_filters(filters)
        dialog.set_default_filter(default_filter)
        dialog.set_initial_name(self._document.display_name)
        folder = self._initial_folder()
        if folder is not None:
            dialog.set_initial_folder(folder)
        self._file_dialog = dialog
        dialog.save(self, None, self._on_save_as_finished, callback)

    def _on_save_as_finished(self, dialog: Gtk.FileDialog, result, callback) -> None:
        try:
            file = dialog.save_finish(result)
        except GLib.Error as error:
            if not self._is_dismissed(error):
                self._show_error(_("Could not save file"), error.message)
            return
        if file is not None:
            self._write_file(file, callback)

    def _cancel_load(self) -> None:
        if self._load_cancellable is not None:
            self._load_cancellable.cancel()
            self._load_cancellable = None

    def _invalidate_file_operations(self) -> None:
        """Detach all pending file callbacks from the current document."""
        self._document_epoch += 1
        self._load_generation += 1
        self._cancel_load()
        self._save_queue.clear()
        self.editor_view.set_editable(True)

    def _load_file(self, file: Gio.File, on_loaded=None) -> None:
        self._document_epoch += 1
        self._save_queue.clear()
        self._load_generation += 1
        generation = self._load_generation
        self._cancel_load()
        cancellable = Gio.Cancellable()
        self._load_cancellable = cancellable
        starting_revision = self._document.revision
        self.editor_view.set_editable(False)
        fileio.load_text_async(
            file,
            lambda text, etag, error: self._on_file_loaded(
                generation,
                starting_revision,
                file,
                text,
                etag,
                error,
                on_loaded,
            ),
            cancellable,
        )

    def _on_file_loaded(
        self,
        generation: int,
        starting_revision: int,
        requested_file: Gio.File,
        text: str | None,
        etag: str | None,
        error: Exception | None,
        on_loaded,
    ) -> None:
        if self._destroyed or generation != self._load_generation:
            return
        self.editor_view.set_editable(True)
        self._load_cancellable = None

        if error is not None:
            if _io_error_matches(error, Gio.IOErrorEnum.CANCELLED):
                return
            if isinstance(error, UnicodeDecodeError):
                self._show_error(
                    _("Could not open file"),
                    _("The file is not valid UTF-8 text."),
                )
            else:
                self._show_error(_("Could not open file"), str(error))
            return

        assert text is not None
        if self._document.revision != starting_revision:
            self._show_error(
                _("Could not open file"),
                _("The document changed while the file was loading."),
            )
            return

        # Invalidate saves started against the previous document while this
        # load was pending.
        self._document_epoch += 1
        self._save_queue.clear()
        self._document.load(text, requested_file, etag)
        self._set_buffer_text(text)
        self._update_ui(render_preview=True)
        self._remember_folder(requested_file)
        self._buffer.place_cursor(self._buffer.get_start_iter())
        self.editor_view.scroll_to_iter(
            self._buffer.get_start_iter(), 0.0, False, 0.0, 0.0
        )
        self.editor_view.grab_focus()
        if on_loaded is not None:
            on_loaded()

    def _write_file(
        self, file: Gio.File, callback: Callable[[], None] | None
    ) -> None:
        self._document.set_text(self.get_text())
        self._save_queue.append((file, callback, self._document_epoch))
        self._start_next_save()

    def _start_next_save(self) -> None:
        if self._save_active:
            return
        while self._save_queue and self._save_queue[0][2] != self._document_epoch:
            self._save_queue.pop(0)
        if not self._save_queue:
            return

        requested_file, callback, epoch = self._save_queue.pop(0)
        snapshot = self.get_text()
        self._document.set_text(snapshot)
        same_file = (
            self._document.file is not None
            and requested_file.equal(self._document.file)
        )
        expected_etag = self._document.etag if same_file else None
        self._save_active = True
        fileio.save_text_async(
            requested_file,
            snapshot,
            lambda error, etag: self._on_file_written(
                epoch,
                requested_file,
                snapshot,
                error,
                etag,
                callback,
            ),
            etag=expected_etag,
        )

    def _on_file_written(
        self,
        epoch: int,
        requested_file: Gio.File,
        snapshot: str,
        error: Exception | None,
        etag: str | None,
        callback: Callable[[], None] | None,
    ) -> None:
        self._save_active = False
        if self._destroyed or epoch != self._document_epoch:
            self._start_next_save()
            return

        if error is not None:
            self._save_queue.clear()
            if _io_error_matches(error, Gio.IOErrorEnum.CANCELLED):
                return
            if _io_error_matches(error, Gio.IOErrorEnum.WRONG_ETAG):
                self._show_error(
                    _("File changed on disk"),
                    _(
                        "The file was changed by another application. "
                        "Reopen it before saving again."
                    ),
                )
            else:
                self._show_error(_("Could not save file"), str(error))
            return

        self._document.mark_saved(
            requested_file, saved_text=snapshot, etag=etag
        )
        self._remember_folder(requested_file)
        self._update_ui()

        has_queued_save = bool(self._save_queue)
        self._start_next_save()
        if (
            callback is not None
            and not has_queued_save
            and self._document.text == snapshot
        ):
            callback()

    # -- dialogs ---------------------------------------------------------

    def _confirm_discard(self, heading: str, on_discard) -> None:
        if not self._document.is_dirty:
            on_discard()
            return

        dialog = Adw.AlertDialog()
        dialog.set_heading(heading)
        dialog.set_body(_("Your changes will be lost if you don’t save them."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("discard", _("Discard"))
        dialog.add_response("save", _("Save"))
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response: str) -> None:
            if response == "discard":
                on_discard()
            elif response == "save":
                self.save_document_then(on_discard)

        dialog.connect("response", on_response)
        self._confirm_dialog = dialog
        dialog.present(self)

    def _show_error(self, heading: str, message: str) -> None:
        dialog = Adw.AlertDialog()
        dialog.set_heading(heading)
        dialog.set_body(message)
        dialog.add_response("close", _("Close"))
        dialog.set_default_response("close")
        dialog.set_close_response("close")
        self._error_dialog = dialog
        dialog.present(self)

    def _is_dismissed(self, error: GLib.Error) -> bool:
        return error.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED) or error.matches(
            Gtk.DialogError.quark(), Gtk.DialogError.CANCELLED
        )

    # -- window lifecycle ------------------------------------------------

    def _on_destroy(self, *_args) -> None:
        self._destroyed = True
        self._cancel_preview_timeout()
        self._cancel_stats_timeout()
        self._invalidate_file_operations()
        for owner, handler_id in self._signal_handlers:
            disconnect = getattr(owner, "disconnect", None)
            if disconnect is not None:
                try:
                    disconnect(handler_id)
                except (TypeError, RuntimeError):
                    pass
        self._signal_handlers.clear()
        style_manager = Adw.StyleManager.get_default()
        if getattr(self, "_style_handler", 0):
            style_manager.disconnect(self._style_handler)
            self._style_handler = 0
        if getattr(self, "_settings_handler", 0):
            self._settings.disconnect(self._settings_handler)
            self._settings_handler = 0
        self._preview.shutdown()

    def _on_close_request(self, *_args) -> bool:
        if self._force_close:
            return False
        self._save_settings()
        if not self._document.is_dirty:
            return False
        self._confirm_discard(
            _("Save changes before closing?"),
            self._close_now,
        )
        return True

    def _close_now(self) -> None:
        self._force_close = True
        self.destroy()

    def _save_settings(self) -> None:
        width = self.get_width()
        height = self.get_height()
        if width > 0:
            self._settings.set_int("window-width", width)
        if height > 0:
            self._settings.set_int("window-height", height)
        self._settings.set_int("paned-position", self.paned.get_position())
        self._settings.set_boolean(
            "show-preview", self.preview_container.get_visible()
        )
