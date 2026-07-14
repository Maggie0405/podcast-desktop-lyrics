#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试工具: 把 Apple 播客窗口的辅助功能(AX)树完整 dump 出来, 每个节点连同
它的 role / roleDescription / value / title / description / selected 等属性都打印。

本项目"实时"模式依赖: 逐字稿每句是一个 AXStaticText(文本在 AXDescription),
当前高亮句其 AXValue 非空。若某个 macOS 版本这套结构变了导致同步失效, 用本
脚本 dump 出实际结构, 附在 issue 里最有帮助。

跑法:
    1. 播客 App 正在播放 + 逐字稿面板打开
    2. python3 scripts/ax_probe.py > ax_dump.txt
       (首次需在 系统设置>隐私与安全性>辅助功能 勾选运行的终端)
    3. 查看 / 附上 ax_dump.txt
"""
import json
import subprocess
import sys

from ApplicationServices import (
    AXIsProcessTrustedWithOptions, AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue, AXUIElementCopyAttributeNames,
)

STR_ATTRS = [
    "AXRoleDescription", "AXValue", "AXTitle", "AXDescription",
    "AXHelp", "AXLabel", "AXSelectedText", "AXPlaceholderValue",
]


def get(el, attr):
    err, val = AXUIElementCopyAttributeValue(el, attr, None)
    return val if err == 0 else None


def attr_names(el):
    err, names = AXUIElementCopyAttributeNames(el, None)
    return list(names) if err == 0 else []


def podcasts_pid():
    try:
        d = json.loads(subprocess.run(
            ["media-control", "get"], capture_output=True, text=True).stdout)
        if d.get("bundleIdentifier") == "com.apple.podcasts":
            return d.get("processIdentifier")
    except Exception:
        pass
    out = subprocess.run(["pgrep", "-x", "Podcasts"], capture_output=True, text=True).stdout
    return int(out.split()[0]) if out.strip() else None


def brief(v):
    if isinstance(v, str):
        v = v.replace("\n", " ").strip()
        return repr(v[:80])
    return None


def walk(el, depth=0, count=[0]):
    if el is None or depth > 60 or count[0] > 6000:
        return
    count[0] += 1
    role = get(el, "AXRole") or "?"
    names = set(attr_names(el))
    bits = []
    for a in STR_ATTRS:
        if a in names:
            b = brief(get(el, a))
            if b and b != "''":
                bits.append(f"{a.replace('AX','')}={b}")
    if get(el, "AXSelected"):
        bits.append("SELECTED")
    # 有没有 TextMarker 相关(WebKit 富文本会有)
    marker = [a for a in names if "Marker" in a or "Selected" in a]
    if marker:
        bits.append("markers=" + ",".join(sorted(set(m.replace('AX','') for m in marker))))
    line = f"{'  '*depth}[{role}] " + "  ".join(bits)
    # 只打印有信息量的行, 或结构性容器
    if bits or role in ("AXScrollArea", "AXWebArea", "AXGroup", "AXList", "AXTable", "AXRow"):
        print(line)
    for child in (get(el, "AXChildren") or []):
        walk(child, depth + 1, count)


def main():
    if not AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}):
        print("!! 没有辅助功能权限。系统设置>隐私与安全性>辅助功能 勾选终端后再跑。")
        sys.exit(1)
    pid = podcasts_pid()
    print("播客 pid =", pid)
    app = AXUIElementCreateApplication(pid)
    wins = get(app, "AXWindows") or []
    print("窗口数:", len(wins))
    for i, w in enumerate(wins):
        print(f"\n===== 窗口 {i}: {get(w,'AXTitle')!r} =====")
        walk(w)


if __name__ == "__main__":
    main()
