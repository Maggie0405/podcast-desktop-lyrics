#!/usr/bin/env bash
# 一键卸载: 停止运行 + 移除开机自启 + 卸载 Python 包
set -euo pipefail

LABEL="com.podcast-desktop-lyrics.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "==> 卸载 Podcast Desktop Lyrics"

launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
pkill -f "podcast_desktop_lyrics" 2>/dev/null || true

python3 -m pip uninstall -y podcast-desktop-lyrics 2>/dev/null || true

echo "==> 已停止、移除开机自启并卸载 Python 包。"
echo "   如不再需要, 可自行:"
echo "     brew uninstall media-control"
echo "   并在 系统设置>隐私与安全性>辅助功能 里移除 python3。"
