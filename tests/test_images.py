"""GUI tests for the remote-image policy and resource limits.

The test server binds to loopback only and never contacts the internet.
"""

import os
import struct
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SOURCE_ROOT)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

if not Gtk.init_check() or Gdk.Display.get_default() is None:
    print("SKIP: no display available")
    sys.exit(77)

Adw.init()

from src import renderer as renderer_module
from src.markdown_view import MarkdownView


def make_png(width=2, height=2):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


requests = []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        requests.append(self.path)
        if self.path == "/slow.png":
            time.sleep(1.5)
        if self.path == "/large.png":
            body = make_png(2, 2) + b"x" * 128_000
        else:
            body = make_png()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, _format, *_args):
        pass


def wait_until(predicate, timeout_ms=3000):
    loop = GLib.MainLoop()
    state = {"timed_out": False}

    def poll():
        if predicate():
            loop.quit()
            return False
        return True

    def timeout():
        state["timed_out"] = True
        loop.quit()
        return False

    GLib.timeout_add(10, poll)
    timeout_id = GLib.timeout_add(timeout_ms, timeout)
    loop.run()
    if not state["timed_out"]:
        GLib.source_remove(timeout_id)
    assert not state["timed_out"], "timed out waiting for image operation"


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
base_url = f"http://127.0.0.1:{server.server_port}"

try:
    view = MarkdownView()

    # Remote fetching is disabled by default.
    view.set_markdown(f"![pixel]({base_url}/pixel.png)")
    while GLib.MainContext.default().iteration(False):
        pass
    assert requests == [], requests
    labels = []
    pending = [view]
    while pending:
        widget = pending.pop()
        if isinstance(widget, Gtk.Label):
            labels.append(widget.get_label())
        child = widget.get_first_child()
        while child is not None:
            pending.append(child)
            child = child.get_next_sibling()
    assert any("Remote image not loaded" in text for text in labels), labels

    # Enabling remote images fetches once and caches the decoded texture.
    view.set_remote_images(True)
    wait_until(lambda: "/pixel.png" in requests and not view.renderer._remote_pending)
    assert requests.count("/pixel.png") == 1, requests

    view.set_markdown(f"![pixel]({base_url}/pixel.png)")
    wait_until(lambda: not view.renderer._remote_pending)
    assert requests.count("/pixel.png") == 1, requests

    # Oversized bodies are rejected while streaming.
    original_limit = renderer_module._MAX_IMAGE_BYTES
    renderer_module._MAX_IMAGE_BYTES = 1024
    try:
        view.set_markdown(f"![large]({base_url}/large.png)")
        wait_until(lambda: not view.renderer._remote_pending)
    finally:
        renderer_module._MAX_IMAGE_BYTES = original_limit
    assert "/large.png" in requests
    assert f"{base_url}/large.png" not in view.renderer._remote_images

    # A stalled response is cancelled by the request timeout.
    original_timeout = renderer_module._IMAGE_TIMEOUT_SECONDS
    renderer_module._IMAGE_TIMEOUT_SECONDS = 1
    try:
        view.set_markdown(f"![slow]({base_url}/slow.png)")
        wait_until(lambda: not view.renderer._remote_pending, timeout_ms=4000)
    finally:
        renderer_module._IMAGE_TIMEOUT_SECONDS = original_timeout
    assert "/slow.png" in requests
    assert f"{base_url}/slow.png" not in view.renderer._remote_images

    # A re-render cancels in-flight local image reads and drops stale widgets.
    import tempfile
    from pathlib import Path

    local = MarkdownView()
    started = []

    def fake_worker(cache_key, path, callbacks, cancellable):
        started.append(cancellable)

    local.renderer._read_local_worker = fake_worker
    with tempfile.TemporaryDirectory() as local_dir:
        (Path(local_dir) / "local.png").write_bytes(make_png())
        local.set_markdown("![Local](local.png)", base_dir=Path(local_dir))
        assert len(started) == 1, started
        first_request = started[0]
        assert isinstance(first_request, Gio.Cancellable), first_request
        assert not first_request.is_cancelled()
        local.set_markdown("![Local](local.png)", base_dir=Path(local_dir))
        assert len(started) == 2, started
        assert first_request.is_cancelled(), (
            "superseded local image read was not cancelled"
        )
        assert not started[1].is_cancelled()
    local.shutdown()

    view.shutdown()
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)

print("ok: remote image policy")
