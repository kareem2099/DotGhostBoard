#!/bin/bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Arch Linux Package Builder (.pkg.tar.zst)
# ═══════════════════════════════════════════════════════

set -e

APP_NAME="dotghostboard"
VERSION=$(grep -oP 'version-v\K[0-9]+\.[0-9]+\.[0-9]+' README.md | head -1 || echo "1.5.5")
ARCH="x86_64"
REL="1"
PKG_DIR="${APP_NAME}-${VERSION}-${REL}-${ARCH}"
PKG_FILE="${APP_NAME}-${VERSION}-${REL}-${ARCH}.pkg.tar.zst"

echo "🧹 Cleaning previous Arch builds..."
rm -rf "$PKG_DIR" "$PKG_FILE" PKGBUILD

if [ ! -d "dist/dotghostboard-app" ]; then
    echo "🚀 Compiling with PyInstaller..."
    pip install PyQt6 Pillow cryptography pyinstaller --break-system-packages --quiet || true
    pyinstaller --noconsole --onedir \
        --add-data "data:data" \
        --add-data "ui/ghost.qss:ui" \
        --hidden-import "PyQt6.sip" \
        --hidden-import "cryptography" \
        --collect-all "cryptography" \
        --name dotghostboard-app main.py
fi

echo "🏗️ Creating Arch Linux package directory structure..."
mkdir -p "$PKG_DIR/opt/dotghostboard"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"

# Copy binary files
cp -r dist/dotghostboard-app/* "$PKG_DIR/opt/dotghostboard/"

# Create launcher binary in /usr/bin
cat > "$PKG_DIR/usr/bin/dotghostboard" << 'EOF'
#!/bin/bash
/opt/dotghostboard/dotghostboard-app "$@"
EOF
chmod +x "$PKG_DIR/usr/bin/dotghostboard"

# Create Desktop entry
cat > "$PKG_DIR/usr/share/applications/dotghostboard.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=DotGhostBoard
Comment=Advanced encrypted clipboard manager for Linux — DotSuite
Exec=/usr/bin/dotghostboard
Icon=dotghostboard
Categories=Utility;
Terminal=false
StartupNotify=false
EOF

# Copy Icon
if [ -f "data/icons/icon_256.png" ]; then
    cp data/icons/icon_256.png "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/dotghostboard.png"
fi

# Generate Arch .PKGINFO metadata
BUILDDATE=$(date -u +%s)
cat > "$PKG_DIR/.PKGINFO" << EOF
pkgname = ${APP_NAME}
pkgver = ${VERSION}-${REL}
pkgdesc = Advanced encrypted clipboard manager for Linux (Nexus v${VERSION})
url = https://github.com/kareem2099/DotGhostBoard
builddate = ${BUILDDATE}
packager = FreeRave <kareem209907@gmail.com>
size = $(du -sk "$PKG_DIR" | cut -f1)000
arch = ${ARCH}
license = Apache-2.0
depend = libxkbcommon
depend = libglvnd
depend = hicolor-icon-theme
EOF

# Generate Arch .BUILDINFO metadata
cat > "$PKG_DIR/.BUILDINFO" << EOF
format = 2
pkgname = ${APP_NAME}
pkgver = ${VERSION}-${REL}
pkgarch = ${ARCH}
pkgbuild_sha256sum = 0000000000000000000000000000000000000000000000000000000000000000
packager = FreeRave <kareem209907@gmail.com>
builddate = ${BUILDDATE}
builddir = /tmp
buildenv = check
buildenv = sign
options = !strip
options = docs
options = !libtool
options = !staticlibs
options = empty
options = zipman
options = purge
options = !optipng
options = !upx
options = !debug
options = lto
EOF

# Generate AUR PKGBUILD file for reference
cat > PKGBUILD << EOF
# Maintainer: FreeRave <kareem209907@gmail.com>
pkgname=${APP_NAME}
pkgver=${VERSION}
pkgrel=${REL}
pkgdesc="Advanced encrypted clipboard manager for Linux — DotSuite"
arch=('x86_64')
url="https://github.com/kareem2099/DotGhostBoard"
license=('Apache-2.0')
depends=('libxkbcommon' 'libglvnd' 'hicolor-icon-theme')
source=("https://github.com/kareem2099/DotGhostBoard/releases/download/v\${pkgver}/dotghostboard_\${pkgver}_amd64.tar.gz")
sha256sums=('SKIP')

package() {
    mkdir -p "\${pkgdir}/opt/dotghostboard"
    mkdir -p "\${pkgdir}/usr/bin"
    cp -r "\${srcdir}/dotghostboard-\${pkgver}-portable/"* "\${pkgdir}/opt/dotghostboard/"
    ln -s /opt/dotghostboard/dotghostboard.sh "\${pkgdir}/usr/bin/dotghostboard"
}
EOF

echo "🔨 Creating .pkg.tar.zst package..."
if command -v zstd >/dev/null 2>&1; then
    (cd "$PKG_DIR" && tar --zstd -cf "../$PKG_FILE" .PKGINFO .BUILDINFO opt usr)
else
    echo "⚠️ zstd not found, creating .pkg.tar.gz fallback..."
    PKG_FILE="${APP_NAME}-${VERSION}-${REL}-${ARCH}.pkg.tar.gz"
    (cd "$PKG_DIR" && tar -czf "../$PKG_FILE" .PKGINFO .BUILDINFO opt usr)
fi

rm -rf "$PKG_DIR"

echo "✅ Arch Linux package created successfully:"
echo "   $(pwd)/${PKG_FILE}"
