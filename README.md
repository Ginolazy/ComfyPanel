# ComfyPanel 🎨⚡

> **The Artisan’s Bridge between ComfyUI and Adobe Photoshop.**

[English](#english) | [中文](#中文) | [📖 Detailed Tutorials](https://lazyet.com/blogs/labs/comfypanel-tutorial) | [💎 ComfyPanel Pro](https://lazyet.com/products/comfypanel-pro)

---

<a name="english"></a>

## 🌟 Overview
ComfyPanel is a professional-grade, high-performance integration for **Adobe Photoshop** and **ComfyUI**. Built by designers for designers, it treats AI generation not just as a button, but as a fine-tuned "artisan tool" seamlessly woven into your creative layers. 

With the latest **v1.1.0** ecosystem upgrade, ComfyPanel expands beyond 2D canvas sensing into multi-cloud environments, real-time asset synchronization, and immersive multi-dimensional previews.

<p align="center">
  <img src="https://github.com/user-attachments/assets/6624c39b-1d04-4a11-a644-48e8ec3ac573" alt="ComfyPanel Interface" width="900" />
</p>

### 🚀 Key Features
- **Multi-Cloud & Local Engine Ecosystem**: Seamlessly switch compute backends between **Local ComfyUI** (Maximum Privacy), **BizyAir Cloud**, and the newly integrated **RunningHub Cloud API** (Maximum Power), with native support for the dedicated **NanoBanana Engine**.
- **ModelZoo API with Instant Live Sync**: Real-time cloud model library integration for BizyAir and RunningHub. New models added to official cloud repositories become immediately available in ComfyPanel without any plugin updates. Features dynamic parameter UI generation, **Smart-Loader** grouping, and transparent billing references.
- **Immersive Multi-Dimensional Previews (New)**: The result preview box goes beyond flat images:
  - **360° VR Panoramic View**: Fully interactive, equirectangular panoramic viewer built directly into the Photoshop sidebar.
  - **Native 3D Mesh Viewer**: Smooth interactive rendering for 3D assets (supports `.glb` and `.obj` files) generated from backend nodes (e.g., SV3D / Tripo3D workflows).
- **Integrated Split-View (App + Graph)**: No need to switch between browser and Photoshop. Open the full ComfyUI workflow graph directly inside the Photoshop panel side-by-side with your "App" controls.
- **Interactive Control (Pause & Preview)**: Integrated `AnyPreviewPause` node allows you to stop and preview intermediate latents directly in the Photoshop panel. Tweak parameters or continue only when you're satisfied.
- **Infinite Offline Recovery**: Never lose a masterpiece. If Photoshop crashes or closes, ComfyPanel automatically retrieves and renders your asynchronous cloud results (RunningHub / BizyAir) upon the next launch.
- **Deep Canvas Awareness**: Real-time synchronization of layer visibility, transparency, masks, and sub-pixel selections via Photoshop UXP core.
- **Zero-Copy Performance**: Architecture-level optimization. Utilizing direct local file referencing to completely bypass binary IPC data bottlenecks. Delivers instant synchronization for 4K+ high-resolution textures out of the box with **zero manual configuration required**.
- **Remote Tunnel (FRP)**: Access your local ComfyUI instance from anywhere via integrated FRP tunneling. Features on-demand dependency downloading with multi-source fallback and auto-resume logic.

### 🏗️ Structure
1. **[ComfyPanel (PS Plugin)](./photoshop_plugin/ComfyPanel)**: The UXP core. A modern, minimalist UI built for the Photoshop sidebar.
2. **Custom Nodes**: A robust library of back-end nodes for flow control, multi-dimensional asset rendering, and image IO.
3. **App System**: Pre-built "Apps" that turn scary JSON workflows into beautiful, familiar UI sliders.

### 🛠️ Installation
* **Photoshop**: Adobe Photoshop 2025 (v26.0) or higher.
* **ComfyUI**: Clone this repo to `custom_nodes/` and restart.
* **Plugin Setup**: 
    * **Auto**: Run `comfypanel.ccx` (recommended).
    * **Manual**: Copy the plugin folder to the UXP plugins directory.
    * *Need help? See the [Full Setup Guide](https://lazyet.com/blogs/labs/comfypanel-tutorial).*

### ❓ AI-Assisted Troubleshooting & FAQ
> **Q: How do I sync account balances and user info for BizyAir and RunningHub?**
> **A:** ComfyPanel features a built-in real-time billing and account dashboard inside the sidebar panel:
> - **BizyAir Cloud**: Simply enter your `API Key`. ComfyPanel will execute workflows and instantly fetch your **Username** and **Account Balance** automatically.
> - **RunningHub Cloud**: Enter both your `API Key` and `UserId` to fully unlock your **Username**, **Account Balance/Credits**, and sync your cloud API workflows.

> **Q: How do I fix interface lag or memory overflows when transferring large images?**
> **A:** You don't have to configure anything. ComfyPanel utilizes a native, architecture-level **Zero-Copy mechanism** by default. It leverages direct local file references via Photoshop UXP to completely bypass standard binary IPC data bottlenecks, delivering near-instant synchronization for 4K+ high-resolution textures without consuming extra panel memory.

> **Q: How can I interact with 360° Panoramas or 3D Assets (GLB/OBJ) generated by ComfyUI?**
> **A:** Simply run your workflow. When ComfyPanel detects panoramic outputs or 3D mesh file formats (`.glb`/`.obj`), the result preview widget automatically switches to an interactive 3D/VR viewport, allowing you to orbit, pan, or spin the asset directly inside the Photoshop UI sidebar.

---

<a name="中文"></a>

## 🌟 项目简介
ComfyPanel 是一套专为 **Adobe Photoshop** 开发的高灵敏度、专业级 **ComfyUI** 深度整合方案。它由设计师发起，旨在将复杂的节点工作流打磨成设计师手中得心应手的“算力画笔”，让 AI 真正回归到图层创作的本源。

在最新的 **v1.1.0** 生态升级中，ComfyPanel 的触角正式从传统的 2D 画布感知延伸至多云算力调度、多维资产实时同步及沉浸式交互预览。

<p align="center">
  <img src="https://github.com/user-attachments/assets/6624c39b-1d04-4a11-a644-48e8ec3ac573" alt="ComfyPanel 界面演示" width="900" />
</p>

### ✨ 核心特性
- **云/地多算力与引擎矩阵**：支持**本地运行**（极致隐私）、**BizyAir 云端加速**、全新集成的 **RunningHub 算力云/API 工作流调度**以及 **NanoBanana 专属引擎**一键无缝切换。
- **ModelZoo API 实时同步模型库**：完美整合 RunningHub 与 BizyAir 的云端海量模型库。云端官方库新增模型无需更新插件即可**即时全自动同步**，在 Photoshop 内直接解析模型参数并自动生成 UI 控制项，支持智能加载器（Smart-Loader）自动分组及云端计费参考。
- **沉浸式多维资产预览 (全新升级)**：结果预览框打破平面图层限制，迎来空间维度的全面跃升：
  - **360° VR 全景视图**：在 Photoshop 侧边栏内直接嵌入全交互式、等距柱状投影全景图渲染视口。
  - **原生 3D 模型视口**：支持由后端节点（如 SV3D / Tripo3D 工作流）生成的 3D 资产（支持 `.glb` 和 `.obj` 格式文件）在面板内进行平滑的 3D 轨道交互旋转与预览。
- **全功能双分栏模式 (App + Graph)**：无需在浏览器和 PS 之间切换。直接在 Photoshop 插件面板内打开完整的 ComfyUI 工作流连线图，与 App 操作面板并排显示，实时联动。
- **交互式过程控制**：内置 `AnyPreviewPause` 节点，支持在 PS 面板中直接预览中间层潜空间结果（Latent Preview）。暂停、微调或继续，确保生成过程完全可控。
- **离线断点找回**：首创云端任务持久化机制。即便中途关闭 PS 或遇到程序崩溃，重启后系统也会自动抓回并渲染来自 RunningHub / BizyAir 已完成的算力任务，绝不丢失灵感。
- **深层画布感知**：基于 Photoshop UXP 核心，全自动同步图层显隐、透明度、选区及蒙版。
- **零拷贝（Zero-Copy）架构级加速**：架构级无感优化。独有的本地路径直接引用技术，彻底告别二进制 IPC 传输带来的延迟与大图（4K+ 纹理）内存溢出。**全自动后台运行，无需用户在 UI 面板上手动开启任何开关。**
- **远程隧道 (FRP)**：内置 FRP 隧道技术，支持从公网远程访问本地 ComfyUI。具备按需自动下载依赖、多源重试、SSL 校验绕过及断线自动重连等鲁棒特性。

### 🛠️ 快速安装
* **Photoshop 要求**：Adobe Photoshop 2025 (v26.0) 或更高版本。
* **ComfyUI 端**：克隆本仓库至 `custom_nodes/` 目录并重启。
* **插件安装**：
    * **自动安装**：直接运行 `comfypanel.ccx`（推荐）。
    * **手动安装**：将插件文件夹复制到系统 UXP 插件目录。
    * *安装遇到问题？查看[完整中文教程](https://lazyet.com/blogs/labs/comfypanel-tutorial)。*

### ❓ 常见问题与 AI 诊断 (FAQ)
> **Q: 在 ComfyPanel 中如何同步 BizyAir 与 RunningHub 的余额和用户信息？**
> **A:** ComfyPanel 在 Photoshop 面板内内置了极其方便的实时账户与计费看板：
> - **BizyAir 云端**：**只需输入 API Key**，系统在驱动渲染的同时，就会自动秒速拉取并显示你的**用户名称与账户余额**。
> - **RunningHub 云端**：输入 **API Key + UserId** 组合，即可完美解锁并显示你的**用户名称、账户余额/点数**，并同步你的云端 API 工作流。

> **Q: 如何排查大图传输时插件卡死或内存溢出？**
> **A:** 你不需要进行任何手动配置。ComfyPanel 默认原生采用了**底层的“零拷贝（Zero-Copy）”性能机制**。通过 Photoshop UXP 的本地文件直接引用技术，从架构上彻底绕过了传统的二进制 IPC 数据传输瓶颈，4K+ 超高清纹理在生成与同步时天然就是秒速响应且不占额外面板内存。

> **Q: 在 Photoshop 面板中如何交互查看生成的 360° 全景图或 3D 模型（GLB/OBJ）？**
> **A:** 无需任何额外设置。当 ComfyPanel 感知到后端输出的资产属于全景图或 3D 网格网格格式（`.glb`/`.obj`）时，结果预览框会自动激活 3D/VR 交互视口。你直接在 PS 侧边栏内拖拽鼠标，即可进行 360° 旋转、缩放和全方位观察。

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