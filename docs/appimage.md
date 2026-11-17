# AppImage

The AppImage is an x86_64 single-file build for Linux desktops that cannot or
do not want to use Flatpak. It bundles the app, Python, PyGObject, GTK 4,
libadwaita, GtkSourceView 5, Pycairo, GSettings schemas, icons, translations,
libspelling and an English dictionary.

The build is intentionally not run on the host. `appimage-builder` resolves
runtime packages from Ubuntu 26.04 and uses its AppRun runtime to select a
compatible glibc at launch. A podman or Docker installation is required.

## Build

```sh
./scripts/build-appimage.sh
```

The script:

1. reads the version from `pyproject.toml` unless `VERSION` is set;
2. starts an `ubuntu:26.04` container;
3. installs Meson, Blueprint, GTK, libadwaita and GtkSourceView build tools;
4. installs `appimage-builder` 1.1.0 with a Python 3.12 tool environment;
5. builds the app with `--buildtype=release` and installs it into the AppDir;
6. bundles runtime packages from the Ubuntu 26.04 archive;
7. writes `dist/md_split-<version>-x86_64.AppImage`.

The first build downloads the container image and package metadata, so it
needs network access and takes several minutes. Later builds reuse the podman
image and are faster.

Use a release version explicitly when testing a tag build:

```sh
VERSION=1.2.3 ./scripts/build-appimage.sh
```

## Run and verify

```sh
chmod +x dist/md_split-1.0.0-x86_64.AppImage
./dist/md_split-1.0.0-x86_64.AppImage examples/demo.md
```

Without FUSE, use the runtime's extract-and-run option:

```sh
./dist/md_split-1.0.0-x86_64.AppImage --appimage-extract-and-run \
  examples/demo.md
```

Extract and check the launcher without a display:

```sh
./dist/md_split-1.0.0-x86_64.AppImage --appimage-extract
./squashfs-root/AppRun --help
```

The release workflow starts the extracted AppRun under Xvfb with
`examples/demo.md` and treats a timeout as success, because the editor stays
open until the user closes it.

## Runtime behavior

- Settings, session state and recovery drafts use the normal XDG directories.
  The AppImage does not write into its own mount.
- `APPDIR` makes the installed launcher resolve `share/md_split`, translations,
  schemas and icons inside the bundle. A normal system install keeps using the
  configured prefix.
- Spell checking uses libspelling and the bundled `en_US` dictionary. Add
  another dictionary with `DICPATH` if needed. The feature remains optional;
  startup does not fail when the provider is missing.
- Remote images remain off by default.
- PDF export uses the bundled Pycairo and Pango.

## Limits

- The artifact is unsigned and has no update metadata. Download it from the
  release page and verify the published `SHA256SUMS`.
- It targets x86_64 only.
- It relies on the host desktop for fonts, input methods, the GL/EGL loader
  and GPU drivers. Desktop installs already provide these; minimal containers
  need `libgl1` and `libegl1`.
- Some hosts still need FUSE or the extract-and-run option.
- Flatpak remains the recommended distribution format for a fully sandboxed
  install and desktop integration.

## Troubleshooting

If the AppImage does not start, run it with `--appimage-extract-and-run` to
bypass FUSE. The bundle includes X11 and Wayland client libraries but uses
host GPU drivers and fonts; confirm the host has a working display and driver
stack. For spell-check issues, verify `libspelling` is loaded from the bundle
and check `DICPATH`. See [troubleshooting.md](troubleshooting.md) for local
build and stale-UI checks.
