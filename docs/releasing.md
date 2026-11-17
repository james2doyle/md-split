# Releasing MD Split

Releases are built from an annotated tag, not from an arbitrary working tree.
The version comes from `meson.build`; keep `pyproject.toml` and
`data/com.james2doyle.MdSplit.metainfo.xml.in` in sync.

## Prepare

1. Set the new version in `meson.build`, `pyproject.toml`, and the AppStream
   release entry. Update the AppStream screenshot URL to the new tag.
2. Run the checks:

   ```sh
   meson compile -C build
   python3 scripts/test.py
   uvx pyright src/*.py tests/*.py
   uvx ruff check --select E9,F63,F7,F82,F401,I001 \
     --exclude src/vendor src tests scripts dev.py
   for file in src/*.blp; do
     blueprint-compiler compile "$file" >/dev/null
     blueprint-compiler lint "$file"
   done
   ```

3. Commit and push the release, then create and push the tag:

   ```sh
   export VERSION=1.0.0
   export TAG="v$VERSION"

   git tag -a "$TAG" -m "MD Split $VERSION"
   git push origin main
   git push origin "$TAG"
   ```

## Native optimized build

```sh
meson setup build-release --buildtype=release \
  --prefix="$PWD/build-release-install"
meson compile -C build-release
python3 scripts/test.py -C build-release --print-errorlogs
meson install -C build-release
./build-release-install/bin/md_split
```

This build uses the system GTK, libadwaita and PyGObject stack. Use the
Flatpak build for a self-contained artifact.

## Flatpak release bundle

The development manifest (`com.james2doyle.MdSplit.json`) builds the working
tree and does not set a release build type. For a release, create an archive
from the tag and a derived manifest with a SHA-256-pinned `archive` source and
`--buildtype=release`. The manifest step uses `jq`.

```sh
export VERSION=1.0.0
export TAG="v$VERSION"

rm -rf dist build-flatpak .flatpak-builder
mkdir -p dist

git archive --format=tar.gz --prefix="md-split-$VERSION/" \
  -o "dist/md-split-$VERSION.tar.gz" "$TAG"

sha=$(sha256sum "dist/md-split-$VERSION.tar.gz" | cut -d' ' -f1)
jq --arg sha "$sha" --arg archive "md-split-$VERSION.tar.gz" '
  .modules[0].sources = [{
    "type": "archive",
    "path": $archive,
    "sha256": $sha
  }]
  | .modules[0]["config-opts"] = ["--libdir=lib", "--buildtype=release"]
' com.james2doyle.MdSplit.json > "dist/com.james2doyle.MdSplit.release.json"

flatpak-builder --force-clean --repo=dist/repo --state-dir=.flatpak-builder \
  --default-branch=stable --subject="MD Split $VERSION" \
  build-flatpak "dist/com.james2doyle.MdSplit.release.json"

flatpak build-bundle dist/repo "dist/md_split-$VERSION.flatpak" \
  com.james2doyle.MdSplit stable
```

On a machine without the GNOME 51 runtime and SDK, add
`--user --install-deps-from=flathub` to the `flatpak-builder` command.

The archive must have a top-level directory (`--prefix=...`). Flatpak strips
one leading path component when extracting; without it the source tree is
flattened and Meson fails with `first statement must be a call to project()`.

## Verify and install

```sh
export VERSION=1.0.0

flatpak install --user --reinstall "dist/md_split-$VERSION.flatpak"
flatpak info --user com.james2doyle.MdSplit
flatpak run com.james2doyle.MdSplit
```

`flatpak build-bundle` produces an unsigned local bundle. Flathub builds the
app from a manifest, so use a URL-backed archive (for example the GitHub tag
tarball) and let Flathub sign and build it. See [flathub.md](flathub.md) for
the submission checklist. For a local install test without touching your
normal Flatpak installation:

```sh
tmp=$(mktemp -d)
FLATPAK_USER_DIR="$tmp" flatpak install --user --noninteractive \
  "dist/md_split-$VERSION.flatpak"
FLATPAK_USER_DIR="$tmp" flatpak run com.james2doyle.MdSplit --help
rm -rf "$tmp"
```

## Automated GitHub release

`.github/workflows/release.yml` runs after the **CI** workflow succeeds for a
`v*` tag. It is deliberately separate from `ci.yml` so CI stays read-only and
releases cannot be published from pull requests or `main` pushes.

The workflow:

- checks out the tagged commit and rejects branch runs that merely start with
  `v`;
- creates the same prefixed source archive and pinned release manifest shown
  above;
- builds the Flatpak with `--buildtype=release`;
- uploads the source archive, release manifest, bundle, and `SHA256SUMS` to a
  GitHub Release;
- updates assets with `--clobber` if the release already exists, making
  re-runs safe.

The release is published, not drafted. Add `--draft` to the `gh release create`
command in the workflow if you prefer a manual approval step.

## Artifacts

`dist/` is gitignored. A successful release build produces:

- `dist/md-split-$VERSION.tar.gz` — tagged source archive
- `dist/com.james2doyle.MdSplit.release.json` — pinned release manifest
- `dist/md_split-$VERSION.flatpak` — installable bundle
- `dist/repo/` — local OSTree repository
