# Changelog

All notable changes to this project will be documented in this file.

## [2.3.7] - 2026-10-29

ComfyPanel v2.3.7

• Security Patch (ComfyUI-Manager #3418 Round 2): Added media file extension whitelist to `upload_from_path` to prevent arbitrary files from being copied into `input/` and served via `/view`. Confirmed all round-1 and round-2 compliance requirements are addressed.

• Crop-by-Selection Fix: Fixed a bug where crop mode fell back to canvas when multiple load nodes were present. Primary node is now always `mediaNodes[0]` (workflow order), and the crop button state is read directly from the DOM with consistent string ID comparison.

• Result Preview Fix: Removed the `thumbnailUrl` HTTP fallback that caused 403 errors in the Photoshop UXP panel. Result images now load directly from their local `file://` path.

• 安全合规补丁（#3418 第二轮）：为 `upload_from_path` 增加媒体扩展名白名单，防止系统文件通过该接口被复制到 `input/` 后经 `/view` 外泄。全量确认第一、二轮合规要求均已覆盖。

• 选区裁剪模式修复：修复多 Load 节点时裁剪模式回退为画布的问题。首图固定为 `mediaNodes[0]`（工作流顺序），裁剪状态统一从 DOM 按钮直接读取，消除了 String/Number ID 类型不匹配的根因。

• 结果预览修复：删除 `thumbnailUrl` HTTP 降级逻辑（UXP 中 Origin 为 null 导致 403）。结果图现在直接以本地 `file://` 路径渲染。

## [2.3.6] - 2026-10-28

ComfyPanel v2.3.6

• Security Hardening & ComfyUI-Manager Alignment: Addressed all security and ecosystem compliance requirements from ComfyUI-Manager review (#3418). Confined file reads/writes using `os.path.realpath` and `os.path.commonpath`, strictly isolated CORS bypass exclusively to Photoshop UXP `file://` origin, masked API keys in responses, and enforced strict host whitelisting on cloud proxy endpoints.

• Remote Tunnel Cleanup & Security Policy Compliance: In strict compliance with ComfyUI-Manager security guidelines and to eliminate external binary security risks, the experimental built-in `frpc` binary downloader and tunnel daemon routes have been removed. This eliminates untrusted executable downloads while keeping ComfyPanel pure and lightweight. Remote ComfyUI access remains fully supported by connecting client-side to any user-hosted URL (e.g. Cloudflare Tunnel, Tailscale, self-hosted FRP, or LAN).

• 安全加固与规范对齐：全量修复并对齐 ComfyUI-Manager 官方收录规范（#3418）。对所有文件读写操作严格实施 `realpath` 与 `commonpath` 目录越界限制，严格将跨域检查隔离至 Photoshop UXP 的 `file://` 协议，对配置接口中的 API Key 进行脱敏，并对云端代理主机实施严格白名单校验。

• 内网穿透模块精简与安全合规说明：为严格遵守 ComfyUI-Manager 官方生态安全规范，杜绝从网络自动下载并执行未经校验的外部第三方二进制文件（`frpc`）所带来的潜在安全隐患，我们彻底移除了实验性的内置 `frpc` 隧道守护进程及管理路由，以保证插件核心的纯粹与系统运行安全。远程访问需求不受影响：用户仍可作为客户端，通过连接任意外部自建隧道（如 Cloudflare Tunnel、Tailscale、自建 FRP 等）或局域网地址顺畅使用 ComfyPanel。

## [2.3.5] - 2026-10-27

ComfyPanel v2.3.5

• Prompt AI Service & Universal OpenAI-Compatible Endpoint: Added a configurable Prompt AI Service in Global Settings, decoupled from the ComfyUI backend. Supports switching between the official free online service (powered by Index-Translate-35B-A3B) and custom endpoints (supporting API Key / Authorization, universally compatible with OpenAI, Claude, Gemini, DeepSeek, Groq, Ollama, llama.cpp, vLLM, etc.) with a built-in one-click connection test.

• Multimodal Vision Prompt Enhancement (Pro): Exclusive for Pro users. When enhancing prompts with reference images present, thumbnails of active loader nodes are automatically bound and sent to multimodal vision models. If an inpainting selection/mask is present, it is dynamically composited as a semi-transparent quick mask, allowing the AI to accurately locate the exact editing target area and surrounding context for pixel-perfect, photorealistic prompt expansions. Visual tags (`图1`, `图2`...) are automatically rendered in node titles to clearly map user references.

• 提示词 AI 服务与通用 OpenAI 兼容端点：在全局设置中新增独立的“提示词 AI 服务”配置，纯前端直连且与 ComfyUI 后端完全解耦。支持在官方“免费在线 API”（接入 Index-Translate-35B-A3B）与“自定义端点”（支持配置 API 密钥 Authorization，通用兼容 OpenAI、Claude、Gemini、DeepSeek、Groq、Ollama、vLLM 等国际与本地主流平台）之间自由切换，并提供一键连接测试。

• 多模态参考图与选区视觉感知增强 (Pro)：Pro 用户专享支持。点击“增强”时自动抓取当前活跃载入节点的缩略图作为多模态上下文；若存在重绘选区/蒙版（Mask），前端将以类似 Photoshop 快速蒙版的半透红色高亮实时合成传入，让 AI 模型精准看懂具体框选的是哪个肢体或物体部位，结合主体、光影与周围环境进行像素级精准扩写，彻底告别局部重绘时模型对编辑区域的凭空猜测。并在载入节点标题前展示 `图1`、`图2` 等直观徽标，让多图编辑逻辑清晰对齐。

## [2.3.4] - 2026-10-22

ComfyPanel v2.3.4

• Prompt Toolbar — Version History Navigation: Added `‹` / `›` arrow buttons to the prompt toolbar. The buttons are hidden by default and appear automatically after the first Translate or Enhance action. Clicking `‹` restores the previous version; `›` re-applies the next. Manual edits between AI actions are preserved in the stack with forward history trimmed on new operations. State is scoped to the textarea lifetime (no persistence).

• Prompt 工具栏 — 版本历史导航：为 Prompt 工具栏新增 `‹` / `›` 箭头按钮，默认隐藏，首次执行翻译或增强操作后自动显示。点击 `‹` 可回退至上一版本，点击 `›` 可恢复下一版本。AI 操作之间的手动编辑也会计入版本栈，执行新操作时自动截断前向历史。版本状态仅在当前 textarea 生命周期内有效，刷新后清空。

## [2.3.3] - 2026-10-22

ComfyPanel v2.3.3

• Documentation & Extension Registry Mapping: Updated documentation and README assets. Submitted official ComfyUI-Manager node class mappings to enable node discovery and indexing in the Manager registry.

• 文档与节点映射收录：更新说明文档及 README。为 ComfyUI-Manager 提交了官方节点类别映射，使 ComfyPanel 的自定义节点能被 Manager 正确索引并完整展示节点列表。

## [2.3.2] - 2026-10-19

ComfyPanel v2.3.2

• Media Asset Lock Fix: Fixed a bug where locked media assets (images, video, audio) lost their preview after switching apps or workflows. Locked assets now seamlessly follow slot order (slot 0 → slot 0, slot 1 → slot 1, ...) across any workflow switch, consistent with how mask state has always worked globally.

• Auto-Insert Mask Fix: Fixed a regression where auto-inserting results no longer created a layer mask from the active selection. The mask was previously only applied in canvas capture mode; it now correctly applies in all capture modes (canvas, layer, selection) whenever a selection is present at run time.

• 媒体资产锁定修复：修复锁定后切换 App / 工作流时媒体预览（图像、视频、音频）丢失的问题。锁定的媒体资产现在按槽位顺序（槽位 0 → 槽位 0，槽位 1 → 槽位 1，...）无缝流转至新工作流对应节点，行为与遮罩全局状态保持一致。

• 自动插回蒙版修复：修复了自动插回结果图时不再自动基于当前选区添加图层蒙版的回归性问题。此前蒙版创建仅在画布捕获模式（canvas）下生效；现已修正为任意捕获模式（canvas / layer / selection）下，只要运行时存在有效选区，均能正确创建蒙版。

• Multi-Load Layer Placement Fix: Fixed a bug where auto-insert with layer capture + crop-by-layer mode would fall back to canvas-fill placement when multiple LoadImage nodes were present. The primary node's layer bounds are now locked in at run time and correctly used as the placement target for all auto-inserted results.

• 多 LoadImage 节点图层置入修复：修复在"取图层图 + crop by layer"模式下，存在多个 LoadImage 节点时自动插回回退为撑满画布的问题。现已在运行时正确锁定首图节点的图层包围盒，并将其用于所有自动插回结果图的置入定位。

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
