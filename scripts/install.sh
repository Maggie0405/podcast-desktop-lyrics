#!/usr/bin/env bash
# 一键安装: 装依赖 + 安装 Python 包 + 注册开机自启(LaunchAgent)
set -euo pipefail

LABEL="com.podcast-desktop-lyrics.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Podcast Desktop Lyrics 安装"

# 1) 系统检查
if [[ "$(uname)" != "Darwin" ]]; then
  echo "!! 仅支持 macOS"; exit 1
fi

# 2) media-control(识别正在播放哪一集)
if ! command -v media-control >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "==> 安装 media-control ..."
    brew install media-control
  else
    echo "!! 未找到 media-control, 且未安装 Homebrew。"
    echo "   请先装 Homebrew (https://brew.sh) 后重跑, 或手动: brew install media-control"
    exit 1
  fi
fi

# 3) 安装 Python 包(含 pyobjc 依赖)
PY="$(command -v python3)"
echo "==> 用 $PY 安装 Python 包 ..."
"$PY" -m pip install --user "$REPO_DIR"

# 4) 注册开机自启
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>-m</string>
    <string>podcast_desktop_lyrics</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StandardOutPath</key><string>/tmp/podcast-lyrics.log</string>
  <key>StandardErrorPath</key><string>/tmp/podcast-lyrics.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo
echo "==> 完成! 已注册开机自启并启动 (日志: /tmp/podcast-lyrics.log)"
echo
echo "最后一步 —— 启用与播客 App 一致的『实时』精度:"
echo "  系统设置 › 隐私与安全性 › 辅助功能, 添加并勾选:"
echo "      $PY"
echo "  然后重启本程序:  launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo
echo "  (不授权也能用, 但只是按播放进度顺延的估算精度)"
