# Testing

The suite is a set of Meson test targets run by `scripts/test.py`. Tests do not
launch a separate app process; GUI tests build widgets and application actions
in-process.

## Quick commands

```sh
meson compile -C build
python3 scripts/test.py
```

Run a release build's tests:

```sh
python3 scripts/test.py -C build-release --print-errorlogs
```

Run one target:

```sh
python3 scripts/test.py -C build "HTML and PDF export"
```

Run under a virtual display (Linux CI or headless development machines):

```sh
xvfb-run --auto-servernum python3 scripts/test.py
```

## Test matrix

| Target | Type |
| --- | --- |
| Validate desktop file | Headless |
| Validate appstream file | Headless |
| Validate schema file | Headless |
| Document model | Headless |
| File I/O | Headless |
| External file changes | Headless |
| Session helpers | Headless |
| Recovery helpers | Headless |
| Spell-check helpers | Headless |
| Editing helpers | Headless |
| List continuation | Headless |
| Packaged resources | Headless |
| HTML and PDF export | Headless |
| GTK warning filters | Headless |
| Markdown markup | Headless |
| Native Markdown renderer | Display |
| Window smoke test | Display |
| Application lifecycle | Display |
| Preferences dialog | Display |
| View modes | Display |
| CLI options | Display |
| Scroll sync | Display |
| Remote image policy | Display |

Display tests call `Gtk.init_check()` and exit with status 77 when no display
is available, so `python3 scripts/test.py` still passes on a headless machine
(those targets report as skipped).

## Sanitized environment

`scripts/test.py` deliberately forwards only a small allowlist of environment
variables to Meson. This prevents API keys, tokens, and other shell secrets
from being copied into `build/meson-logs/`. It also sets:

- `GSETTINGS_BACKEND=memory`
- `PYTHONDONTWRITEBYTECODE=1`
- per-test `HOME`, `XDG_*`, and `GSETTINGS_SCHEMA_DIR` values

Use the wrapper when running the suite locally. If you invoke `meson test`
directly, do not do it from a shell containing secrets.

## Headless tests

Headless tests cover pure logic and file/resource behavior:

- `Document` state, dirty tracking, counts, and file association
- async UTF-8 load/save limits, ETags, worker-thread decoding, and stale
  callback handling
- editing helpers: wrapping, link completion, list continuation, formatting,
  search matching, and replace-all
- recovery draft write/read/clear, backup retention, session path pruning, and
  recent-file ordering
- external-change event classification and self-save filtering
- spell-check language choice and missing-backend fallback
- parser output, escaped Pango markup, path containment and underline nesting
- standalone HTML and PDF export, extension handling, figures and print rules,
  full-width PDF table grids, repeated table headers, row splitting,
  page-spanning quote bars, and cleanup on failure
- packaged GResource content, icons, demo, UI files, and the Meson source list
- desktop, AppStream, and schema validation

They must not require a display, a session bus, or a running app.

## Display tests

Display tests construct GTK widgets in-process and inspect:

- preview widget trees, links, images, theme changes, and nested list indentation
- window lifecycle, focus, view modes, preview render counts, and paned positions
- selection statistics, reading time, find/replace, and search-bar focus
- autosave drafts, recovery prompts, session restore, and recent-file menus
- external-change prompts and spell-check no-backend fallback
- preferences bindings and dialog dismissal
- CLI parsing and application action state
- scroll synchronization, allocation-time restore, and feedback suppression
- local and remote image cancellation, remote-image policy, and export threading
- export overwrite confirmation and geometry clamping

They run under Xvfb in CI. On X11/Xwayland, ibus can crash on
`gdk_x11_surface_get_xid`; use:

```sh
GTK_IM_MODULE=gtk-im-context-simple xvfb-run --auto-servernum python3 scripts/test.py
```

## Adding tests

1. Put pure logic in a headless module and add assertions to the matching
   `tests/test_*.py`.
2. Put widget/application behavior in a display test and self-skip with status
   77 when `Gtk.init_check()` or `Gdk.Display.get_default()` fails.
3. Add a Meson `test()` target in `src/meson.build` with `env: test_env` and,
   if needed, `depends: test_schemas`.
4. Add user-visible strings to `po/POTFILES.in` if they live in a new file.
5. Run the focused target, then the full suite.

See [architecture.md](architecture.md) for where each behavior belongs.

## Manual export QA

Headless tests assert export structure, but styling changes still need a visual
pass:

1. Open a document with a short table, a long table, a tall cell, code,
   quotes, alerts and an image, then export both HTML and PDF.
2. HTML: check the measure, link treatment, table borders and zebra rows,
   figure captions, callout backgrounds, and print preview at A4 and Letter.
3. PDF: check the same table rules, header repetition after a page break, row
   splitting for tall cells, rounded code boxes, quote/alert bars, centered
   images with captions, and the title/page-number footer.
4. Confirm exports stay light-themed and no cell text is clipped or overlaps a
   neighbouring row.

## CI

`.github/workflows/ci.yml` runs two jobs:

- **test** on Fedora 45: installs GTK/libadwaita/GtkSourceView and Python
  bindings, builds with Meson, runs the suite under Xvfb, installs, and
  smoke-tests the installed launcher.
- **Flatpak lint** on the GNOME 51 Flatpak image: builds the manifest and runs
  `flatpak-builder-lint` on the manifest and local repository.

Branch pushes run CI on `main` only, so internal pull requests are tested once;
`v*.*.*` tag pushes also run CI and feed the release workflow. The release
workflow is separate; see [releasing.md](releasing.md).
