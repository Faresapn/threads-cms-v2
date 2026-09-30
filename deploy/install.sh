#!/bin/bash
# install.sh — pasang autostart CMS v2 via launchd (macOS)
# Server nyala sendiri pas login + auto-restart kalau mati (KeepAlive).
set -e
UID_NUM=$(id -u)
PLIST=com.branko.threads-cms-v2.plist
DEST=~/Library/LaunchAgents/$PLIST

cp "$(dirname "$0")/$PLIST" "$DEST"
launchctl bootout gui/$UID_NUM/com.branko.threads-cms-v2 2>/dev/null || true
launchctl bootstrap gui/$UID_NUM "$DEST"
launchctl enable gui/$UID_NUM/com.branko.threads-cms-v2
echo "✓ CMS v2 autostart terpasang. http://127.0.0.1:8455"
echo "  cek: launchctl list | grep threads-cms-v2"
echo "  stop: launchctl bootout gui/$UID_NUM/com.branko.threads-cms-v2"
