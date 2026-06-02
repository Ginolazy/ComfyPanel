/**
 * User Configuration & Node Filtering for Local ComfyUI / 本地 ComfyUI 用户配置与节点过滤
 * Customize how nodes/widgets appear in Photoshop. / 自定义节点/控件在 Photoshop 中的显示方式。
 *
 * widgetType mapping / 控件类型映射：
 * button: Button / 按钮
 * combo: Combo Box / 下拉框
 * number: Number / 数字
 * slider: Slider / 滑块
 * string/customtext: String/Custom Text / 字符串
 * toggle: Toggle / 勾选框
 * 
 * Custom Styles & Rules / 自定义样式与规则说明：
 * 'note_type' or 'note_title': Match Note nodes to display using type or title / 使用 Note 节点的类型或标题来匹配需要显示的 Note 节点
 *   widgets: '*' means show all widgets / '*' 表示显示所有 widget
 * 1. widgets: [{param1}, {param2}, ...] optional parameters / 数组项可选参数：
 *    - widgetName: Matching widget name (supports * wildcard) / 匹配的小部件名称（支持 * 通配符）
 *    - widgetType: Matching widget type (e.g., 'combo', 'number') / 匹配的小部件类型（如 'combo', 'number'）
 *    - hideLabel: true/false, Whether to hide the label / 是否隐藏标签（小部件名称）
 *    - fullWidth: true/false, Whether to take up the full row (hides label automatically) / 是否占满整行（开启后会自动隐藏标签）
 *    - labelWidth: Number (0-100), Custom label percentage width (only if not fullWidth and not hideLabel) / 自定义标签占用的百分比宽度（仅在非 fullWidth 且非 hideLabel 时生效）
 *    - layout: 'grid', Use responsive grid layout for the node (allows multiple widgets per row) / 为该节点开启响应式网格布局（允许一排显示多个参数）
 * 
 * 2. exclude: [{param1}, {param2}, ...] optional parameters / 数组可选参数：
 *    - Format same as 'widgets', matched widgets will be completely hidden / 格式与 widgets 相同，匹配的小部件将被彻底屏蔽
 * 
 * Examples / 示例：
 * { widgetName: 'seed', labelWidth: 30 } // Label 30%, Input 70% / 标签占 30%，输入框占 70%
 * { widgetName: 'APP', hideLabel: true, fullWidth: true } // Full width combo / 全宽下拉菜单
 */

window.userConfig = {
    // Global Settings / 全局设置
    globalSettings: {
        strictMode: true, // Enabled to honor the whitelist/blacklist / 强制启用白名单/黑名单模式
        itemLimit: 100, // Node count limit / 节点数量限制
        forceShowSuffix: '*', // Force show all widgets if title ends with this / 节点 title 以此结尾时，强制显示该节点的所有 widget
        forceHideSuffix: '.', // Force hide all widgets if title ends with this / 节点 title 以此结尾时，强制隐藏该节点的所有 widget
        topIcons: ['🎨', '📁', '⚙️'], // Nodes with titles starting with these icons will be prioritized and full-width / 节点 title 以下列图标开头时，将优先显示并横跨整行
        useSlidersForNumbers: true // true: Add sliders for numbers, false: Input boxes only / true: 数字类型增加滑块，false: 数字类型仅显示输入框
    },

    /**
     * Allowed Nodes (Unified Whitelist) / 允许显示的节点（统一白名单）
     * Keys: Node Type or wildcard like '*rgthree*' / 键：节点类型或通配符，如 '*rgthree*'
     * Values: Object config with 'widgets' array or '*' to allow all / 值：包含 'widgets' 数组的配置对象，或 '*' 表示允许所有
     */
    allowedNodes: {
        /* default / 默认 */
        'Float': { widgets: '*' },
        'Int': { widgets: '*' },
        '*NanoBanana*': {// [NEW] 为本地引擎启用 Smart-Loader 特性：被静音 Bypass 的该类节点将被收纳为 UI 缩略图栏里的 "+" 号添加按钮 / Enable Smart-Loader: bypassed nodes of this type will be grouped into a "+" add button in the UI strip
            widgets: [
                { widgetName: '*' } // Allow all other widgets so they aren't hidden by the whitelist / 允许所有其他小部件，以免被白名单隐藏
            ],
            exclude: [{ widgetName: 'Inputcount' }, { widgetType: 'button' }]
        },
        '*GPT*': {// [NEW] 为本地引擎启用 Smart-Loader 特性：被静音 Bypass 的该类节点将被收纳为 UI 缩略图栏里的 "+" 号添加按钮 / Enable Smart-Loader: bypassed nodes of this type will be grouped into a "+" add button in the UI strip
            widgets: [
                { widgetName: '*' } // Allow all other widgets so they aren't hidden by the whitelist / 允许所有其他小部件，以免被白名单隐藏
            ],
            exclude: [{ widgetName: 'Inputcount' }, { widgetType: 'button' }]
        },
        '*Display*': { widgets: '*' },
        '*Note*': { widgets: '*' },
        '*Show*': { widgets: '*' },
        /* custom / 自定义 */
        'BizyAirWebApp': {
            widgets: [
                { widgetName: 'APP', hideLabel: true, fullWidth: true },
                { widgetName: '*' } // Allow all other widgets so they aren't hidden by the whitelist / 允许所有其他小部件，以免被白名单隐藏
            ],
            exclude: [{ widgetName: 'input_values_json' }]
        },
        'SwitchAny': { widgets: '*' },
        'SwitchOutput': { widgets: '*' },
        'TextMultiline': { widgets: [{ widgetName: 'text' }] }
    }
};


