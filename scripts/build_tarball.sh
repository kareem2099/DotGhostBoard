#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Portable Tarball Builder (.tar.gz)
# ═══════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

source "$SCRIPT_DIR/lib/build_common.sh"

APP_NAME="dotghostboard"
VERSION="$(get_version)"
TAR_DIR="${APP_NAME}-${VERSION}-portable"
TAR_FILE="${APP_NAME}_${VERSION}_amd64.tar.gz"

echo "🧹 Cleaning previous tarball builds..."
rm -rf "$TAR_DIR" "$TAR_FILE"

# Ensure executable binary exists or build it
BINARY="dist/dotghostboard-app/dotghostboard-app"
if [ ! -x "$BINARY" ]; then
    echo "📦 Compiled binary not found or not executable, invoking build_binary.sh..."
    bash "$SCRIPT_DIR/build_binary.sh"
fi

echo "📦 Creating portable tarball structure..."
mkdir -p "$TAR_DIR"
cp -a dist/dotghostboard-app/. "$TAR_DIR/"
cp README.md "$TAR_DIR/" 2>/dev/null || true
cp LICENSE "$TAR_DIR/" 2>/dev/null || true
if [ -f "data/icons/icon_256.png" ]; then
    cp data/icons/icon_256.png "$TAR_DIR/dotghostboard.png"
fi

# Launcher script inside tarball (clean, self-contained execution)
cat > "$TAR_DIR/dotghostboard.sh" << 'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
cd "$HERE"
exec ./dotghostboard-app "$@"
EOF
chmod 755 "$TAR_DIR/dotghostboard.sh"

echo "🔨 Creating .tar.gz archive..."
tar -czf "$TAR_FILE" "$TAR_DIR"

rm -rf "$TAR_DIR"

echo "✅ Portable tarball created successfully:"
echo "   $(pwd)/${TAR_FILE}"
