# ComfyPanel 🎨⚡

> **The Artisan’s Bridge between ComfyUI and Adobe Photoshop.**

[English](#english) | [中文](#中文) | [📖 Detailed Tutorials](https://lazyet.com/blogs/labs/comfypanel-tutorial) | [💎 ComfyPanel Pro](https://lazyet.com/products/comfypanel-pro)

---

<a name="english"></a>

## 🌟 Overview
ComfyPanel is a professional-grade, high-performance integration for **Adobe Photoshop** and **ComfyUI**. Built by designers for designers, it treats AI generation not just as a button, but as a fine-tuned "artisan tool" seamlessly woven into your creative layers.

<p align="center">
  <img src="https://github.com/user-attachments/assets/6624c39b-1d04-4a11-a644-48e8ec3ac573" alt="ComfyPanel Interface" width="900" />
</p>

### 🚀 Key Features
- **Dual Computation Engine**: Seamlessly switch between **Local ComfyUI** (Maximum Privacy) and **BizyAir Cloud** (Maximum Power),  **Runninghub Cloud** (Maximum Power), with dedicated support for **NanoBanana Engine**.
- **Integrated Split-View (App + Graph)**: No need to switch between browser and Photoshop. Open the full ComfyUI workflow graph directly inside the Photoshop panel side-by-side with your "App" controls.
- **Interactive Control (Pause & Preview)**: Integrated `AnyPreviewPause` node allows you to stop and preview intermediate latents directly in the Photoshop panel. Tweak parameters or continue only when you're satisfied.
- **Infinite Offline Recovery**: Never lose a masterpiece. If Photoshop crashes or closes, ComfyPanel automatically retrieves and renders your cloud results upon the next launch.
- **Deep Canvas Awareness**: Real-time synchronization of layer visibility, transparency, masks, and sub-pixel selections.
- **Node-Based Logic Control**: Advanced custom nodes like `SwitchAnyMute` allow you to toggle complex workflow branches directly from the Photoshop UI.
- **Zero-Copy Performance**: High-speed local file referencing to bypass binary IPC bottlenecks—perfect for 4K+ textures.
- **Remote Tunnel (FRP)**: Access your local ComfyUI instance from anywhere via integrated FRP tunneling. Features on-demand dependency downloading with multi-source fallback and auto-resume logic.
- **ModelZoo API (All-in-one) Integration**: Access RunningHub and BizyAir's comprehensive model libraries directly. Dynamically generates UI for model parameters, features smart input grouping (Smart-Loader) and built-in billing references.

### 🏗️ Structure
1. **[ComfyPanel (PS Plugin)](./photoshop_plugin/ComfyPanel)**: The UXP core. A modern, minimalist UI built for the Photoshop sidebar.
2. **Custom Nodes**: A robust library of back-end nodes for flow control and image IO.
3. **App System**: Pre-built "Apps" that turn scary JSON workflows into beautiful, familiar UI sliders.

### 🛠️ Installation
*   **Photoshop**: Adobe Photoshop 2025 (v26.0) or higher.
*   **ComfyUI**: Clone this repo to `custom_nodes/` and restart.
*   **Plugin Setup**: 
    *   **Auto**: Run `comfypanel.ccx` (recommended).
    *   **Manual**: Copy the plugin folder to the UXP plugins directory.
    *   *Need help? See the [Full Setup Guide](https://lazyet.com/blogs/labs/comfypanel-tutorial).*

---

<a name="中文"></a>

## 🌟 项目简介
ComfyPanel 是一套专为 **Adobe Photoshop** 开发的高灵敏度、专业级 **ComfyUI** 深度整合方案。它由设计师发起，旨在将复杂的节点工作流打磨成设计师手中得心应手的“算力画笔”，让 AI 真正回归到图层创作的本源。

<p align="center">
  <img src="https://github.com/user-attachments/assets/6624c39b-1d04-4a11-a644-48e8ec3ac573" alt="ComfyPanel 界面演示" width="900" />
</p>

### ✨ 核心特性
- **云/地多引擎支持**：支持**本地微调**（极致隐私）与 **BizyAir 云端加速**（极致算力）, **Runninghub 云端加速**（极致算力）,**NanoBanana 专属引擎**一键切换。
- **全功能双分栏模式 (App + Graph)**：无需在浏览器和 PS 之间切换。直接在 Photoshop 插件面板内打开完整的 ComfyUI 工作流连线图，与 App 操作面板并排显示，实时联动。
- **交互式过程控制**：内置 `AnyPreviewPause` 节点，支持在 PS 面板中直接预览中间层结果（Latent Preview）。暂停、微调或继续，确保生成过程完全可控。
- **离线断点找回**：首创云端任务持久化机制。即便中途关闭 PS，重启后系统也会自动抓回并渲染所有已完成的任务图片，绝不丢失灵感。
- **深层画布感知**：全自动同步图层显隐、透明度、选区及蒙版。
- **流程逻辑控制**：内置 `SwitchAnyMute` 等逻辑节点，让你在 PS 界面中就能优雅地切换复杂的流程分支。
- **零拷贝加速**：独有的本地路径直接引用技术，告别大图传输的延迟与内存溢出。
- **远程隧道 (FRP)**：内置 FRP 隧道技术，支持从公网远程访问本地 ComfyUI。具备按需自动下载依赖、多源重试、SSL 校验绕过及断线自动重连等鲁棒特性。
- **ModelZoo API (All-in-one)模型库整合**：集成 RunningHub 与 BizyAir 强大模型库。自动解析模型参数生成 UI，支持智能加载器（Smart-Loader）自动分组功能，并内置计费参考。

### 🛠️ 快速安装
*   **Photoshop 要求**：Adobe Photoshop 2025 (v26.0) 或更高版本。
*   **ComfyUI 端**：克隆本仓库至 `custom_nodes/` 目录并重启。
*   **插件安装**：
    *   **自动安装**：直接运行 `comfypanel.ccx`（推荐）。
    *   **手动安装**：将插件文件夹复制到系统 UXP 插件目录。
    *   *安装遇到问题？查看[完整中文教程](https://lazyet.com/blogs/labs/comfypanel-tutorial)。*

---

## 💎 Free Community vs Pro / 免费社区版与专业版

ComfyPanel is committed to the open-source community. The **Free Community Edition** is 100% free, forever free, and unlimited for all core local workflow requirements! If you need advanced professional tools to supercharge your design workflow, consider upgrading to the **Pro Edition**.

ComfyPanel 始终拥抱开源社区。**免费社区版**是 100% 永久免费的，不限制本地核心工作流的基础生成！如果您需要更高级的专业功能以大幅提升创作效率，可以考虑升级为 **Pro 专业版**。

| Feature / 功能 | Free Community / 免费社区版 | Pro Edition / Pro专业版 💎 |
| :--- | :--- | :--- |
| **Local Execution / 本地运行** | Unlimited / 无限制 | Unlimited / 无限制 |
| **Interactive Pause / 暂停再编辑** | Static only / 仅限静态执行 | Interactive re-edit / 交互式暂停再重绘 |
| **Video & Audio / 视频与音频节点** | Image only / 仅限图像 (LoadImage) | Full video & audio / 音视频全功能及本地导出 |
| **Resolution Limit / 分辨率上限** | Up to 2000px / 限制 2K 以内 | Unlimited resolution / 无损超高清无上限 |
| **History Manager / 历史生成记录** | Last 5 items / 仅保留 5 条 | Unlimited history / 无上限保存 |
| **Smart Layout / 清爽排版** | Standard tiled / 标准平铺 | Smart-Loader & Capsule / 极简胶囊布局 |

---

## 💬 Support & Feedback / 反馈与升级
ComfyPanel is an independent tool hand-crafted by **[Gino @ LAZYet](https://lazyet.com)**, designed to bring professional AI workflows directly into Adobe Photoshop.
ComfyPanel 是由 **[Gino @ LAZYet](https://lazyet.com)** 独立开发与精心打磨的设计师级 AI 整合方案，旨在将专业的 AI 工作流无缝融入 Adobe Photoshop。

- 💎 **[Upgrade to ComfyPanel Pro / 升级至 Pro 专业版](https://lazyet.com/products/comfypanel-pro)**
- 🛍️ **[Explore our Physical Designs at LAZYet Studio / 探索我们的物理设计产品](https://lazyet.com)**
- 🐛 **[Submit Feedback & Bug Reports / 提交反馈与 Bug 报告 (GitHub)](https://github.com/ginolazy/ComfyPanel/issues)**

<p align="center">
  <img src="https://github.com/user-attachments/assets/775d47e7-cb82-4f71-a5b1-2726159592b8" alt="ComfyPanel 交流群" width="220" />
</p>

## ⚖️ License

This project uses a **Dual License** model:

| Component | Paths | License |
| :--- | :--- | :--- |
| **ComfyUI Custom Nodes** | `/modules/`, `/web/`, `/custom/`, `/default/` | MIT License — free to use, modify & distribute |
| **Photoshop Plugin (UXP)** | `/photoshop_plugin/` | Proprietary — free to use, no redistribution or reverse engineering |

See [LICENSE](./LICENSE) for full terms.

---
*Crafted slowly. Shared freely. 2026 © [LAZYet](https://lazyet.com)*
