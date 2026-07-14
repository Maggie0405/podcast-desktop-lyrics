#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Podcast Desktop Lyrics for macOS
把 Apple 播客的逐字稿像"桌面歌词"一样悬浮显示在屏幕底部。

同步策略(两级):
  1) 首选 —— 直接镜像 Apple 播客的高亮句:
     通过 macOS 辅助功能(Accessibility)API 读取播客"逐字稿"面板里当前高亮
     那一句(AXStaticText)。这是 Apple 自己算好的实时对齐结果, 精度与播客 App
     完全一致, 不受动态广告插入(DAI)/时间轴漂移影响。
     前提: 已授予辅助功能权限, 且逐字稿面板处于打开状态(窗口可被挡在后面)。
  2) 兜底 —— 面板关闭时用播放进度顺延:
     从 Apple 播客数据库(MTLibrary.sqlite)的 ZPLAYHEAD 拿到真实播放位置,
     配合上一次首选模式校准出的偏移量, 查本地缓存的 TTML 字幕继续往后走。
     每次重新打开逐字稿面板都会自动重新校准。

使用前提:
  - macOS, Python3, 依赖 pyobjc (见 pyproject.toml)
  - 安装播放进度读取工具(用于识别"在播哪一集"):
      brew install media-control      # 推荐, 全 macOS 版本
      # 或旧方案: brew install nowplaying-cli
  - 首次运行后, 到 系统设置>隐私与安全性>辅助功能 勾选运行本程序的宿主
    (终端 / 打包后的 App), 才能启用"实时"模式
  - 在播客 App 里打开一次该集的"逐字稿", 让系统下载 TTML 缓存

运行:
  python3 -m podcast_desktop_lyrics      # 或安装后执行 podcast-lyrics

悬浮窗底部控件:
  « ‹ › »  顺延模式下手动微调字幕(粗调 ±10s / 细调 ±1s)
  ✕        退出
  右下角    ● 实时 = 正跟随 Apple 高亮; ○ 顺延 = 面板关后按进度顺延
  按住窗口可拖动位置; 长句会自动把窗口撑高
"""

import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import xml.etree.ElementTree as ET

import objc
try:
    from ApplicationServices import (
        AXIsProcessTrusted, AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
    )
    _AX_OK = True
except Exception:
    _AX_OK = False
from AppKit import (
    NSApp, NSApplication, NSAttributedString, NSBackingStoreBuffered, NSButton,
    NSColor, NSFont, NSFontAttributeName, NSMakeRect, NSPanel, NSScreen,
    NSStatusWindowLevel, NSStringDrawingUsesLineFragmentOrigin,
    NSTextAlignmentCenter, NSTextField, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSObject, NSTimer

PODCAST_GROUP = os.path.expanduser(
    "~/Library/Group Containers/243LU875E5.groups.com.apple.podcasts"
)
# Apple 播客的本地数据库, 里面 ZMTEPISODE.ZPLAYHEAD 保存每集的播放进度(秒)
PODCAST_DB = os.path.join(PODCAST_GROUP, "Documents", "MTLibrary.sqlite")

# ---------------------------------------------------------------- TTML 解析

def find_ttml(episode_id=None):
    """找到要显示的 TTML 字幕文件。

    Apple 把每集逐字稿缓存成 transcript_<episode_id>.ttml, 其中 <episode_id>
    正是 media-control 报告的 uniqueIdentifier。所以优先按当前正在播放这一集
    的 id 精确匹配; 只有拿不到 id(如未播放/用 nowplaying-cli)时, 才退回
    "最近修改的一个", 否则会出现"进度对得上、内容却是另一集"的串台问题。
    """
    patterns = [
        os.path.join(PODCAST_GROUP, "Library", "Cache", "Assets", "TTML", "**", "*.ttml"),
        os.path.join(PODCAST_GROUP, "**", "*.ttml"),
    ]
    candidates = []
    for p in patterns:
        candidates.extend(glob.glob(p, recursive=True))
        if candidates:
            break
    if not candidates:
        return None
    if episode_id is not None:
        sid = str(episode_id)
        matched = [c for c in candidates if sid in os.path.basename(c)]
        if matched:
            return max(matched, key=os.path.getmtime)
    return max(set(candidates), key=os.path.getmtime)


# 兼容旧名字
def find_latest_ttml():
    return find_ttml(None)


def parse_clock(value):
    """把 TTML 时间字符串转成秒: 支持 '12.5s' / '00:01:02.5' / '62.5'"""
    if value is None:
        return None
    value = value.strip()
    if value.endswith("s") and ":" not in value:
        try:
            return float(value[:-1])
        except ValueError:
            return None
    if ":" in value:
        parts = value.split(":")
        try:
            parts = [float(x) for x in parts]
        except ValueError:
            return None
        sec = 0.0
        for x in parts:
            sec = sec * 60 + x
        return sec
    try:
        return float(value)
    except ValueError:
        return None


def element_text(el):
    """递归取元素内全部文本(逐词 span 会被拼起来)"""
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(element_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _unit(el):
    """取 podcasts:unit 属性(忽略命名空间前缀), 没有则返回 None"""
    for k, v in el.attrib.items():
        if k.split("}")[-1] == "unit":
            return v
    return None


def _joined_text(el):
    """
    把元素内的逐词 span 用空格拼成可读句子。
    Apple 播客 TTML 里每个单词是独立 <span unit="word">, 词间无空白节点,
    直接 element_text 会粘成一坨; 这里按词拼接并补空格。
    没有 word span 时回退到原始文本。
    """
    words = [w for w in el.iter() if _unit(w) == "word"]
    if words:
        return " ".join((w.text or "").strip() for w in words if (w.text or "").strip())
    return re.sub(r"\s+", " ", element_text(el)).strip()


def parse_ttml(path):
    """解析 TTML, 返回 [(begin, end, text), ...] 按时间排序。

    优先按 <span unit="sentence"> 逐句切分(桌面歌词一句一句滚动);
    没有句级 span 时回退到 <p> 段落级。
    """
    tree = ET.parse(path)

    sentences = [
        el for el in tree.iter()
        if el.tag.split("}")[-1] == "span" and _unit(el) == "sentence"
    ]
    elements = sentences if sentences else [
        el for el in tree.iter() if el.tag.split("}")[-1] == "p"
    ]

    cues = []
    for el in elements:
        begin = parse_clock(el.get("begin"))
        end = parse_clock(el.get("end"))
        text = _joined_text(el)
        if begin is None or not text:
            continue
        cues.append((begin, end if end is not None else begin + 5.0, text))
    cues.sort(key=lambda c: c[0])
    return cues


# ------------------------------------------------------------- 播放进度读取

class PositionSource:
    """
    读取当前正在播放这一集的真实播放进度。

    为什么不用 media-control 的 elapsedTime:
      Apple 播客只在"播放/暂停/拖动"等事件时才向 MediaRemote 发布一次
      elapsedTime + timestamp, 连续播放时并不刷新。于是那个快照经常是几分钟、
      十几分钟前的旧值, 直接用或线性外推都会与真实进度越差越多(字幕串行)。

    真正可靠的位置来自 Apple 播客自己的数据库:
      ~/…/243LU875E5.groups.com.apple.podcasts/Documents/MTLibrary.sqlite
      表 ZMTEPISODE 的 ZPLAYHEAD 字段就是该集的播放进度(秒), 播放时大约每 10
      秒写盘一次。我们:
        1. 用 media-control 确定"正在播放哪一集"(uniqueIdentifier);
        2. 按该集 id(=ZSTORETRACKID)读 ZPLAYHEAD 拿到位置;
        3. 两次写盘之间做"带上限的外推", 让字幕平滑; 上限 ~12s, 这样即便用户
           暂停(ZPLAYHEAD 不再增长), 最多多跑十几秒就冻结, 恢复后自动校正。
    """

    MAX_EXTRAP = 12.0  # ZPLAYHEAD 约每 10s 刷新, 外推最多补这么多秒

    def __init__(self):
        self.backend = self._detect()
        self.episode_id = None        # 当前正在播放这一集的 uniqueIdentifier
        self.title = None             # 当前集标题(仅供显示/调试)
        self.pid = None               # 播客 App 进程号(AX 读高亮句时用)
        self.db_value = None          # 最近一次从 DB 读到的 ZPLAYHEAD
        self.db_anchor_mono = 0.0     # 该值"发生变化"时的 monotonic 时刻
        self.audio_dur = None         # 该集音频时长(秒), 用于比例校正
        self.playing = True           # 是否正在播放(暂停时停止外推)
        self.last_meta_poll = 0.0
        self.last_db_poll = 0.0

    # Finder 启动的 .app PATH 很干净, which 找不到 brew 的可执行文件,
    # 所以除了 PATH 再显式兜底这些常见安装目录
    _BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin")

    @classmethod
    def _resolve(cls, name):
        p = shutil.which(name)
        if p:
            return p
        for d in cls._BIN_DIRS:
            cand = os.path.join(d, name)
            if os.path.exists(cand):
                return cand
        return None

    def _detect(self):
        self.bin = None   # 选中后端的可执行文件绝对路径
        for name in ("media-control", "nowplaying-cli"):
            p = self._resolve(name)
            if p:
                self.bin = p
                return name
        return None

    def _poll_meta(self):
        """用 media-control/nowplaying-cli 确定当前正在播放的这一集"""
        try:
            if self.backend == "media-control":
                out = subprocess.run(
                    [self.bin, "get"], capture_output=True, text=True, timeout=3
                ).stdout
                data = json.loads(out)
                if data.get("bundleIdentifier") == "com.apple.podcasts":
                    self.episode_id = data.get("uniqueIdentifier")
                    self.title = data.get("title")
                    self.pid = data.get("processIdentifier")
                    # 暂停时 media-control 会立即把 playbackRate 变 0, 用它判断播放状态
                    self.playing = (data.get("playbackRate") or 0) > 0
        except Exception:
            pass

    def _read_playhead(self):
        """按当前集 id 从 Apple 播客数据库读取 ZPLAYHEAD(秒)"""
        if self.episode_id is None:
            return None
        try:
            # mode=ro 只读且能读到 WAL 里的最新写入; immutable 会读到旧快照, 不要用
            con = sqlite3.connect(f"file:{PODCAST_DB}?mode=ro", uri=True, timeout=0.5)
            try:
                row = con.execute(
                    "SELECT ZPLAYHEAD, ZDURATION FROM ZMTEPISODE WHERE ZSTORETRACKID=?",
                    (int(self.episode_id),),
                ).fetchone()
            finally:
                con.close()
            if row:
                if row[1]:
                    self.audio_dur = float(row[1])
                if row[0] is not None:
                    return float(row[0])
        except Exception:
            pass
        return None

    def position(self):
        now = time.monotonic()
        # 每 2s 确认一次"是哪一集"(换集时会变)
        if self.episode_id is None or now - self.last_meta_poll > 2.0:
            self._poll_meta()
            self.last_meta_poll = now
        # 每 1s 读一次 DB 里的播放进度
        if now - self.last_db_poll > 1.0:
            self.last_db_poll = now
            v = self._read_playhead()
            if v is not None and v != self.db_value:
                self.db_value = v
                self.db_anchor_mono = now  # 只在真正变化时重设锚点
        if self.db_value is None:
            return 0.0
        # 播放时从上次变化时刻起外推(封顶); 暂停时直接冻结在最后的进度, 不再前冲
        if not self.playing:
            return self.db_value
        return self.db_value + min(now - self.db_anchor_mono, self.MAX_EXTRAP)


# ---------------------------------------------------- 首选: 直接读 App 的高亮句

class AXLyrics:
    """
    通过 macOS 辅助功能(Accessibility)API 直接读取 Apple 播客逐字稿窗口里
    "当前高亮那句"的文本。这是 Apple 自己算好的实时对齐结果, 精度与播客 App
    完全一致, 不受动态广告插入/时间轴漂移影响。

    观察到的结构: 逐字稿每句是一个 AXStaticText, 句子文本在 AXDescription;
    正在朗读的高亮句其 AXValue 非空(本地化文案如"已高亮"/"Highlighted"),
    未高亮的句子 AXValue 为空 —— 用"AXValue 非空"判断高亮, 跨语言通用。

    前提: 已授予辅助功能权限, 且播客的逐字稿(听写文本)面板处于打开状态
    (播客窗口可以在其它窗口后面, 不必在最前)。
    """

    def __init__(self):
        self.pid = None
        self.app = None

    @staticmethod
    def supported():
        return _AX_OK

    @staticmethod
    def trusted():
        return _AX_OK and AXIsProcessTrusted()

    def _get(self, el, attr):
        err, val = AXUIElementCopyAttributeValue(el, attr, None)
        return val if err == 0 else None

    def _app_for(self, pid):
        if pid and pid != self.pid:
            self.app = AXUIElementCreateApplication(pid)
            self.pid = pid
        return self.app

    def _find_highlighted(self, el, depth=0):
        if el is None or depth > 60:
            return None
        if self._get(el, "AXRole") == "AXStaticText":
            val = self._get(el, "AXValue")
            if isinstance(val, str) and val.strip():   # 高亮句 AXValue 非空
                desc = self._get(el, "AXDescription")
                if isinstance(desc, str) and desc.strip():
                    return desc.strip()
        for child in (self._get(el, "AXChildren") or []):
            got = self._find_highlighted(child, depth + 1)
            if got:
                return got
        return None

    def current_line(self, pid):
        """返回当前高亮句文本; 拿不到(无权限/未开逐字稿/未播放)时返回 None"""
        if not self.trusted() or not pid:
            return None
        app = self._app_for(pid)
        if app is None:
            return None
        for win in (self._get(app, "AXWindows") or []):
            got = self._find_highlighted(win)
            if got:
                return got
        return None


# ------------------------------------------------------------------ 悬浮窗

class LyricsApp(NSObject):
    def init(self):
        self = objc.super(LyricsApp, self).init()
        if self is None:
            return None
        self.offset = 0.0          # 手动微调(«‹›»), 叠加在自动校准之上
        self.auto_offset = 0.0     # 由 AX 精确读数自动校准出的"内容时间 - 播放时间"
        self.calibrated = False    # 是否已用 AX 校准过(校准前不敢乱顺延)
        self.cues = []
        self.cue_index = {}        # 归一化句子文本 -> [cue 下标], 供 AX 文本匹配
        self.ttml_path = None
        self.ttml_mtime = 0
        self.source = PositionSource()
        self.ax = AXLyrics()
        self._build_window()
        self._reload_ttml()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, "tick:", None, True
        )
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            3.0, self, "checkNewTTML:", None, True
        )
        return self

    # 布局常量: 底部留一条 BAR 高的控制栏, 歌词区在其上, MARGIN_X 为左右边距
    MARGIN_X = 24
    BAR = 30
    TOP_PAD = 12
    MIN_H = 62
    FONT_SIZE = 22.0

    def _build_window(self):
        screen = NSScreen.mainScreen().frame()
        w = min(900, screen.size.width - 120)
        self.win_w = w
        self.max_h = screen.size.height * 0.55   # 再长也不铺满屏幕
        self._last_text = None
        h = self.MIN_H
        rect = NSMakeRect((screen.size.width - w) / 2, 60, w, h)

        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(NSStatusWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.55))
        panel.setMovableByWindowBackground_(True)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        content = panel.contentView()
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(14.0)
        self.panel = panel

        # 歌词区: 底部锚在控制栏之上, 高度随文字自适应
        label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(self.MARGIN_X, self.BAR, w - 2 * self.MARGIN_X,
                       h - self.BAR - self.TOP_PAD))
        label.setEditable_(False)
        label.setBordered_(False)
        label.setDrawsBackground_(False)
        label.setAlignment_(NSTextAlignmentCenter)
        label.setFont_(NSFont.systemFontOfSize_(self.FONT_SIZE))
        label.setTextColor_(NSColor.whiteColor())
        label.cell().setWraps_(True)
        content.addSubview_(label)
        self.label = label

        # 底部控制栏: 左侧 « ‹ › » 校准按钮, 右侧状态 + 关闭
        def make_button(title, x, width, action):
            b = NSButton.alloc().initWithFrame_(NSMakeRect(x, 4, width, 24))
            b.setTitle_(title)
            b.setBordered_(False)
            b.setTarget_(self)
            b.setAction_(action)
            content.addSubview_(b)
            return b

        make_button("«", 6, 22, "coarseEarlier:")   # -10s
        make_button("‹", 28, 20, "earlier:")        # -1s
        make_button("›", 48, 20, "later:")          # +1s
        make_button("»", 68, 22, "coarseLater:")    # +10s
        make_button("✕", w - 32, 26, "quit:")

        info = NSTextField.alloc().initWithFrame_(NSMakeRect(w - 200, 7, 158, 15))
        info.setEditable_(False)
        info.setBordered_(False)
        info.setDrawsBackground_(False)
        info.setAlignment_(2)  # 右对齐
        info.setFont_(NSFont.systemFontOfSize_(11.0))
        info.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.55))
        info.setStringValue_("")
        content.addSubview_(info)
        self.info = info

        self._set_text("等待播放中… 请在播客 App 播放一集(已看过逐字稿的)")
        panel.orderFrontRegardless()

    def _set_text(self, text):
        """更新歌词文字, 并按文字长度自适应窗口高度(底部固定, 向上生长)"""
        if text == self._last_text:
            return
        self._last_text = text
        self.label.setStringValue_(text)

        label_w = self.win_w - 2 * self.MARGIN_X
        font = self.label.font()
        astr = NSAttributedString.alloc().initWithString_attributes_(
            text, {NSFontAttributeName: font})
        rect = astr.boundingRectWithSize_options_(
            (label_w, 100000.0), NSStringDrawingUsesLineFragmentOrigin)
        text_h = rect.size.height
        new_h = max(self.MIN_H, min(self.max_h, text_h + self.BAR + self.TOP_PAD))

        f = self.panel.frame()
        if abs(f.size.height - new_h) > 1:
            # 保持底部左下角不动 -> 窗口向上生长
            self.panel.setFrame_display_(
                NSMakeRect(f.origin.x, f.origin.y, self.win_w, new_h), True)
        self.label.setFrame_(
            NSMakeRect(self.MARGIN_X, self.BAR, label_w, new_h - self.BAR - self.TOP_PAD))

    # ---------- 定时任务 ----------

    def tick_(self, timer):
        # 首选: 逐字稿面板开着时, 直接镜像 Apple 的高亮句(实时精确),
        # 同时用它校准偏移, 供面板关闭后顺延
        line = self.ax.current_line(self.source.pid)
        if line:
            self._set_text(line)
            self._calibrate_from_ax(line)
            self.info.setStringValue_("● 实时")
            return

        # 面板关闭: 用播放进度 + 上次 AX 校准出的偏移顺延字幕
        if not self.cues:
            if not AXLyrics.trusted():
                self._set_text(
                    "请在 系统设置>隐私与安全性>辅助功能 里授权本程序, "
                    "并在播客里打开该集的“逐字稿”"
                )
            return
        t = self.source.position() + self.auto_offset + self.offset
        text = self._cue_at(t)
        if text is not None:
            self._set_text(text)
        if self.calibrated:
            tail = f" {self.offset:+.0f}s" if abs(self.offset) >= 0.5 else ""
            state = "○ 暂停" if not self.source.playing else "○ 顺延"
            self.info.setStringValue_(state + tail)
        else:
            # 还没被 AX 校准过, 顺延会不准 —— 提示打开一次逐字稿
            self.info.setStringValue_("打开一次逐字稿以校准")

    def checkNewTTML_(self, timer):
        self._reload_ttml()

    def _reload_ttml(self):
        # 先刷新一次"正在播放"信息, 拿到当前集 id, 再据此挑选对应的字幕
        self.source.position()
        path = find_ttml(self.source.episode_id)
        if not path:
            self.label.setStringValue_(
                "没找到逐字稿缓存: 请先在播客 App 里打开该集的\u201c逐字稿\u201d"
            )
            return
        mtime = os.path.getmtime(path)
        if path == self.ttml_path and mtime == self.ttml_mtime:
            return
        try:
            self.cues = parse_ttml(path)
            self._build_cue_index()
            self.calibrated = False   # 换集/换文件后需要重新校准
            self.auto_offset = 0.0
            self.ttml_path, self.ttml_mtime = path, mtime
            print(f"[loaded] {os.path.basename(path)}  ({len(self.cues)} 句)"
                  f"  ep={self.source.episode_id}")
        except Exception as e:
            print("TTML 解析失败:", e)

    # ---------- AX 精确读数 <-> TTML 的文本匹配与校准 ----------

    @staticmethod
    def _norm(s):
        """归一化句子文本, 便于跨来源匹配(忽略大小写/空白/首尾标点)"""
        return re.sub(r"\s+", " ", s).strip().lower().strip(".,!?;:…\"' ")

    def _build_cue_index(self):
        self.cue_index = {}
        for i, (_b, _e, text) in enumerate(self.cues):
            self.cue_index.setdefault(self._norm(text), []).append(i)

    def _match_cue(self, line):
        """把 AX 高亮句文本匹配到某个 cue 下标; 有重复时取离当前预期最近的那个"""
        key = self._norm(line)
        idxs = self.cue_index.get(key)
        if not idxs:
            # AX 文本可能标点/截断略有不同, 退回前缀匹配
            pref = key[:40]
            if pref:
                idxs = [i for i, c in enumerate(self.cues)
                        if self._norm(c[2]).startswith(pref)]
        if not idxs:
            return None
        if len(idxs) == 1:
            return idxs[0]
        expect = self.source.position() + self.auto_offset + self.offset
        return min(idxs, key=lambda i: abs(self.cues[i][0] - expect))

    def _calibrate_from_ax(self, line):
        """用一次精确的 AX 高亮句, 校准 内容时间 - 播放时间 的偏移"""
        idx = self._match_cue(line)
        if idx is None:
            return
        content_begin = self.cues[idx][0]
        real = self.source.position()
        self.auto_offset = content_begin - real
        self.calibrated = True

    def _cue_at(self, t):
        lo, hi, best = 0, len(self.cues) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if self.cues[mid][0] <= t:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        if best is None:
            return "♪"
        begin, end, text = self.cues[best]
        return text if t <= end + 2.0 else "♪"

    # ---------- 按钮 ----------

    # 偏移为正 = 字幕整体提前(显示更靠后的内容), 用来追上超前的音频
    def earlier_(self, sender):
        self.offset -= 1.0

    def later_(self, sender):
        self.offset += 1.0

    def coarseEarlier_(self, sender):
        self.offset -= 10.0

    def coarseLater_(self, sender):
        self.offset += 10.0

    def quit_(self, sender):
        NSApp.terminate_(None)


def main():
    if PositionSource()._detect() is None:
        print(
            "未检测到进度读取工具, 请先安装:\n"
            "  brew install media-control      (推荐, 全 macOS 版本)\n"
            "  # 或旧方案: brew install nowplaying-cli\n"
            "安装后重新运行。"
        )
    if AXLyrics.supported() and not AXLyrics.trusted():
        print(
            "提示: 尚未获得辅助功能权限, 当前只能用『顺延』估算模式。\n"
            "到 系统设置>隐私与安全性>辅助功能 勾选运行本程序的宿主(终端/App)"
            "后重启, 即可启用与播客 App 一致的『实时』模式。"
        )
    app = NSApplication.sharedApplication()
    delegate = LyricsApp.alloc().init()
    app.run()


if __name__ == "__main__":
    main()
