#!/usr/bin/env bash
# 把程序打包成独立的 macOS .app (用 py2app)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"

echo "==> 安装 / 更新 py2app ..."
"$PY" -m pip install --user --upgrade py2app >/dev/null

# 把 media-control(BSD-3) 整套内嵌进 .app, 这样用户无需再 brew 安装
echo "==> 内嵌 media-control ..."
MC="$(command -v media-control || true)"
VENDOR="$REPO_DIR/packaging/vendor/media-control"
if [[ -n "$MC" ]]; then
  MC_REAL="$("$PY" -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$MC")"
  MC_ROOT="$(cd "$(dirname "$MC_REAL")/.." && pwd)"   # .../Cellar/media-control/<ver>
  rm -rf "$VENDOR"; mkdir -p "$VENDOR"
  cp -R "$MC_ROOT/bin" "$MC_ROOT/lib" "$MC_ROOT/Frameworks" "$VENDOR/"
  cp "$MC_ROOT/README.md" "$VENDOR/MEDIA-CONTROL-README.md" 2>/dev/null || true
  echo "    已内嵌: $MC_ROOT"
else
  echo "    !! 未找到 media-control(brew install media-control), 本次不内嵌;"
  echo "       构建出的 .app 会退回到系统 PATH 里找 media-control。"
  rm -rf "$VENDOR"
fi

echo "==> 清理旧产物并构建 .app ..."
cd "$REPO_DIR/packaging"
rm -rf build dist
"$PY" setup_app.py py2app

APP="$REPO_DIR/packaging/dist/Podcast Desktop Lyrics.app"

# py2app 完成后再拷入 media-control: 保留其原始签名(py2app 的深度重签会
# 破坏 MediaRemoteAdapter.framework 对私有 API 的访问), 然后对外层非深度重签
if [[ -d "$VENDOR" ]]; then
  echo "==> 拷入 media-control 并重签外层 ..."
  rm -rf "$APP/Contents/Resources/media-control"
  cp -R "$VENDOR" "$APP/Contents/Resources/media-control"
  codesign --force --sign - "$APP" >/dev/null 2>&1 || true
fi

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
