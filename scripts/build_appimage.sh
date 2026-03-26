#!/bin/bash
# ════════════════════════════════════════════
# DotGhostBoard — AppImage Builder (Docker Edition)
# ════════════════════════════════════════════

set -e

APP_NAME="DotGhostBoard"
VERSION=$(grep -oP "version-v\K[0-9]+\.[0-9]+\.[0-9]+" README.md | head -1 || echo "1.3.1")
ARCH="x86_64"
APPDIR="${APP_NAME}.AppDir"

# Detect if running inside Docker
if [ -f /.dockerenv ]; then
    echo "🐳 Running inside Docker container"
    PYTHON=python3.9
else
    PYTHON=python3
fi

echo "🚀 Compiling Python code with PyInstaller..."
# Generate icon first
$PYTHON scripts/generate_icon.py

# Build with PyInstaller
pyinstaller --noconsole --onedir --add-data "data:data" \
    --hidden-import "PyQt6.sip" --name dotghostboard main.py

echo "🔨 Building ${APP_NAME} v${VERSION} AppImage structure..."

# ── Clean previous build ──
rm -rf "$APPDIR" "${APP_NAME}-${VERSION}-${ARCH}.AppImage"

# ── Create AppDir structure ──
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# ── Copy Compiled App ──
# Copy PyInstaller output files (not raw Python files)
cp -r dist/dotghostboard/* "$APPDIR/usr/bin/"

# ── Create launcher script (AppRun) ──
cat > "$APPDIR/AppRun" << 'LAUNCHER'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export QT_QPA_PLATFORM=xcb
# Suppress noisy debug messages
export QT_LOGGING_RULES="*.debug=false;qt.dbus.*=false"

cd "${HERE}/usr/bin"
exec ./dotghostboard "$@"
LAUNCHER
chmod +x "$APPDIR/AppRun"

# ── Desktop entry ──
cat > "$APPDIR/dotghostboard.desktop" << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=DotGhostBoard
GenericName=Clipboard Manager
Comment=Advanced clipboard manager for Linux — DotSuite
Exec=dotghostboard
Icon=dotghostboard
Categories=Utility;
Keywords=clipboard;copy;paste;pin;ghost;dotsuite;
StartupNotify=false
Terminal=false
DESKTOP

cp "$APPDIR/dotghostboard.desktop" "$APPDIR/usr/share/applications/"

# ── Icon ──
cp data/icons/icon_256.png "$APPDIR/dotghostboard.png"
cp data/icons/icon_256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/dotghostboard.png"

# ── AppStream Metadata ──
mkdir -p "$APPDIR/usr/share/metainfo"
cp data/dotghostboard.appdata.xml "$APPDIR/usr/share/metainfo/com.github.kareem2099.dotghostboard.metainfo.xml"

# ── Download appimagetool if not present ──
if [ ! -f appimagetool ]; then
    echo "📥 Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage" -O appimagetool
    chmod +x appimagetool
fi

# ── Build AppImage ──
echo "📦 Packaging AppImage..."
export ARCH=x86_64
./appimagetool --appimage-extract-and-run "$APPDIR" "${APP_NAME}-${VERSION}-${ARCH}.AppImage"

# ── Cleanup ──
rm -rf "$APPDIR"
rm -rf build dist dotghostboard.spec # Clean up PyInstaller files

echo ""
echo "✅ Done! AppImage created successfully:"
echo "   ${APP_NAME}-${VERSION}-${ARCH}.AppImage"