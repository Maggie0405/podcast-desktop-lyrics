#!/usr/bin/env bash
# 把已构建的 .app 打成可下载的 .dmg (拖拽到 Applications 即可安装)
# 需先运行 scripts/build_app.sh 生成 .app
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:-0.1.0}"
APP="$REPO_DIR/packaging/dist/Podcast Desktop Lyrics.app"
DMG="$REPO_DIR/packaging/dist/PodcastDesktopLyrics-$VERSION.dmg"

if [[ ! -d "$APP" ]]; then
  echo "!! 未找到 $APP"
  echo "   请先运行: bash scripts/build_app.sh"
  exit 1
fi

STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"     # 方便拖拽安装

rm -f "$DMG"
hdiutil create -volname "Podcast Desktop Lyrics" \
  -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

echo
echo "==> 完成: $DMG"
