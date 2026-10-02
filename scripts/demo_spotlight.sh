#!/usr/bin/env bash
# Trigger spotlight on Qtile Xephyr demo
DISPLAY=:2 DOTGHOST_HOME=/tmp/dotghost_demo_home QT_QPA_PLATFORM=xcb python3 main.py --spotlight
echo "DotGhostBoard Spotlight summoned!"
