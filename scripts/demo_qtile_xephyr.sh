#!/usr/bin/env bash
# scripts/demo_qtile_xephyr.sh
# ─────────────────────────────
# Interactive visual tester for DotGhostBoard under Qtile using Xephyr.
#
# Usage:
#   ./scripts/demo_qtile_xephyr.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

XEPHYR_DISP=":2"
XEPHYR_RES="1280x800"
SOCKET_PATH="/tmp/qtile_demo_socket"
DEMO_HOME="/tmp/dotghost_demo_home"
CONFIG_PATH="$REPO_ROOT/tests/fixtures/qtile_test_config.py"

# 1. Clean previous state
rm -f "$SOCKET_PATH"
rm -rf "$DEMO_HOME"
mkdir -p "$DEMO_HOME"

echo "============================================================"
echo " Starting Qtile + DotGhostBoard interactive Xephyr demo"
echo " Target nested display: $XEPHYR_DISP ($XEPHYR_RES)"
echo " Isolated demo home:    $DEMO_HOME"
echo "============================================================"

# 2. Launch Xephyr
Xephyr "$XEPHYR_DISP" -screen "$XEPHYR_RES" -ac -br &
XEPHYR_PID=$!
sleep 0.8

APP_PID=""
QTILE_PID=""

# Trap cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up Xephyr demo..."
    [ -n "$APP_PID" ] && kill "$APP_PID" 2>/dev/null || true
    [ -n "$QTILE_PID" ] && kill "$QTILE_PID" 2>/dev/null || true
    [ -n "$XEPHYR_PID" ] && kill "$XEPHYR_PID" 2>/dev/null || true
    rm -f "$SOCKET_PATH"
    rm -rf "$DEMO_HOME"
    echo "Done."
}
trap cleanup EXIT INT TERM

# 3. Launch Qtile inside Xephyr
DISPLAY="$XEPHYR_DISP" QT_QPA_PLATFORM=xcb qtile start -b x11 -s "$SOCKET_PATH" -c "$CONFIG_PATH" &
QTILE_PID=$!
sleep 1.2

# 4. Launch DotGhostBoard inside Xephyr with isolated profile
echo "Starting DotGhostBoard inside Qtile..."
DISPLAY="$XEPHYR_DISP" DOTGHOST_HOME="$DEMO_HOME" QT_QPA_PLATFORM=xcb python3 "$REPO_ROOT/main.py" &
APP_PID=$!

echo ""
echo "------------------------------------------------------------"
echo "DEMO READY! Xephyr window is now open on your screen."
echo ""
echo "Test steps (run these in another terminal):"
echo " 1. See DotGhostBoard active on Group 1 with the top bar showing [1]."
echo " 2. Switch Qtile to Group 2 (will show clean empty Group 2 with [2] highlighted):"
echo "      ./scripts/demo_switch_group2.sh"
echo " 3. Summon / toggle DotGhostBoard to Group 2:"
echo "      ./scripts/demo_toggle.sh"
echo "    -> Notice DotGhostBoard instantly jumps to Group 2 and focuses!"
echo " 4. Test Spotlight search overlay:"
echo "      ./scripts/demo_spotlight.sh"
echo "------------------------------------------------------------"
echo "Press Ctrl+C in this terminal or close the Xephyr window to exit."

wait "$XEPHYR_PID"
