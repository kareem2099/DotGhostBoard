#!/bin/bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Local DEB Builder (v1.5.0 Nexus)
# ═══════════════════════════════════════════════════════

set -e

APP_NAME="dotghostboard"
# Get version from README or default to 1.4.1
VERSION=$(grep -oP 'version-v\K[0-9]+\.[0-9]+\.[0-9]+' README.md | head -1 || echo "1.5.2")
PKG_DIR="${APP_NAME}_${VERSION}_amd64"

echo "🧹 Cleaning previous builds..."
rm -rf build dist "$PKG_DIR" "${PKG_DIR}.deb"

echo "🚀 Compiling with PyInstaller..."
# Bundle all libraries and name the executable dotghostboard-app
pip install PyQt6 Pillow cryptography pyinstaller --quiet
pyinstaller --noconsole --onedir \
    --add-data "data:data" \
    --add-data "ui/ghost.qss:ui" \
    --hidden-import "PyQt6.sip" \
    --hidden-import "cryptography" \
    --collect-all "cryptography" \
    --name dotghostboard-app main.py

echo "🏗️ Creating Debian package structure..."
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/opt/dotghostboard"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/256x256/apps"

# 1. Move program files to /opt
echo "📦 Copying files to /opt/dotghostboard..."
cp -r dist/dotghostboard-app/* "$PKG_DIR/opt/dotghostboard/"

# 2. Create launcher in /usr/bin
echo "🔗 Creating binary launcher..."
cat > "$PKG_DIR/usr/bin/dotghostboard" << 'EOF'
#!/bin/bash
# Run program from its path in /opt with any arguments passed through
/opt/dotghostboard/dotghostboard-app "$@"
EOF
chmod +x "$PKG_DIR/usr/bin/dotghostboard"

# 3. Create desktop entry (menu)
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

# 4. Copy icon
cp data/icons/icon_256.png "$PKG_DIR/usr/share/icons/hicolor/256x256/apps/dotghostboard.png"

# 5. Create control file (package metadata)
echo "📝 Generating DEBIAN/control file..."
cat > "$PKG_DIR/DEBIAN/control" << EOF
Package: ${APP_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Depends: libgl1, libxcb1, libxkbcommon0, libxcb-xinerama0, libxcb-cursor0, python3-cryptography
Maintainer: FreeRave <kareem209907@gmail.com>
Description: Advanced clipboard manager for Linux (Eclipse v${VERSION})
 Built with PyQt6 and AES-256 encryption. Part of the DotSuite tools.
EOF

# 6. Build final package
echo "🔨 Packaging .deb file..."
fakeroot dpkg-deb --build "$PKG_DIR"

# Cleanup
rm -rf "$PKG_DIR"
rm -rf build dist

echo ""
echo "✅ Done! DEB package created successfully:"
echo "   $(pwd)/${PKG_DIR}.deb"
echo ""
echo "To install it, run:"
echo "   sudo dpkg -i ${PKG_DIR}.deb"