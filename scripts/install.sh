#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
#  DotGhostBoard — install.sh
#  Automatically does 3 things:
#    1. Keyboard shortcut  (Ctrl+Alt+V)  on XFCE
#    2. Autostart on boot  (~/.config/autostart/)
#    3. .desktop file      (appears in App Launcher)
# ═══════════════════════════════════════════════════════════

set -e

# ── Paths ─────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT_DIR/venv/bin/python3"
MAIN="$PROJECT_DIR/main.py"
ICON="$PROJECT_DIR/data/icons/icon.png"

AUTOSTART_DIR="$HOME/.config/autostart"
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
# 1. Keyboard Shortcut on XFCE
# ─────────────────────────────────────────────────────────
echo "⌨  Setting up Ctrl+Alt+V shortcut..."

COMMAND="$PYTHON $MAIN"

# Using xfconf-query (official method for XFCE)
if command -v xfconf-query &>/dev/null; then
    xfconf-query \
        --channel xfce4-keyboard-shortcuts \
        --property "/commands/custom/<Primary><Alt>v" \
        --create \
        --type string \
        --set "$COMMAND" 2>/dev/null && \
        echo "   ✓ Shortcut added via xfconf-query" || {
        echo "   ⚠ Could not set shortcut automatically."
        echo ""
        echo "   ➜ Add it manually:"
        echo "     Settings → Keyboard → Application Shortcuts → Add"
        echo "     Command : $COMMAND"
        echo "     Shortcut: Ctrl + Alt + V"
        echo ""
    }
else
    echo "   ⚠ xfconf-query not found — add the shortcut manually:"
    echo ""
    echo "   ➜ Settings → Keyboard → Application Shortcuts → Add"
    echo "     Command : $COMMAND"
    echo "     Shortcut: Ctrl + Alt + V"
    echo ""
fi

# ─────────────────────────────────────────────────────────
# 2. Autostart on Boot
# ─────────────────────────────────────────────────────────
echo "🚀 Setting up autostart..."

mkdir -p "$AUTOSTART_DIR"

cat > "$AUTOSTART_DIR/DotGhostBoard.desktop" << EOF
[Desktop Entry]
Type=Application
Name=DotGhostBoard
Comment=Clipboard Manager — DotSuite
Exec=$PYTHON $MAIN
Icon=$ICON
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-XFCE-Autostart-Override=true
StartupNotify=false
Terminal=false
EOF

echo "   ✓ Autostart entry created: $AUTOSTART_DIR/DotGhostBoard.desktop"

# ─────────────────────────────────────────────────────────
# 3. .desktop file (App Launcher)
# ─────────────────────────────────────────────────────────
echo " Creating app launcher entry..."

mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_DIR/DotGhostBoard.desktop" << EOF
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

echo "   ✓ App launcher entry created"

# ─────────────────────────────────────────────────────────
# Done!
# ─────────────────────────────────────────────────────────
echo ""
echo " DotGhostBoard installed successfully!"
echo ""
echo "   Shortcut  : Ctrl + Alt + V"
echo "   Autostart : on login"
echo "   App menu  : search 'DotGhostBoard'"
echo ""
echo "   Run now   : $PYTHON $MAIN &"
echo ""