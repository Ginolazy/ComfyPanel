/**
 * User Configuration for Local ComfyUI
 *
 * Tip: Ask an AI assistant to modify this file for you.
 * Manual editing is not recommended.
 * 
 * Configuration rules:
 * - globalSettings controls global behavior.
 * - allowedNodes controls which node types are shown.
 * - Node keys support * as a wildcard.
 * - widgets: '*' allows all widgets.
 * - widgets can match by widgetName or widgetType (button, combo, number, slider, string, toggle).
 * - exclude hides widgets matched by the same rules.
 * - hideLabel hides the widget label.
 * - fullWidth makes the widget span the full row.
 * - labelWidth sets the label width as a percentage.
 * - layout: 'grid' enables multiple widgets per row.
 * - forceShowSuffix / forceHideSuffix are used to temporarily show or hide nodes.
 */

window.userConfig = {
    globalSettings: {
        strictMode: true,
        itemLimit: 100,
        forceShowSuffix: '*',
        forceHideSuffix: '.',
        topIcons: ['🎨', '📁', '⚙️'],
        useSlidersForNumbers: true
    },

    allowedNodes: {
        'Float': { widgets: '*' },
        'Int': { widgets: '*' },
        '*Display*': { widgets: '*' },
        '*Note*': { widgets: '*' },
        '*Show*': { widgets: '*' },
        '*Banana*': {
            widgets: [{ widgetName: '*' }],
            exclude: [{ widgetName: 'Inputcount' }, { widgetType: 'button' }]
        },
        '*Gpt*': {
            widgets: [{ widgetName: '*' }],
            exclude: [{ widgetName: 'Inputcount' }, { widgetType: 'button' }]
        },
        'BizyAirWebApp': {
            widgets: [{ widgetName: 'APP', hideLabel: true, fullWidth: true }, { widgetName: '*' }],
            exclude: [{ widgetName: 'input_values_json' }, { widgetType: 'button' }]
        },
        'RHWebApp': {
            widgets: [{ widgetName: 'APP', hideLabel: true, fullWidth: true }, { widgetName: '*' }],
            exclude: [{ widgetName: 'input_values_json' }, { widgetType: 'button' }]
        },

        // Custom
        'SwitchAny': { widgets: '*' },
        'SwitchOutput': { widgets: '*' },
        'KSampler': { widgets: '*' },
        'TextMultiline': {
            widgets: [{ widgetName: 'text' }]
        }
    }
};