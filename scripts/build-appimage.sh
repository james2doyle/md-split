#!/bin/sh
# Build the x86_64 AppImage inside a pinned Ubuntu container.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname "$SCRIPT_DIR")
cd "$ROOT"

if [ "${MD_SPLIT_APPIMAGE_BUILD:-}" != "1" ]; then
    PROJECT_VERSION=$(python3 - <<'PY'
import tomllib
from pathlib import Path
print(tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"])
PY
)
    VERSION=${VERSION:-$PROJECT_VERSION}
    if [ "$VERSION" != "$PROJECT_VERSION" ]; then
        echo "VERSION=$VERSION does not match pyproject.toml ($PROJECT_VERSION)" >&2
        exit 1
    fi
    APPIMAGE_VERSION=$VERSION
    export APPIMAGE_VERSION

    for engine in podman docker; do
        if command -v "$engine" >/dev/null 2>&1; then
            exec "$engine" run --rm \
                --security-opt label=disable \
                -v "$ROOT:/src:Z" \
                -w /src \
                -e APPIMAGE_VERSION \
                -e MD_SPLIT_APPIMAGE_BUILD=1 \
                ubuntu:26.04 \
                ./scripts/build-appimage.sh
        fi
    done
    echo "podman or docker is required to build the AppImage" >&2
    exit 1
fi

VERSION=${APPIMAGE_VERSION:?APPIMAGE_VERSION is required inside the build container}

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    appstream \
    blueprint-compiler \
    ca-certificates \
    curl \
    desktop-file-utils \
    fakeroot \
    gettext \
    git \
    libadwaita-1-dev \
    libglib2.0-bin \
    libglib2.0-dev \
    libgtk-4-dev \
    libgtksourceview-5-dev \
    meson \
    ninja-build \
    patchelf \
    python3 \
    python3-venv \
    squashfs-tools \
    strace \
    xz-utils \
    zsync \
    >/dev/null

PROJECT_VERSION=$(python3 - <<'PY'
import tomllib
from pathlib import Path
print(tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"])
PY
)
if [ "$VERSION" != "$PROJECT_VERSION" ]; then
    echo "APPIMAGE_VERSION=$VERSION does not match pyproject.toml ($PROJECT_VERSION)" >&2
    exit 1
fi

# appimage-builder checks for apt-key even though it writes keys directly to
# its private apt configuration. Ubuntu 26.04 no longer ships the wrapper.
if ! command -v apt-key >/dev/null 2>&1; then
    cat > /usr/local/bin/apt-key <<'APTKEY'
#!/bin/sh
exit 0
APTKEY
    chmod 0755 /usr/local/bin/apt-key
fi

if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
fi
export PATH="$HOME/.local/bin:$PATH"
if ! command -v appimage-builder >/dev/null 2>&1; then
    uv tool install --python 3.12 --from appimage-builder==1.1.0 \
        appimage-builder >/dev/null
fi

# appimage-builder 1.1.0 parses apt versions with PEP 440, which rejects
# Ubuntu's "1.23.7ubuntu1" form. Fall back to a plain comparison for those.
TOOL_DIR=$(uv tool dir)
PACKAGE_PY=$(find "$TOOL_DIR/appimage-builder" \
    -path '*appimagebuilder/modules/deploy/apt/package.py' \
    -print -quit)
python3 - "$PACKAGE_PY" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = """    def __gt__(self, other):
        if isinstance(other, Package):
            return version.parse(self.version) > version.parse(other.version)
"""
new = """    def __gt__(self, other):
        if isinstance(other, Package):
            try:
                return (
                    version.parse(self.version) > version.parse(other.version)
                )
            except version.InvalidVersion:
                return self.version > other.version
"""
if old not in text:
    raise SystemExit("appimage-builder apt version patch did not apply")
path.write_text(text.replace(old, new))
PY

if ! command -v appimagetool >/dev/null 2>&1; then
    curl -Lsf \
        -o /opt/appimagetool \
        https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod 0755 /opt/appimagetool
    (cd /opt && ./appimagetool --appimage-extract >/dev/null)
    ln -sf /opt/squashfs-root/AppRun /usr/local/bin/appimagetool
fi

rm -rf packaging/appimage/AppDir packaging/appimage/md_split-*.AppImage
(
    cd packaging/appimage
    appimage-builder --recipe AppImageBuilder.yml --skip-tests
)

mkdir -p dist
APPIMAGE="packaging/appimage/md_split-${VERSION}-x86_64.AppImage"
if [ ! -f "$APPIMAGE" ]; then
    echo "AppImage was not produced at $APPIMAGE" >&2
    exit 1
fi
mv "$APPIMAGE" "dist/md_split-${VERSION}-x86_64.AppImage"
chmod 0755 "dist/md_split-${VERSION}-x86_64.AppImage"
echo "Wrote dist/md_split-${VERSION}-x86_64.AppImage"
