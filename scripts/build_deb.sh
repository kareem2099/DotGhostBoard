#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Local DEB Builder (v1.5.6 Nexus)
# ═══════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

source "$SCRIPT_DIR/lib/build_common.sh"

APP_NAME="dotghostboard"
VERSION="$(get_version)"
PKG_DIR="${APP_NAME}_${VERSION}_amd64"

echo "🧹 Cleaning previous deb package directory..."
rm -rf "$PKG_DIR" "${PKG_DIR}.deb"

# 1. Ensure executable binary exists or build it
BINARY="dist/dotghostboard-app/dotghostboard-app"
if [ ! -x "$BINARY" ]; then
    echo "📦 Compiled binary not found or not executable, invoking build_binary.sh..."
    bash "$SCRIPT_DIR/build_binary.sh"
fi

echo "🏗️ Creating Debian package structure..."
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/opt/dotghostboard"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"

# 2. Move program files to /opt
echo "📦 Copying files to /opt/dotghostboard..."
cp -a dist/dotghostboard-app/. "$PKG_DIR/opt/dotghostboard/"

# 3. Create launcher in /usr/bin
echo "🔗 Creating binary launcher..."
cat > "$PKG_DIR/usr/bin/dotghostboard" << 'EOF'
#!/bin/bash
# Run program from its path in /opt with any arguments passed through
exec /opt/dotghostboard/dotghostboard-app "$@"
EOF
chmod 755 "$PKG_DIR/usr/bin/dotghostboard"

# Create CLI companion in /usr/bin
echo "🔗 Creating CLI companion launcher..."
cp cli/dotghost.py "$PKG_DIR/usr/bin/dotghost"
chmod 755 "$PKG_DIR/usr/bin/dotghost"

# 4. Create desktop entry (menu)
echo "🖥️ Creating desktop entry..."
cat > "$PKG_DIR/usr/share/applications/dotghostboard.desktop" << EOF
[Desktop Entry]
Type=Application
Name=DotGhostBoard
Comment=Advanced clipboard manager for Linux — DotSuite
Exec=/usr/bin/dotghostboard
Icon=dotghostboard
Categories=Utility;
Terminal=false
StartupNotify=false
EOF

# 5. Copy icon
if [ -f "data/icons/icon_256.png" ]; then
    cp data/icons/icon_256.png "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/dotghostboard.png"
fi

# 6. Create control file (package metadata)
echo "📝 Generating DEBIAN/control file..."
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: ${APP_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3, libgl1, libxcb1, libxkbcommon0, libxcb-xinerama0, libxcb-cursor0
Recommends: pkexec | policykit-1
Maintainer: FreeRave <kareem209907@gmail.com>
Description: Advanced clipboard manager for Linux (Nexus v${VERSION})
 Built with PyQt6 and AES-256 encryption. Part of the DotSuite tools.
EOF

# 7. Normalize package permissions:
# remove group/other write bits while preserving executable bits
chmod -R go-w "$PKG_DIR"

# Explicit integration-file permissions
chmod 755 "$PKG_DIR/usr/bin/dotghostboard"
chmod 644 "$PKG_DIR/usr/share/applications/dotghostboard.desktop"

# Debian maintainer scripts, if present
if [ -d "$PKG_DIR/DEBIAN" ]; then
    chmod 755 "$PKG_DIR/DEBIAN"

    for script in preinst postinst prerm postrm; do
        if [ -f "$PKG_DIR/DEBIAN/$script" ]; then
            chmod 755 "$PKG_DIR/DEBIAN/$script"
        fi
    done

    if [ -f "$PKG_DIR/DEBIAN/control" ]; then
        chmod 644 "$PKG_DIR/DEBIAN/control"
    fi
fi

# 8. Build final package
echo "🔨 Packaging .deb file..."
fakeroot dpkg-deb --build "$PKG_DIR"

# Cleanup temporary package directory
rm -rf "$PKG_DIR"

echo ""
echo "✅ Done! DEB package created successfully:"
echo "   $(pwd)/${PKG_DIR}.deb"
echo ""
echo "To install it, run:"
echo "   sudo apt install ./$(basename "${PKG_DIR}.deb")"