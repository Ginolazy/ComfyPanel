# Changelog

All notable changes to this project will be documented in this file.

## [2.3.1] - 2026-10-14

ComfyPanel v2.3.1

• Loader Enhancer: Added universal support for `none` option in file dropdowns of ComfyUI loader nodes (e.g., `LoadImage`, `LoadAudio`, `LoadVideo`). Automatically bypasses file validation and returns `None` outputs when `none` is selected, enabling multi-input workflows (like Nanobanana, GPT Image, Qwen Image) to selectively pass inputs without breaking or disconnecting nodes.

• Loader 节点增强：为原生及自定义媒体加载节点（如 `LoadImage`、`LoadAudio`、`LoadVideo` 等）的文件下拉菜单首位全局注入 `none` 选项。选择 `none` 时自动放行文件存在性校验并在运行时输出 `None`，完美解决多图/多输入节点（如 Nanobanana、GPT Image、Qwen Image）需要按需传图时不得不频繁手动断开连线的问题。

## [2.3.0] - 2026-10-11

ComfyPanel v2.3.0

• Silent Config & Asset Sync Refactor: Streamlined default app configuration (`default_apps.json`) and workflow manifest synchronization in the Photoshop plugin. Removed dependence on unreliable GitHub API and SHA tracking, switching to direct CDN-based content comparison and atomic file overwrite. Ensures instant, zero-friction updates across domestic and global networks whenever defaults are pushed.

• Image Alignment & Lossless Restore Nodes: Added `ImageMask_Align` and `ImageMask_AlignRestore` nodes (`ComfyPanel/Process & Restore`). Solves image distortion, edge cropping, and pixel shifting caused by non-standard dimensions in ComfyUI workflows (e.g. Qwen, Wan, CogVideo, Inpainting). Pads outward instead of lossy interpolation resizing to meet model alignment requirements (8/16/32/64), and accurately restores the canvas to original dimensions with 1:1 pixel-perfect, distortion-free, and shift-free precision.

• 静默配置与资产同步重构：精简 Photoshop 插件端内置默认应用（`default_apps.json`）及工作流清册的同步机制。彻底移除对易受网络环境限制的 GitHub API 与 SHA 文件比对的依赖，改为直连 CDN 内容比对与文件直接覆盖写入。确保海内外用户在云端配置推送后均能秒级、无感、稳定地同步最新应用及工作流变更。

• 图像尺寸对齐与无损还原节点：在 `ComfyPanel/Process & Restore` 分类下新增 `ImageMask_Align` 与 `ImageMask_AlignRestore` 节点。彻底解决 ComfyUI 工作流中非标尺寸在模型重绘、生图时画面被插值拉伸变糊、边缘被悄悄裁切或多模态/视频模型（如 Qwen、Wan、CogVideo）因非倍数尺寸报错的问题。采用向外居中扩充代替有损重采样缩放，对齐至 8/16/32/64 等模型推荐倍数；配套还原节点保证画面 1:1 绝对不变形、不偏移、无损还原。

## [2.2.0] - 2026-10-01

ComfyPanel v2.2.0

• Turbo Mode: Added `cropLayer` (Crop by Layer Bounds) button, dynamically shown when active document has multiple layers (`layerCount > 1`). Fully aligned with Studio mode's mutual exclusion logic between Selection and Layer cropping.

• Turbo Mode: Fixed an issue where changing crop modes or switching active documents could mistakenly reuse stale RGBA cache from the first execution.

• Result Placement Optimization: Refactored the result insertion logic to prevent unintended stretching or scaling on cutout and transparent images. Auto-insert mode now intelligently places matching canvas images at 1:1 original scale in-place without distortion. Manual insertion continues to fit effective contents to canvas, while Shift+ click reliably restores 1:1 true physical pixel dimensions.

• [PRO] Upload Image Format: Added a new PRO setting to control the image format used when uploading to ComfyUI. Supports WebP (Fast) and PNG. WebP drastically reduces file size and upload time. Non-Pro users default to PNG.

• Prompt Toolbar (Translate & Enhance): Added inline "Translate to EN" and "Enhance to EN" action buttons to multiline prompt inputs in the Photoshop panel, powered by Index-Translate (pure frontend, zero ComfyUI dependency). Supports translating any source language to English, AI prompt enhancement, and smart partial replacement for selected text.

• TextMultiline Node: Upgraded translation and prompt enhancement capabilities powered by Index-Translate, supporting multi-language translation to English (`translate_to_en`), AI prompt enhancement (`enhance_to_en`), and target language translation (`translate_to_target`).

• Turbo 模式：新增 `cropLayer`（按图层边界裁剪）快捷按钮，在多图层文档（图层数 > 1）时按需显示，并与选区裁剪遵循与 Studio 模式一致的互斥逻辑。

• Turbo 模式：修复了切换裁剪模式或切换文档时，可能误用首次运行产生的旧 RGBA 缓存的问题。

• 结果图插回逻辑优化：重构了置入图层变换与缩放逻辑，解决抠图及带透明区域图片插回时异常撑满变形的问题。自动插回模式新增轻智能判定，结果画布与文档一致时自动 1:1 原位贴合；手动点击保持适配撑满画布，Shift+ 点击可无损还原为结果图真实的 1:1 物理像素尺寸。

• [PRO] 上传图片格式：新增 PRO 专属设置，可控制上传至 ComfyUI 时所使用的图片格式。支持 WebP（快速）与 PNG。WebP 可大幅压缩文件体积并缩短上传耗时；非 Pro 用户默认使用 PNG。

• 提示词工具栏（翻译与增强）：在 Photoshop 面板的多行提示词输入框上方新增「翻译为英文 (Translate to EN)」与「AI增强为英文 (Enhance to EN)」按钮，基于 Index-Translate 纯前端直连（不依赖 ComfyUI）。支持任意源语言翻译为英文、AI 提示词智能增强，以及选中的文本局部替换。

• TextMultiline 节点：升级翻译与提示词增强功能，集成开源 Index-Translate 服务，支持多语言翻译为英文（`translate_to_en`）、AI 提示词增强（`enhance_to_en`）以及目标语言翻译（`translate_to_target`）。

## [2.1.0] - 2026-09-30

ComfyPanel v2.1.0

• AnyPause / AnyPreviewPause — Added `always_continue` boolean toggle. When enabled, the node skips the pause and passes data through immediately without interrupting the workflow.

• AnyPause / AnyPreviewPause —— 新增 `always_continue` 布尔开关。开启后节点跳过暂停，数据直接透传，不中断工作流执行。

## [2.0.0] - 2026-09-19

ComfyPanel v2.0.0 - ComfyPanel Turbo Bar Support

• Turbo / Studio Modes — Replaced the previous Express / Expert modes with the new Turbo / Studio experience.

• ComfyPanel Turbo Bar — Added support for the new Turbo Bar, providing a lightweight and streamlined interface for Turbo Mode.

• Separate Component — ComfyPanel Turbo Bar is distributed separately and must be downloaded and installed separately to use Turbo Mode.

[Download ComfyPanel Turbo Bar](https://github.com/Ginolazy/ComfyPanel-Turbo-Bar)

• Turbo / Studio 模式 —— 以全新的 Turbo / Studio 体验取代了此前的 Express / Expert 模式。

• ComfyPanel Turbo Bar —— 新增了对 Turbo Bar 的支持，为 Turbo 模式提供了一个轻量且精简的界面。

• 独立组件 —— ComfyPanel Turbo Bar 作为独立组件发布；若要使用 Turbo 模式，必须单独下载并安装该组件。

[下载 ComfyPanel Turbo Bar](https://github.com/Ginolazy/ComfyPanel-Turbo-Bar)

## [1.8.1] - 2026-09-12

ComfyPanel v1.8.1 - 2026-09-12

• Routine optimizations and bug fixes.

• 日常优化与问题修复。

## [1.8.0] - 2026-09-05

ComfyPanel v1.8.0 - Multi-Session Architecture & System Browser Support

• New System Browser Mode: Connect ComfyPanel directly to ComfyUI running in your default system browser, optimized for multi-monitor and large-screen workflows.

• Panel as a Control Hub: The plugin panel now acts as a dedicated controller and monitor, seamlessly interacting with whichever active workflow you select.

• Isolated Multi-Session Execution: Embedded WebView and System Browser run completely independently, preserving their own distinct canvases and workflows without interference.

• Independent Launch: Open and switch workflows in your target browser directly from the panel, completely safe from accidental canvas overwrites.

ComfyPanel v1.8.0 - 双轨架构升级与系统浏览器支持

• 新增 System Browser 模式：支持将 PS 插件直接连接至系统浏览器中运行的 ComfyUI，完美适配大屏与多显示器工作流。

• 面板控制台化（Control Hub）：插件面板升级为“操控台 + 监视器”，切到哪个工作流，PS 就可以直接与哪个工作流交互。

• 多上下文隔离运行：Embedded WebView 与 System Browser 状态完全独立，各自保留独立的画布与工作流，同时运行互不干扰。

• 自由新建与打开：可在插件面板中直接选择使用目标浏览器打开指定工作流，无需担心相互覆盖或干扰。
