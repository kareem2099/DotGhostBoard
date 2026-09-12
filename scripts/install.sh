#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
#  DotGhostBoard — install.sh
#  Configures:
#    1. Global shortcuts:
#       Ctrl+Alt+V     → Toggle Dashboard
#       Ctrl+Alt+Space → Spotlight
#    2. Autostart on graphical login
#    3. Desktop launcher
#    4. dotghost CLI companion
# ═══════════════════════════════════════════════════════════

set -euo pipefail

# ── Paths ─────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/venv/bin/python3"
MAIN="$PROJECT_DIR/main.py"
ICON="$PROJECT_DIR/data/icons/icon_256.png"

DESKTOP_DIR="$HOME/.local/share/applications"

# ── Check if venv exists ────────────────────────────────────
if [ ! -f "$PYTHON" ]; then
    echo "⚠  venv not found at $PYTHON"
    echo "   Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "👻 Installing DotGhostBoard..."
echo "   Project: $PROJECT_DIR"

# ── Create icon if not exists ──────────────────────────
if [ ! -f "$ICON" ]; then
    echo "Generating icon..."
    "$PYTHON" "$PROJECT_DIR/scripts/generate_icon.py"
fi

# ─────────────────────────────────────────────────────────
# 1. Keyboard Shortcuts (Dashboard & Spotlight)
# ─────────────────────────────────────────────────────────
echo "⌨  Setting up Global Shortcuts..."
if "$PYTHON" "$PROJECT_DIR/scripts/setup_shortcuts.py"; then
    echo "   ✓ Global shortcuts configured"
else
    echo "   ⚠ Could not configure global shortcuts automatically."
    echo "     You can configure them later from:"
    echo "     DotGhostBoard → Settings → General → Global Hotkeys"
fi

# ─────────────────────────────────────────────────────────
# 2. Autostart on graphical login (Delegated to core.autostart)
# ─────────────────────────────────────────────────────────
echo "🚀 Setting up autostart..."
"$PYTHON" "$PROJECT_DIR/scripts/setup_autostart.py"
echo "   ✓ Autostart configured through core.autostart"

# ─────────────────────────────────────────────────────────
# 3. .desktop file (App Launcher)
# ─────────────────────────────────────────────────────────
echo "🖥️ Creating app launcher entry..."

mkdir -p "$DESKTOP_DIR"
rm -f "$DESKTOP_DIR/DotGhostBoard.desktop"

cat > "$DESKTOP_DIR/dotghostboard.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=DotGhostBoard
GenericName=Clipboard Manager
Comment=Advanced clipboard manager — DotSuite
Exec=$PYTHON $MAIN
Icon=$ICON
Categories=Utility;
Keywords=clipboard;copy;paste;pin;ghost;dotsuite;
StartupNotify=false
Terminal=false
EOF

# Update desktop database
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null && \
        echo "   ✓ Desktop database updated"
fi

echo "   ✓ App launcher entry created: $DESKTOP_DIR/dotghostboard.desktop"

# ─────────────────────────────────────────────────────────
# 4. CLI Companion
# ─────────────────────────────────────────────────────────
echo "🔗 Setting up command-line tool (dotghost)..."

mkdir -p "$HOME/.local/bin"
CLI_SCRIPT="$PROJECT_DIR/cli/dotghost.py"
SYMLINK_PATH="$HOME/.local/bin/dotghost"

if [ -f "$CLI_SCRIPT" ]; then
    chmod +x "$CLI_SCRIPT"
    ln -sf "$CLI_SCRIPT" "$SYMLINK_PATH"
    echo "   ✓ Created dotghost symlink in $HOME/.local/bin"
else
    echo "   ⚠ Could not find $CLI_SCRIPT"
fi

# ─────────────────────────────────────────────────────────
# Done!
# ─────────────────────────────────────────────────────────
echo ""
echo " DotGhostBoard installed successfully!"
echo ""
echo "   Dashboard : Ctrl + Alt + V"
echo "   Spotlight : Ctrl + Alt + Space"
echo "   Autostart : on login"
echo "   App menu  : search 'DotGhostBoard'"
echo ""
echo "   Run now   : $PYTHON $MAIN &"
echo ""