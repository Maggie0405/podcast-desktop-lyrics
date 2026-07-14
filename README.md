# Podcast Desktop Lyrics

把 **Apple 播客**的逐字稿像"桌面歌词"一样，实时悬浮显示在 macOS 屏幕上。
_Show Apple Podcasts transcripts as a floating, karaoke-style "desktop lyrics" overlay on macOS._

<p align="center"><em>播客窗口可以丢到后台，只看这条悬浮字幕就行。</em></p>

---

## ✨ 特性 / Features

- 🎯 **与播客 App 完全一致的实时精度** —— 直接镜像 Apple 逐字稿里当前高亮的那句
- 🌊 **面板关掉也能顺延** —— 用播放进度继续往下走，再开面板自动重新校准
- ⏸ **暂停同步暂停** —— 播客一停，字幕立刻定住，不会继续往前冲
- 🪟 悬浮窗置顶、无边框、可拖动，**长句自动撑高**、跨所有桌面/全屏
- 🈶 正确处理 Apple 逐字稿的逐词 span（补空格）、逐句切分
- 🎧 自动识别"正在播放哪一集"，多份缓存也不会串台

---

## 🧠 原理 / How it works

同步分两级，自动切换：

### 1) 首选：镜像 Apple 的高亮句（实时、精确）

Apple 播客的"逐字稿"面板会随音频**逐句高亮**。程序通过 macOS **辅助功能
(Accessibility) API** 读取那个面板里当前高亮的 `AXStaticText`，直接显示到悬浮窗。

这是 Apple 自己算好的实时对齐结果，**精度和播客 App 一模一样**，不受下面提到的
广告偏移影响。

> 前提：已授予辅助功能权限，且逐字稿面板处于打开状态（**播客窗口可以被其它窗口
> 完全挡住、放到别的桌面**，只是不能切走逐字稿视图、也别最小化）。

### 2) 兜底：面板关掉后按播放进度顺延

面板一关，那些 UI 元素就不存在了，AX 读不到。这时改用：

- **真实播放位置**：读 Apple 播客数据库 `MTLibrary.sqlite` 的 `ZMTEPISODE.ZPLAYHEAD`
  （播放时约每 10 秒写盘一次），两次写盘之间做带上限的外推，保证平滑。
- **本地 TTML 字幕**：Apple 打开过逐字稿后会把 TTML 缓存到本地；按当前集
  `uniqueIdentifier` 精确匹配对应文件解析。
- **偏移校准**：用最近一次"首选模式"读到的高亮句，匹配回 TTML，算出
  `内容时间 − 播放时间` 的偏移量；面板关闭期间就用 `播放位置 + 偏移` 查字幕。

所以推荐用法：**开一次逐字稿面板校准 → 丢后台 → 全程看悬浮窗**；偶尔再瞄一眼
面板就会自动纠偏。

---

## ⚠️ 已知限制 / Known limitations

- **仅限 macOS 上的 Apple 播客**（依赖其本地 TTML 缓存、数据库和 UI 结构）。
- **"实时"模式需要辅助功能权限**，且逐字稿面板得渲染着——因为 Apple 没有公开
  "当前是哪句"的后台接口，这个对齐数据只从渲染出来的 UI 里出。
- **纯顺延（面板全程关闭）不够精确**。Apple 逐字稿是母版时间轴，实际发布音频经
  **动态广告插入 / 剪辑**后与之有逐段累积的偏移（可差几十秒），且断点信息本地不
  可得。所以顺延依赖"首选模式"校准；离上次校准越久、跨越的广告断点越多，越可能
  漂移，重新打开面板即可校正。
- 得先在播客里**打开过该集的逐字稿**，让系统下载 TTML 缓存。
- 依赖 Apple 未公开的缓存/数据库结构与 AX 层级，**系统更新后可能失效**。

---

## 📦 安装 / Install

### 依赖

- macOS，Python 3.9+
- [`media-control`](https://formulae.brew.sh/formula/media-control)（识别正在播放哪一集）

### 方式一：打包成独立 .app（推荐，免终端、授权最省心）

```bash
git clone https://github.com/Maggie0405/podcast-desktop-lyrics.git
cd podcast-desktop-lyrics
brew install media-control
bash scripts/build_app.sh
```

产物在 `packaging/dist/Podcast Desktop Lyrics.app`，把它拖进 `/Applications` 即可
双击运行（自带 Python，无 Dock 图标的后台悬浮工具，用悬浮窗上的 `✕` 退出）。
辅助功能权限直接授给这个 App（见下），比授权终端更干净。

### 方式二：一键脚本安装（终端运行 + 开机自启）

```bash
bash scripts/install.sh
```

脚本会：装 `media-control` → `pip install` 本包 → 注册开机自启（LaunchAgent）。

### 手动

```bash
brew install media-control
pip install .
python3 -m podcast_desktop_lyrics     # 或安装后直接: podcast-lyrics
```

### 授予辅助功能权限（启用"实时"模式）

**系统设置 › 隐私与安全性 › 辅助功能**，添加并勾选运行本程序的宿主：
- **.app 方式** → 勾选 **Podcast Desktop Lyrics**（推荐，最干净）
- 从终端运行 → 勾选你的**终端**（Terminal / iTerm）
- 开机自启脚本 → 勾选安装脚本里提示的 **python3 路径**

没授权也能用，但只有"顺延"估算精度。

### 卸载

```bash
bash scripts/uninstall.sh
```

---

## 🕹 使用 / Usage

1. 打开 Apple 播客，播放一集，并**打开它的"逐字稿"**面板
2. 启动本程序，屏幕底部出现悬浮字幕
3. 悬浮窗跟随播客高亮实时滚动；把播客窗口丢到后台即可

悬浮窗底部：

| 控件 | 作用 |
|---|---|
| `« ‹ › »` | 顺延模式下手动微调字幕（粗调 ±10s / 细调 ±1s） |
| `✕` | 退出 |
| 右下角 | `● 实时` = 正跟随 Apple 高亮；`○ 顺延` = 面板关后按进度顺延 |

按住窗口可拖动位置；长句会自动把窗口撑高。

---

## 🗺 Roadmap

- [x] 打包成独立 `.app`（免终端、辅助功能授权更顺）—— 见 `scripts/build_app.sh`
- [ ] 给 `.app` 做签名 / 公证，并附上图标
- [ ] 悬浮窗外观设置（字号 / 透明度 / 颜色 / 位置记忆）
- [ ] 同时显示上一句 / 下一句
- [ ] 可选：把广告断点校准点持久化，改善纯顺延精度
- [ ] 兼容更多 macOS 版本 / 语言的 AX 文案

---

## 🤝 贡献 / Contributing

欢迎 issue 和 PR。这个项目重度依赖 Apple 未公开的实现细节，遇到某个 macOS
版本失效时，欢迎运行 `python3 scripts/ax_probe.py > ax_dump.txt` 把 AX 结构
dump 出来附在 issue 里一起反馈。

## 📄 License

[MIT](LICENSE)
