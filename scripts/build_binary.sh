#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════
# DotGhostBoard — Unified PyInstaller Binary Builder
# Compiles core application into dist/dotghostboard-app/
# ═══════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

source "$SCRIPT_DIR/lib/build_common.sh"

VERSION="$(get_version)"
PYTHON_BIN="$(get_python)"

echo "========================================================"
echo "👻 DotGhostBoard v${VERSION} — Compiling Native Binary"
echo "   Python: $PYTHON_BIN"
echo "========================================================"

# Sanity check build environment
if ! "$PYTHON_BIN" -c 'import PyInstaller, PyQt6, cryptography' >/dev/null 2>&1; then
    echo "❌ Incomplete build environment in $PYTHON_BIN." >&2
    echo "Run:" >&2
    echo "   $PYTHON_BIN -m pip install -r requirements-dev.txt pyinstaller" >&2
    exit 1
fi

echo "🧹 Cleaning previous compilation outputs..."
rm -rf build dist

if [ ! -f "data/icons/icon_256.png" ] && [ -f "scripts/generate_icon.py" ]; then
    echo "🎨 Generating icons..."
    "$PYTHON_BIN" scripts/generate_icon.py
fi

echo "🚀 Compiling with PyInstaller..."
"$PYTHON_BIN" -m PyInstaller \
    --noconsole \
    --onedir \
    --add-data "data:data" \
    --add-data "ui/ghost.qss:ui" \
    --hidden-import "PyQt6.sip" \
    --hidden-import "cryptography" \
    --collect-all "cryptography" \
    --name dotghostboard-app \
    main.py

BINARY="dist/dotghostboard-app/dotghostboard-app"
if [ ! -x "$BINARY" ]; then
    echo "❌ Expected executable was not produced or is not executable:" >&2
    echo "   $BINARY" >&2
    exit 1
fi

echo "✅ Binary compiled successfully in: $(pwd)/$BINARY"
