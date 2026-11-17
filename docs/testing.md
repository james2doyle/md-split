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
- async UTF-8 load/save limits, ETags, and stale callback handling
- editing helpers: wrapping, link completion, list continuation, formatting
- parser output and escaped Pango markup
- standalone HTML and PDF export, including cleanup on failure
- packaged GResource content, icons, demo, and UI files
- desktop, AppStream, and schema validation

They must not require a display, a session bus, or a running app.

## Display tests

Display tests construct GTK widgets in-process and inspect:

- preview widget trees, links, images, and theme changes
- window lifecycle, focus, view modes, and paned positions
- preferences bindings and dialog dismissal
- CLI parsing and application action state
- scroll synchronization and feedback suppression
- remote-image policy and cancellation

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

## CI

`.github/workflows/ci.yml` runs two jobs:

- **test** on Fedora 45: installs GTK/libadwaita/GtkSourceView and Python
  bindings, builds with Meson, runs the suite under Xvfb, installs, and
  smoke-tests the installed launcher.
- **Flatpak lint** on the GNOME 51 Flatpak image: builds the manifest and runs
  `flatpak-builder-lint` on the manifest and local repository.

The release workflow is separate; see [releasing.md](releasing.md).
