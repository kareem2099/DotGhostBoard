#!/usr/bin/env bash
# Switch Qtile inside Xephyr demo to Group 2
qtile cmd-obj -s /tmp/qtile_demo_socket -o group 2 -f toscreen
echo "Switched Qtile to Group 2!"
