#!/usr/bin/env bash
# 把程序打包成独立的 macOS .app (用 py2app)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"

echo "==> 安装 / 更新 py2app ..."
"$PY" -m pip install --user --upgrade py2app >/dev/null

echo "==> 清理旧产物并构建 .app ..."
cd "$REPO_DIR/packaging"
rm -rf build dist
"$PY" setup_app.py py2app

APP="$REPO_DIR/packaging/dist/Podcast Desktop Lyrics.app"
echo
echo "==> 完成: $APP"
echo
echo "安装 & 授权:"
echo "  1) 把该 .app 拖进 /Applications"
echo "  2) 首次打开若提示无法验证开发者: 右键 > 打开, 或到"
echo "     系统设置 > 隐私与安全性 点『仍要打开』"
echo "  3) 系统设置 > 隐私与安全性 > 辅助功能, 把 Podcast Desktop Lyrics 打勾"
echo "     (启用与播客 App 一致的实时精度)"
