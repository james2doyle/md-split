# Security model

MD Split treats Markdown files, remote images, links, and export destinations as
untrusted input. The app is a native GTK application: it does not embed a
browser, execute JavaScript, or run shell commands from document content.

## Document parsing

- Raw HTML is disabled in the parser (`html: False`).
- The only promoted inline HTML is a balanced, correctly nested `<u>`/`</u>`
  pair. Code spans, unbalanced tags and pairs that cross emphasis or link
  boundaries remain literal text.
- All text placed into `Gtk.Label` Pango markup is escaped with
  `GLib.markup_escape_text`. Pango markup is not HTML.
- Markdown parsing uses the vendored markdown-it-py + GFM parser. No runtime
  parser package is downloaded or imported from the network.

## Links

Link handling rejects the `javascript`, `vbscript`, and `data` schemes. The
preview opens `http`, `https`, and `mailto` links through `Gtk.UriLauncher`.
Relative links resolve against the document's directory or `Gio.File` parent.
Internal `#anchors` stay inside the preview.

HTML and PDF export reject the same unsafe schemes (`javascript`, `vbscript`,
and `data`). Export does not fetch remote images; remote image URLs are
preserved in standalone HTML, and only local images are embedded.

## Remote images

Remote images are disabled by default. The **Load Remote Images** menu item and
preferences switch enable them for the current document. When enabled:

- only `http` and `https` URLs are accepted;
- redirects are checked again and must remain HTTP(S);
- 10 MiB per image and 20 megapixels;
- at most 32 remote images per render;
- a 15 second request timeout;
- images are cached with a bounded count and pixel budget;
- decoding happens off the UI thread, with cancellation on rerender or window
  shutdown.

There is no telemetry, analytics, or background network access. If remote
images are disabled, nothing in the preview is fetched.

## File input

`src/fileio.py` bounds document reads at 64 MiB and reads in 64 KiB chunks.
Files are decoded as UTF-8; invalid input produces an error dialog instead of a
partial document. Loads query the ETag so stale async callbacks can be
discarded.

Saving uses `Gio.File.replace_contents_async()` for atomic replacement. The
window serializes saves and invalidates pending callbacks when the document
changes, so a late write cannot be applied to the wrong file.

## Resource limits

| Limit | Value |
| --- | --- |
| Document read | 64 MiB |
| Preview | 250,000 characters or 10,000 lines |
| Word count | paused above 2,000,000 characters |
| Local images per render | 64 |
| Remote images per render | 32 |
| Remote image size | 10 MiB / 20 megapixels |
| Remote image timeout | 15 seconds |
| HTML export image embedding | 8 MiB per image, 32 MiB total |
| PDF image pixels | 20 megapixels |

The preview shows a paused state rather than attempting to render an
oversized document. Large-document word counting is also paused.

## Export

HTML export produces a standalone document with embedded CSS. Local images are
embedded as bounded data URIs; remote URLs are left as URLs. PDF export uses
Cairo/Pango and writes to a temporary file beside the target, replacing the
target only after a successful finish. A failed PDF write removes the
temporary file.

PDF export requires the optional Cairo binding. The app still starts without
it; the export action reports an error instead of failing application startup.

## Reporting

Please do not publish exploit details in a public issue. Contact the
maintainer through the repository profile with a reproduction and affected
version. There is no bug bounty program.
