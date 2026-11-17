# Settings

Settings use the GSettings schema `com.james2doyle.MdSplit` with path
`/com/james2doyle/MdSplit/`. The schema is defined in
`data/com.james2doyle.MdSplit.gschema.xml` and installed under
`share/glib-2.0/schemas`.

## Keys

| Key | Type | Default | Effect |
| --- | --- | --- | --- |
| `window-width` | int | `1100` | Last window width; range 600–4000 |
| `window-height` | int | `720` | Last window height; range 400–3000 |
| `paned-position` | int | `540` | Editor/preview split; range 0–4000 |
| `view-mode` | string | `both` | `both`, `source`, or `preview` |
| `remote-images` | bool | `false` | Fetch HTTP(S) images in the preview |
| `appearance` | string | `system` | `system`, `light`, or `dark` |
| `load-demo-on-startup` | bool | `true` | Load bundled demo when opened without a file |
| `sync-scroll` | bool | `true` | Keep editor and preview scroll positions aligned |
| `autocomplete-links` | bool | `true` | Expand a typed `[]` to `[]()` |
| `last-folder` | string | `""` | Last file-chooser directory |

## When values are written

- `view-mode` is written when the user picks a mode or cycles with F9.
- `remote-images` is written by the menu action and preferences switch.
- `sync-scroll`, `autocomplete-links`, `load-demo-on-startup`, and
  `appearance` are bound in the preferences dialog.
- `window-width`, `window-height`, and `paned-position` are written when the
  window receives a close request. `paned-position` is only stored while both
  panes are visible.
- `last-folder` is updated after a file is opened or saved.

## Command-line overrides

`--source-only`, `--preview-only`, `--no-source`, and `--no-preview` set the
initial view mode for the windows created by that invocation. `--light` and
`--dark` force the appearance for that run. These overrides are held on the
application and are not written to GSettings. Conflicting flags exit with
status 1 before a window is created.

## Inspecting and resetting

For an installed app:

```sh
gsettings get com.james2doyle.MdSplit view-mode
gsettings set com.james2doyle.MdSplit remote-images false
gsettings reset com.james2doyle.MdSplit paned-position
```

For an uninstalled prefix, add the build schema directory:

```sh
GSETTINGS_SCHEMA_DIR="$PWD/build/data" \
  gsettings get com.james2doyle.MdSplit view-mode
```

Reset everything:

```sh
gsettings reset-recursively com.james2doyle.MdSplit
```

## Implementation notes

- Preferences bind booleans with `Gio.Settings.bind()`. `bind()` returns
  `None`; cleanup uses `Gio.Settings.unbind(row, "active")`.
- The appearance row is an `Adw.ComboRow`; changing it writes `appearance` and
  the app listens for `changed::appearance` to update `Adw.StyleManager`.
- Invalid `view-mode` values fall back to `both` in the application and window.
- The CLI overrides are deliberately not persisted so a one-off launch does not
  change the user's saved view or theme.
