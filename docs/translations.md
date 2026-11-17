# Translations

The app uses gettext through Meson's `i18n.gettext('md_split', preset: 'glib')`.
The launcher calls `locale.bindtextdomain()` and `gettext.textdomain()` before
importing the application.

## Adding a language

1. Add the locale code to `po/LINGUAS`, one per line. Keep the file sorted.

   ```text
   de
   fr
   pt_BR
   ```

2. Generate the catalogue:

   ```sh
   meson compile -C build md_split-pot
   meson compile -C build md_split-update-po
   ```

3. Translate `po/<locale>.po` and check it:

   ```sh
   msgfmt --check --check-compatibility -o /dev/null po/<locale>.po
   ```

4. Rebuild and test:

   ```sh
   meson compile -C build
   LANG=<locale>.UTF-8 ./build-install/bin/md_split
   ```

`po/LINGUAS` currently contains no locales; the app falls back to the source
strings until a catalogue is added.

## Strings in source

- Python: use `_()` for singular strings and `ngettext()` for plurals.
- Blueprint: use `_()` for normal strings and `C_()` when a translator context
  is needed. Blueprint is parsed with the C fallback because xgettext does not
  know `.blp`; the syntax is compatible.
- Keep user-visible strings out of f-strings when possible; translators need
  complete messages. Format counts with `ngettext(...).format(n=...)`.
- Add any new source file containing user-visible strings to
  `po/POTFILES.in`. Keep the list sorted.
- AppStream release descriptions can use `translate="no"` when the text is
  intentionally not translated.

## Files

| File | Purpose |
| --- | --- |
| `po/LINGUAS` | Enabled locales |
| `po/POTFILES.in` | Source files scanned by xgettext |
| `po/meson.build` | Meson gettext target |
| `data/*.desktop.in` | Translated desktop entry |
| `data/*.metainfo.xml.in` | Translated AppStream metadata |
| `src/*.blp` | Translated Blueprint UI |

## Pre-release checks

```sh
meson compile -C build
python3 scripts/test.py
```

The suite validates the desktop file, AppStream metadata, schema, and packaged
resources. It does not prove that every catalogue is complete; run
`msgfmt --check` on changed `.po` files and launch the app with the target
locale before releasing.

## Layout and directionality

The UI is currently LTR. If an RTL locale is added, check:

- editor and preview alignment;
- Pango markup directionality;
- file-dialog labels;
- keyboard shortcuts and menu alignment.

Add RTL screenshots or notes to the release PR when making that change.
