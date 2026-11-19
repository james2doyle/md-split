# Development

## Requirements

- Python 3.12+ and PyGObject (`Gtk-4.0`, `Adw-1`, `GtkSource-5` GIRs)
- GTK 4 and libadwaita 1.9+ (the Flatpak runtime provides 1.10)
- GtkSourceView 5
- Pycairo for PDF export
- Optional: libspelling, a libenchant provider (hunspell, aspell, nuspell, or
  voikko), and a dictionary for spell checking
- `meson`, `ninja`, `blueprint-compiler`
- `gettext` (`msgfmt`); optional validators: `desktop-file-validate`,
  `appstreamcli`, `glib-compile-schemas`
- `flatpak` and `flatpak-builder` for packaging
- podman or Docker for AppImage builds

The Markdown parser is vendored; install no parser packages.

Spell checking is optional. It needs the libspelling typelib, one libenchant
provider, and at least one dictionary. For example:

```sh
# Debian/Ubuntu
sudo apt install gir1.2-spelling-1 libspelling-1-2 hunspell hunspell-en-us
# Fedora
sudo dnf install libspelling hunspell hunspell-en
# Arch
sudo pacman -S libspelling hunspell hunspell-en_us
```

Leaving the other libenchant providers uninstalled is fine.

## Build and run

```sh
meson setup build --prefix="$PWD/build-install"   # once
meson compile -C build
python3 scripts/test.py
meson install -C build
./build-install/bin/md_split
```

Open a document from the command line:

```sh
./build-install/bin/md_split examples/demo.md
```

The launcher hard-codes the install prefix, so uninstalled runs need the
`build-install` prefix and the `meson install` step. It also adds that prefix
to `GSETTINGS_SCHEMA_DIR` and `XDG_DATA_DIRS`, so schemas and icons resolve
without extra environment setup.

See [testing.md](testing.md) for the test matrix and focused test commands, and
[releasing.md](releasing.md) for release builds.
