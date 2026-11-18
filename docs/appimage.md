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

## Profiling

The bundle carries its own Python and GTK runtime, so profile the extracted
AppDir. `AppRun` sets `PYTHONHOME`, `PYTHONPATH` and the library path the
bundled interpreter needs; invoking `squashfs-root/usr/bin/python3` directly
does not work. Profiling the mounted AppImage also includes FUSE mount time,
which is not application time.

Extract the release artifact once:

```sh
VERSION=1.2.0
mkdir -p /tmp/md-split-profile && cd /tmp/md-split-profile
gh release download "v$VERSION" --repo james2doyle/md-split \
  --pattern '*x86_64.AppImage'
chmod +x "md_split-$VERSION-x86_64.AppImage"
"./md_split-$VERSION-x86_64.AppImage" --appimage-extract
```

### Import and startup timing

`--help` exits before a window is created, so this measures the launcher and
package imports without opening the app:

```sh
PYTHONPROFILEIMPORTTIME=1 ./squashfs-root/AppRun --help 2>importtime.txt
sort -t'|' -k2 -nr importtime.txt | head -20
```

To include the window, renderer and first preview, start normally and capture
stderr until the timeout stops it:

```sh
PYTHONPROFILEIMPORTTIME=1 timeout 5s \
  ./squashfs-root/AppRun examples/demo.md 2>importtime.txt
```

`timeout` exits with status 124 because the editor stays open; that is
expected. The output is chronological, with inclusive microseconds in the
second column, so sort or filter it for the modules you are investigating.
Release installs ship `unchecked-hash` bytecode, so this measures real start
cost rather than first-run compilation.

### Python CPU sampling

[py-spy](https://github.com/benfred/py-spy) 0.4.2 or newer supports the
Python 3.14 runtime in the bundle. Sampling needs no changes to the AppDir:

```sh
uvx py-spy record -o md-split.svg --rate 100 --duration 10 \
  -- ./squashfs-root/AppRun examples/demo.md
```

Open `md-split.svg` in a browser. The child is stopped when sampling ends. Use
`-f raw` to write collapsed stacks instead, or attach to a running AppImage:

```sh
uvx py-spy top --pid "$(pgrep -n -f 'md_split examples/demo.md')"
```

Launching through py-spy works with the default `ptrace_scope=1`. Attaching to
an already-running process may require `sudo`, or lowering
`kernel.yama.ptrace_scope`.

### GTK and native work

For rendering, layout and main-loop time, use Sysprof with the GTK trace
points:

```sh
sysprof-cli --gtk --use-trace-fd md-split.syscap -- \
  ./squashfs-root/AppRun examples/demo.md
```

Open the `.syscap` file in Sysprof. This records native stacks and GTK
frame-clock data when the bundled GTK is built with tracing support. Sysprof
needs perf event access, so it may require elevated privileges on locked-down
hosts.

`cProfile` also works, but `AppRun` hardcodes `usr/bin/md_split` as the entry
script, so it needs a wrapper or a `sitecustomize.py` in the extracted tree.
py-spy is usually preferable because it samples the unmodified bundle.

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
- The runtime mounts the payload with FUSE on every launch. On some hosts the
  mount and unmount dominate startup; compare the mounted app with an extracted
  `AppRun`. If the difference is large, use the Flatpak or an extracted install.
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
