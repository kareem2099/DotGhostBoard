#!/bin/bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Portable Tarball Builder (.tar.gz)
# ═══════════════════════════════════════════════════════

set -e

APP_NAME="dotghostboard"
VERSION=$(grep -oP 'version-v\K[0-9]+\.[0-9]+\.[0-9]+' README.md | head -1 || echo "1.5.5")
TAR_DIR="${APP_NAME}-${VERSION}-portable"
TAR_FILE="${APP_NAME}_${VERSION}_amd64.tar.gz"

echo "🧹 Cleaning previous tarball builds..."
rm -rf "$TAR_DIR" "$TAR_FILE"

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

echo "📦 Creating portable tarball structure..."
mkdir -p "$TAR_DIR"
cp -r dist/dotghostboard-app/* "$TAR_DIR/"
cp README.md "$TAR_DIR/" 2>/dev/null || true
cp LICENSE "$TAR_DIR/" 2>/dev/null || true

# Launcher script inside tarball
cat > "$TAR_DIR/dotghostboard.sh" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}:${PATH}"
export LD_LIBRARY_PATH="${HERE}:${LD_LIBRARY_PATH}"
export QT_QPA_PLATFORM=xcb
cd "${HERE}"
exec ./dotghostboard-app "$@"
EOF
chmod +x "$TAR_DIR/dotghostboard.sh"

echo "🔨 Creating .tar.gz archive..."
tar -czf "$TAR_FILE" "$TAR_DIR"

rm -rf "$TAR_DIR"

echo "✅ Portable tarball created successfully:"
echo "   $(pwd)/${TAR_FILE}"
