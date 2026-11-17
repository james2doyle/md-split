# Flathub checklist

The application repository is public at
<https://github.com/james2doyle/md-split>. Flathub builds from the manifest in
the Flathub repository, not from this repository's development manifest.

## Required app metadata

- App ID `com.james2doyle.MdSplit` matches the desktop file, GSettings schema,
  D-Bus service, GResource prefix, and icon names.
- `data/com.james2doyle.MdSplit.metainfo.xml.in` has a valid release entry for
  the submitted version and a public screenshot URL that points at the release
  tag.
- The 128×128 scalable app icon is installed at
  `data/icons/hicolor/scalable/apps/com.james2doyle.MdSplit.svg` and the
  symbolic icon at
  `data/icons/hicolor/symbolic/apps/com.james2doyle.MdSplit-symbolic.svg`.
- The desktop file is installed in `share/applications` and declares
  `Icon=com.james2doyle.MdSplit`.
- The AppStream launchable ID is
  `com.james2doyle.MdSplit.desktop`.
- The release tag is pushed and the screenshot URL resolves, for example:

  ```text
  https://raw.githubusercontent.com/james2doyle/md-split/v1.0.0/docs/screenshot.png
  ```

## Manifest rules

The development manifest (`com.james2doyle.MdSplit.json`) uses a `dir` source
and is suitable for local builds only. Flathub requires a pinned source:

```json
"sources": [
  {
    "type": "archive",
    "url": "https://github.com/james2doyle/md-split/archive/refs/tags/v1.0.0.tar.gz",
    "sha256": "..."
  }
]
```

Use [releasing.md](releasing.md) to create the same archive-and-SHA manifest
locally, then replace the archive path with the public URL for the Flathub
submission. Do not use a branch, a moving tag, or `type: "dir"`.

The module should build with:

```json
"buildsystem": "meson",
"config-opts": ["--libdir=lib", "--buildtype=release"]
```

Keep `runtime-version` aligned with the GNOME runtime the app targets. The
current manifest uses `org.gnome.Platform` / `org.gnome.Sdk` 51.

## Permissions

Current finish arguments:

| Permission | Why |
| --- | --- |
| `--share=ipc` | X11 shared-memory transport |
| `--share=network` | Optional remote images; no background networking |
| `--socket=fallback-x11` | X11 fallback |
| `--socket=wayland` | Wayland |
| `--device=dri` | GTK rendering |

Remote images are disabled by default and only load HTTP(S) URLs after the user
enables them. Files are opened through the file chooser/portal; the app does not
request host filesystem access.

## Validate before submitting

From the repository root:

```sh
meson compile -C build
python3 scripts/test.py
```

CI already runs:

```sh
flatpak-builder-lint manifest <manifest>
flatpak-builder-lint repo repo
```

Build and install the bundle locally:

```sh
flatpak-builder --user --install --force-clean build-flatpak <manifest>
flatpak run com.james2doyle.MdSplit
```

Then verify:

- the window and About dialog show the app icon;
- the desktop entry launches the app;
- the demo document loads when no file is passed;
- remote images are off by default and work when enabled;
- the AppStream screenshot URL opens at the tagged commit;
- the release version matches `meson.build`, `pyproject.toml`, and the
  AppStream release entry.

## Submission

Follow the current Flathub new-app process and open a pull request against the
Flathub repository with the pinned manifest. Flathub rebuilds and signs the
artifact; the `.flatpak` produced by [releasing.md](releasing.md) is for local
testing and GitHub Releases, not the Flathub submission itself.

If Flathub review requests changes to the manifest, keep this repository's
development manifest and release notes in sync, but do not weaken the pinned
source or the runtime version just to make a local build pass.
