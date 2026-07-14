#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成应用图标: 深色圆角底 + 三行"歌词"(中间一行高亮) + 底部进度条。
用 pyobjc/AppKit 绘制(无需 PIL), 输出 icon.iconset/ 各尺寸 PNG,
再由 iconutil 打成 icon.icns(见 scripts/build_app.sh 或手动执行)。

用法:
    python3 make_icon.py            # 在当前目录生成 icon.iconset/ 和 icon.icns
"""
import os
import subprocess

from AppKit import (
    NSBezierPath, NSBitmapImageRep, NSColor, NSCompositingOperationSourceOver,
    NSGraphicsContext, NSImage, NSMakeRect, NSPNGFileType,
)

SIZE = 1024
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def draw_icon(size):
    img = NSImage.alloc().initWithSize_((size, size))
    img.lockFocus()
    s = size / 1024.0   # 缩放系数, 以 1024 为基准设计

    # 背景: 深灰黑圆角方块(macOS 图标风格, 留边距)
    margin = 100 * s
    rect = NSMakeRect(margin, margin, size - 2 * margin, size - 2 * margin)
    bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        rect, 185 * s, 185 * s)
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.11, 0.11, 0.13, 1.0).set()
    bg.fill()

    # 三行"歌词条": 上下两行暗淡, 中间一行白色高亮(更长更粗)
    def bar(y, w, h, color):
        x = (size - w) / 2
        p = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(x, y, w, h), h / 2, h / 2)
        color.set()
        p.fill()

    dim = NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.30)
    hot = NSColor.whiteColor()
    bar(680 * s, 420 * s, 56 * s, dim)               # 上一句(暗)
    bar(520 * s, 620 * s, 88 * s, hot)               # 当前句(亮, 粗)
    bar(392 * s, 360 * s, 56 * s, dim)               # 下一句(暗)

    # 底部进度条: 轨道 + 已播放段(紫色点缀, 呼应播客)
    track_w, track_h = 520 * s, 26 * s
    tx, ty = (size - track_w) / 2, 258 * s
    bar_track = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(tx, ty, track_w, track_h), track_h / 2, track_h / 2)
    NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.18).set()
    bar_track.fill()
    done_w = track_w * 0.62
    bar_done = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(tx, ty, done_w, track_h), track_h / 2, track_h / 2)
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.69, 0.32, 0.87, 1.0).set()
    bar_done.fill()
    # 进度点
    dot_r = 34 * s
    dot = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(tx + done_w - dot_r, ty + track_h / 2 - dot_r, dot_r * 2, dot_r * 2))
    NSColor.whiteColor().set()
    dot.fill()

    img.unlockFocus()
    return img


def save_png(img, size, path):
    img.lockFocus()
    rep = NSBitmapImageRep.alloc().initWithFocusedViewRect_(
        NSMakeRect(0, 0, size, size))
    img.unlockFocus()
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(
        path, True)


def main():
    iconset = os.path.join(OUT_DIR, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)
    # iconset 需要的标准尺寸
    for pt in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = pt * scale
            img = draw_icon(px)
            suffix = f"{pt}x{pt}" + ("@2x" if scale == 2 else "")
            save_png(img, px, os.path.join(iconset, f"icon_{suffix}.png"))
    icns = os.path.join(OUT_DIR, "icon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    print(f"已生成 {icns}")


if __name__ == "__main__":
    main()
