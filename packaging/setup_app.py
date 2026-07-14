"""
py2app 打包配置 —— 把程序打成 macOS 独立 .app。

用法(推荐直接跑 scripts/build_app.sh):
    cd packaging
    python3 setup_app.py py2app
产物: packaging/dist/Podcast Desktop Lyrics.app
"""
import os
import sys

# 让 py2app 能 import 到仓库根目录的 podcast_desktop_lyrics 包
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from setuptools import setup

APP = ["entry.py"]
OPTIONS = {
    "argv_emulation": False,
    "packages": ["podcast_desktop_lyrics"],
    # AppKit/Foundation 由 py2app 的 pyobjc recipe 处理; ApplicationServices(AX)
    # 是惰性导入, 显式列出以确保打进 bundle
    "includes": ["ApplicationServices"],
    "plist": {
        "CFBundleName": "Podcast Desktop Lyrics",
        "CFBundleDisplayName": "Podcast Desktop Lyrics",
        "CFBundleIdentifier": "com.maggie0405.podcast-desktop-lyrics",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        # 后台悬浮工具: 不占 Dock、不出菜单栏, 用悬浮窗上的 ✕ 退出
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "MIT (c) 2026 Maggie0405",
    },
}

setup(
    app=APP,
    name="Podcast Desktop Lyrics",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
