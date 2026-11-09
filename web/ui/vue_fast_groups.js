/** ComfyUI/custom_nodes/ComfyPanel/web/vue_fast_groups.js **/
import { app } from "../../../scripts/app.js";
import { showFastGroupsConfigModal, ensureStyleLoaded } from "./comfypanel_components.js";

// Ensure shared UI stylesheet is loaded
if (typeof document !== 'undefined') {
    ensureStyleLoaded();
}

/**
 * Vue Fast Groups Muter & Bypasser Extension
 * Pure and direct Vue / Nodes 2.0 toggle control for canvas groups.
 */

const MUTER_TYPE = "FastGroupsMuterVue";
const BYPASSER_TYPE = "FastGroupsBypasserVue";

const activeFastGroupNodes = new Set();

// Keep a gentle 500ms sync loop for both Vue mode and LiteGraph Canvas mode
setInterval(() => {
    if (activeFastGroupNodes.size > 0 && app?.graph) {
        const canvas = app.canvas;
        if (!canvas?.selected_group_moving && !canvas?.selected_group_resizing && !canvas?.isDragging) {
            syncAllFastGroups();
        }
    }
}, 500);

function syncAllFastGroups(skipNode = null) {
    if (!app.graph) return;
    for (const node of activeFastGroupNodes) {
        if (!node || node === skipNode) continue;
        if (app.graph._nodes && !app.graph._nodes.includes(node)) {
            activeFastGroupNodes.delete(node);
            continue;
        }
        if (node._refreshVueGroupWidgets) {
            node._refreshVueGroupWidgets();
        }
    }
}

function getGroupNodes(group) {
    if (!group || !app.graph) return [];
    if (window.rgthreeUtils?.getGroupNodes) {
        return window.rgthreeUtils.getGroupNodes(group);
    }
    const bounds = group.getBounding ? group.getBounding() : [group.pos[0], group.pos[1], group.size[0], group.size[1]];
    const gMinX = bounds[0];
    const gMinY = bounds[1];
    const gMaxX = bounds[0] + bounds[2];
    const gMaxY = bounds[1] + bounds[3];

    return (app.graph._nodes || []).filter(node => {
        if (!node.pos || !node.size) return false;
        const nCenterX = node.pos[0] + node.size[0] / 2;
        const nCenterY = node.pos[1] + node.size[1] / 2;
        return nCenterX >= gMinX && nCenterX <= gMaxX && nCenterY >= gMinY && nCenterY <= gMaxY;
    });
}

function setGroupMode(group, isMuter, enable) {
    const nodes = getGroupNodes(group);
    const targetMode = enable ? 0 : (isMuter ? 2 : 4); // 0: Always, 2: Never (Mute), 4: Bypass

    let changed = false;
    nodes.forEach(node => {
        if (node.mode !== targetMode) {
            node.mode = targetMode;
            changed = true;
            if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
        }
    });

    if (app.graph) {
        app.graph.setDirtyCanvas(true, true);
    }
    return changed;
}

function normalizeGroupColor(color) {
    const raw = String(color || "").trim().toLowerCase();
    if (!raw) return "";
    const colors = window.LGraphCanvas?.node_colors || app.canvas?.constructor?.node_colors || {};
    const mapped = colors[raw]?.groupcolor || colors[raw]?.color || raw;
    let gColor = String(mapped || "").replace("#", "").trim().toLowerCase();
    if (!gColor) return "";
    if (gColor.length === 3 && /^[0-9a-f]{3}$/.test(gColor)) {
        gColor = gColor.replace(/(.)(.)(.)/, "$1$1$2$2$3$3");
    }
    if (!/^[0-9a-f]{6}$/.test(gColor)) return "";
    return `#${gColor}`;
}

function normalizeToggleRestriction(node) {
    return String(node?.properties?.toggleRestriction || "default").trim().toLowerCase();
}

function applyToggleRestriction(node, widget, isMuter, desiredValue) {
    const restriction = normalizeToggleRestriction(node);
    const widgets = (node.widgets || []).filter(w => w && w._groupRef);

    let effectiveValue = desiredValue;
    if (restriction === "always one" && desiredValue === false) {
        const hasOtherEnabled = widgets.some(w => w !== widget && w.value === true);
        if (!hasOtherEnabled) {
            effectiveValue = true;
        }
    }

    if (effectiveValue === true && (restriction === "max one" || restriction === "always one")) {
        widgets.forEach(other => {
            if (other !== widget && other.value === true) {
                const oldVal = other.value;
                other.value = false;
                if (other._groupRef) {
                    setGroupMode(other._groupRef, isMuter, false);
                }
                if (node.onWidgetChanged) {
                    node.onWidgetChanged(other.name, false, oldVal, other);
                }
            }
        });
    }

    const prevValue = widget.value;
    widget.value = effectiveValue;

    if (widget._groupRef) {
        setGroupMode(widget._groupRef, isMuter, effectiveValue);
    }
    if (node.onWidgetChanged) {
        node.onWidgetChanged(widget.name, effectiveValue, prevValue, widget);
    }

    if (node.setDirtyCanvas) {
        node.setDirtyCanvas(true, true);
    }
    if (app.graph) {
        app.graph.setDirtyCanvas(true, true);
    }

    syncAllFastGroups(node);
    return effectiveValue;
}

function applyBulkAction(node, isMuter, action) {
    const widgets = (node.widgets || []).filter(w => w && w._groupRef);
    if (!widgets.length) return;

    const restriction = normalizeToggleRestriction(node);
    const onlyOne = restriction.includes(" one");
    const alwaysOne = restriction === "always one";

    if (action === "Mute all" || action === "Bypass all") {
        widgets.forEach((widget, index) => {
            const desiredValue = alwaysOne && index === 0 ? true : false;
            applyToggleRestriction(node, widget, isMuter, desiredValue);
        });
    } else if (action === "Enable all") {
        widgets.forEach((widget, index) => {
            const desiredValue = onlyOne && index > 0 ? false : true;
            applyToggleRestriction(node, widget, isMuter, desiredValue);
        });
    } else if (action === "Toggle all") {
        let foundOne = false;
        widgets.forEach(widget => {
            let newValue = onlyOne && foundOne ? false : !widget.value;
            foundOne = foundOne || newValue;
            applyToggleRestriction(node, widget, isMuter, newValue);
        });
        if (!foundOne && alwaysOne) {
            const lastWidget = widgets[widgets.length - 1];
            if (lastWidget) {
                applyToggleRestriction(node, lastWidget, isMuter, true);
            }
        }
    }

    syncAllFastGroups(node);
}

function filterAndSortGroups(groups, props) {
    let result = [...groups];
    if (props.showAllGraphs === false && app.graph) {
        result = result.filter(group => !group.graph || group.graph === app.graph);
    }
    if (props.matchColors) {
        const rawTokens = props.matchColors.split(',').map(c => c.trim()).filter(Boolean);
        if (rawTokens.length) {
            const filterHex = rawTokens.map(t => normalizeGroupColor(t)).filter(Boolean);
            const filterRaw = rawTokens.map(t => t.toLowerCase());
            result = result.filter(g => {
                const gColor = normalizeGroupColor(g.color);
                const gRaw = String(g.color || '').trim().toLowerCase();
                return (gColor && filterHex.includes(gColor)) ||
                    filterRaw.some(f => f === gRaw || f === gRaw.replace('#', ''));
            });
        }
    }
    if (props.matchTitle && props.matchTitle.trim()) {
        try {
            const rx = new RegExp(props.matchTitle.trim(), 'i');
            result = result.filter(g => rx.test(g.title || ''));
        } catch (e) { }
    }
    const sort = props.sort || "position";
    if (sort === "alphanumeric") {
        result.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    } else if (sort === "custom alphabet" && props.customSortAlphabet) {
        const alpha = props.customSortAlphabet.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
        result.sort((a, b) => {
            const aTitle = (a.title || '').toLowerCase();
            const bTitle = (b.title || '').toLowerCase();
            const aIdx = alpha.findIndex(x => aTitle.startsWith(x));
            const bIdx = alpha.findIndex(x => bTitle.startsWith(x));
            if (aIdx !== -1 && bIdx !== -1) return aIdx - bIdx || aTitle.localeCompare(bTitle);
            if (aIdx !== -1) return -1;
            if (bIdx !== -1) return 1;
            return aTitle.localeCompare(bTitle);
        });
    } else {
        result.sort((a, b) => {
            const posA = a.pos || [0, 0];
            const posB = b.pos || [0, 0];
            return posA[1] - posB[1] || posA[0] - posB[0];
        });
    }
    return result;
}

// Inject HTML nav arrow buttons into Vue node rows
function injectVueNavArrows(node) {
    if (node.id == null) return;
    const nodeEl = document.querySelector(`[data-node-id="${node.id}"]`);
    if (!nodeEl) return;

    if (node.properties?.showNav === false) {
        nodeEl.querySelectorAll('.vfg-nav-arrow').forEach(el => el.remove());
        return;
    }

    const groupWidgets = (node.widgets || []).filter(w => w && w._groupRef);
    if (!groupWidgets.length) return;

    const widgetByName = new Map();
    groupWidgets.forEach(w => widgetByName.set(w.name, w));

    const candidateLabels = nodeEl.querySelectorAll(
        '[data-testid="widget-layout-field-label"], .comfy-vue-widget-label, .widget-label, label, span'
    );

    candidateLabels.forEach(labelEl => {
        const labelText = labelEl.textContent?.trim();
        if (!labelText || !labelText.startsWith("Enable ")) return;
        const widget = widgetByName.get(labelText);
        if (!widget || !widget._groupRef) return;

        const row = labelEl.closest('.comfy-vue-widget, [data-testid="widget-layout-field"], .widget-row') || labelEl.parentElement;
        if (!row || row.querySelector('.vfg-nav-arrow')) return;

        row.classList.add('vfg-row-with-nav');

        const btn = document.createElement('button');
        btn.className = 'vfg-nav-arrow';
        btn.title = `Navigate to "${widget._groupRef.title || ''}"`;
        btn.innerHTML = '&#10132;'; // ➔

        btn.addEventListener('pointerdown', (e) => {
            e.stopPropagation();
            e.preventDefault();
            const canvas = app.canvas;
            if (!canvas || !widget._groupRef) return;
            canvas.centerOnNode(widget._groupRef);
            const gSize = widget._groupRef._size || widget._groupRef.size || [100, 100];
            const z = canvas.ds?.scale || 1;
            const zx = (canvas.canvas.width / (gSize[0] || 100)) - 0.02;
            const zy = (canvas.canvas.height / (gSize[1] || 100)) - 0.02;
            canvas.setZoom(Math.min(z, zx, zy), [canvas.canvas.width / 2, canvas.canvas.height / 2]);
            canvas.setDirty(true, true);
        });

        row.appendChild(btn);
    });
}

function initVueDOMObserver() {
    if (window._vfgDOMObserver) return;

    const updateAllFastGroupNodes = () => {
        if (!app.graph) return;
        const nodes = app.graph._nodes || [];
        for (const n of nodes) {
            if (n && (n.type === MUTER_TYPE || n.type === BYPASSER_TYPE)) {
                injectVueNavArrows(n);
            }
        }
    };

    window._vfgDOMObserver = new MutationObserver((mutations) => {
        for (const m of mutations) {
            if (m.addedNodes.length > 0) {
                updateAllFastGroupNodes();
                break;
            }
        }
    });

    window._vfgDOMObserver.observe(document.body, {
        childList: true,
        subtree: true
    });
}

function initSettingsListener() {
    if (typeof app === 'undefined' || !app.ui?.settings?.addEventListener) return;
    try {
        app.ui.settings.addEventListener("change", (e) => {
            const name = e?.detail?.name || e?.name;
            if (!name || name === "Comfy.VueNodes.Enabled") {
                syncAllFastGroups();
            }
        });
    } catch (_) { }
}

if (typeof document !== 'undefined') {
    initVueDOMObserver();
    initSettingsListener();
}

function isVueMode() {
    if (typeof app !== 'undefined' && app.ui?.settings?.getSettingValue) {
        const val = app.ui.settings.getSettingValue("Comfy.VueNodes.Enabled");
        if (val != null) return !!val;
    }
    if (typeof document !== 'undefined') {
        return !!document.querySelector('.comfy-vue-node, [data-testid="node-widgets"], .lg-node-widgets');
    }
    return false;
}

function fitString(ctx, str, maxWidth) {
    let width = ctx.measureText(str).width;
    const ellipsis = "…";
    const ellipsisWidth = ctx.measureText(ellipsis).width;
    if (width <= maxWidth || width <= ellipsisWidth) return str;
    let lo = 0, hi = str.length;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (ctx.measureText(str.substring(0, mid)).width <= maxWidth - ellipsisWidth) {
            lo = mid;
        } else {
            hi = mid - 1;
        }
    }
    return str.substring(0, lo) + ellipsis;
}

function attachCanvasWidgetBehavior(widget, group) {
    const NAV_W = 28;
    const MARGIN = 15;

    const canvasDraw = function (ctx, node, width, posY, height) {
        const showNav = node.properties?.showNav !== false && !!group;

        // 1. Background rounded rect
        ctx.strokeStyle = LiteGraph.WIDGET_OUTLINE_COLOR || "#444";
        ctx.fillStyle = LiteGraph.WIDGET_BGCOLOR || "#222";
        ctx.beginPath();
        ctx.roundRect(MARGIN, posY, width - MARGIN * 2, height, height * 0.5);
        ctx.fill();
        ctx.stroke();

        let currentX = width - MARGIN;

        // 2. Navigation arrow on far right
        if (showNav) {
            currentX -= 7;
            const midY = posY + height * 0.5;
            ctx.fillStyle = ctx.strokeStyle = "#89A";
            ctx.lineJoin = "round";
            ctx.lineCap = "round";
            const arrow = new Path2D(`M${currentX} ${midY} l -7 6 v -3 h -7 v -6 h 7 v -3 z`);
            ctx.fill(arrow);
            ctx.stroke(arrow);
            currentX -= 14;
            currentX -= 7;

            // Divider line
            ctx.strokeStyle = LiteGraph.WIDGET_OUTLINE_COLOR || "#444";
            ctx.stroke(new Path2D(`M ${currentX} ${posY} v ${height}`));
        }

        currentX -= 7;

        // 3. Toggle switch circle
        ctx.fillStyle = widget.value ? "#89A" : "#333";
        ctx.beginPath();
        const toggleRadius = height * 0.36;
        ctx.arc(currentX - toggleRadius, posY + height * 0.5, toggleRadius, 0, Math.PI * 2);
        ctx.fill();
        currentX -= toggleRadius * 2;

        // 4. Value text ("true" / "false")
        currentX -= 4;
        ctx.font = (LiteGraph.WIDGET_FONT_SIZE || 14) + "px sans-serif";
        ctx.textAlign = "right";
        ctx.fillStyle = widget.value ? (LiteGraph.WIDGET_TEXT_COLOR || "#DDD") : (LiteGraph.WIDGET_SECONDARY_TEXT_COLOR || "#888");
        const valText = widget.value ? "true" : "false";
        ctx.fillText(valText, currentX, posY + height * 0.7);
        currentX -= Math.max(ctx.measureText("true").width, ctx.measureText("false").width);
        currentX -= 7;

        // 5. Truncated Widget Label
        ctx.textAlign = "left";
        const maxLabelWidth = currentX - (MARGIN + 10);
        if (widget.name != null && maxLabelWidth > 0) {
            ctx.fillText(fitString(ctx, widget.name, maxLabelWidth), MARGIN + 10, posY + height * 0.7);
        }
    };

    const canvasMouse = function (event, pos, node) {
        if (event.type !== "pointerdown") return true;

        const showNav = node?.properties?.showNav !== false && !!group;
        const nodeWidth = node.size ? node.size[0] : 300;

        // Check if click is on navigation arrow area (rightmost ~45px)
        const isNearRightEdge = pos[0] >= (nodeWidth - MARGIN - NAV_W);

        if (showNav && isNearRightEdge) {
            const canvas = app.canvas;
            if (canvas) {
                canvas.centerOnNode(group);
                const gSize = group._size || group.size || [100, 100];
                const z = canvas.ds?.scale || 1;
                const zx = (canvas.canvas.width / (gSize[0] || 100)) - 0.02;
                const zy = (canvas.canvas.height / (gSize[1] || 100)) - 0.02;
                canvas.setZoom(Math.min(z, zx, zy), [canvas.canvas.width / 2, canvas.canvas.height / 2]);
                canvas.setDirty(true, true);
            }
            return true;
        }

        // Toggle switch
        const newVal = !widget.value;
        widget.value = newVal;
        if (widget.callback) {
            widget.callback(newVal);
        }
        if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
        if (app.graph) app.graph.setDirtyCanvas(true, true);
        return true;
    };

    // Define dynamic getters: return undefined in Vue mode (so Vue renders native ToggleSwitch),
    // and return canvas functions in LiteGraph Canvas mode.
    Object.defineProperty(widget, "draw", {
        get() {
            return isVueMode() ? undefined : canvasDraw;
        },
        configurable: true,
        enumerable: true
    });

    Object.defineProperty(widget, "mouse", {
        get() {
            return isVueMode() ? undefined : canvasMouse;
        },
        configurable: true,
        enumerable: true
    });

    widget.onPointerDown = function (pointer, node, canvas) {
        if (isVueMode()) return false;
        const showNav = node?.properties?.showNav !== false && !!group;
        const nodeWidth = node?.size ? node.size[0] : 300;
        const graphMouse = canvas?.graph_mouse;
        const localX = (graphMouse && node?.pos) ? (graphMouse[0] - node.pos[0]) : 0;
        const isNearRightEdge = localX >= (nodeWidth - MARGIN - NAV_W);

        if (showNav && isNearRightEdge) {
            canvas.centerOnNode(group);
            const gSize = group._size || group.size || [100, 100];
            const z = canvas.ds?.scale || 1;
            const zx = (canvas.canvas.width / (gSize[0] || 100)) - 0.02;
            const zy = (canvas.canvas.height / (gSize[1] || 100)) - 0.02;
            canvas.setZoom(Math.min(z, zx, zy), [canvas.canvas.width / 2, canvas.canvas.height / 2]);
            canvas.setDirty(true, true);
            return true; // Stop event: prevents ComfyUI from toggling the switch
        }
        return false;
    };
}

function watchGroupTitle(group) {
    if (!group || group._vfgWatchingTitle) return;
    group._vfgWatchingTitle = true;
    let titleVal = group.title;
    Object.defineProperty(group, "title", {
        get() {
            return titleVal;
        },
        set(newVal) {
            const changed = titleVal !== newVal;
            titleVal = newVal;
            if (changed) {
                syncAllFastGroups();
            }
        },
        configurable: true,
        enumerable: true
    });
}

function refreshVueGroupWidgets(node, isMuter) {
    if (!app.graph) return;
    node.properties = node.properties || {};
    let groups = app.graph._groups || [];
    groups = filterAndSortGroups(groups, node.properties);

    node.widgets = node.widgets || [];

    const currentWidgetsMap = new Map();
    node.widgets.forEach(w => {
        if (w._groupRef) {
            currentWidgetsMap.set(w._groupRef, w);
        }
    });

    const newWidgets = [];

    groups.forEach(group => {
        watchGroupTitle(group);
        const groupTitle = group.title || "Unnamed Group";
        const widgetLabel = `Enable ${groupTitle}`;
        const nodes = getGroupNodes(group);
        const isGroupEnabled = nodes.length > 0 ? nodes.some(n => n.mode === 0) : false;

        let widget = currentWidgetsMap.get(group);
        if (!widget) {
            widget = node.addWidget("toggle", widgetLabel, isGroupEnabled, function (val) {
                applyToggleRestriction(node, widget, isMuter, val);
            });
            widget._groupRef = group;
        } else {
            if (widget.name !== widgetLabel) {
                widget.name = widgetLabel;
            }
            if (widget.value !== isGroupEnabled) {
                widget.value = isGroupEnabled;
            }
            widget.callback = function (val) {
                applyToggleRestriction(node, widget, isMuter, val);
            };
        }

        // Attach dynamic canvas widget behavior with getters so it adapts to Vue / Canvas modes on the fly
        attachCanvasWidgetBehavior(widget, group);

        newWidgets.push(widget);
    });

    node.widgets = newWidgets;

    injectVueNavArrows(node);

    if (node.setSize && node.computeSize) {
        const computed = node.computeSize();
        const currentWidth = node.size ? node.size[0] : 0;
        const currentHeight = node.size ? node.size[1] : 0;
        const width = Math.max(currentWidth, computed[0], 270);
        const height = Math.max(currentHeight, computed[1]);
        node.setSize([width, height]);
    }
    if (node.setDirtyCanvas) {
        node.setDirtyCanvas(true, true);
    }
}

function syncVueGroupPortLabels(node) {
    if (!node.outputs) return;
    node.outputs.forEach(output => {
        output.label = "OPT_CONNECTION";
        output.name = "OPT_CONNECTION";
    });
}

function setupFastGroupNode(node, isMuter) {
    activeFastGroupNodes.add(node);
    node._isMuter = isMuter;
    node._refreshVueGroupWidgets = () => refreshVueGroupWidgets(node, isMuter);
    node._applyFastGroupsAction = function (action) {
        applyBulkAction(this, isMuter, action);
    };
    refreshVueGroupWidgets(node, isMuter);
    syncVueGroupPortLabels(node);
}

app.registerExtension({
    name: "ComfyPanel.VueFastGroups",

    async nodeCreated(node) {
        const type = node.type || node.comfyClass;
        if (type === MUTER_TYPE || type === BYPASSER_TYPE) {
            setupFastGroupNode(node, type === MUTER_TYPE);
        }
    },

    async loadedGraphNode(node) {
        const type = node.type || node.comfyClass;
        if (type === MUTER_TYPE || type === BYPASSER_TYPE) {
            setupFastGroupNode(node, type === MUTER_TYPE);
        }
    },

    getNodeMenuItems(node) {
        const type = node.type || node.comfyClass;
        if (type !== MUTER_TYPE && type !== BYPASSER_TYPE) return [];
        const isMuter = type === MUTER_TYPE;
        const actionLabel = isMuter ? "Mute all" : "Bypass all";
        return [
            { content: "⚙️ Fast Groups Settings...", callback: () => showFastGroupsConfigModal(node) },
            null,
            { content: actionLabel, callback: () => node._applyFastGroupsAction?.(actionLabel) },
            { content: "Enable all", callback: () => node._applyFastGroupsAction?.("Enable all") },
            { content: "Toggle all", callback: () => node._applyFastGroupsAction?.("Toggle all") },
        ];
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== MUTER_TYPE && nodeData.name !== BYPASSER_TYPE) return;

        const isMuter = nodeData.name === MUTER_TYPE;
        const prototype = nodeType.prototype;
        prototype.properties = prototype.properties || {};
        prototype.properties.matchColors = "";
        prototype.properties.matchTitle = "";
        prototype.properties.showNav = true;
        prototype.properties.showAllGraphs = true;
        prototype.properties.sort = "position";
        prototype.properties.customSortAlphabet = "";
        prototype.properties.toggleRestriction = "default";

        const origOnNodeCreated = prototype.onNodeCreated;
        prototype.onNodeCreated = function () {
            const res = origOnNodeCreated?.apply(this, arguments);
            setupFastGroupNode(this, isMuter);
            return res;
        };

        const origOnConfigure = prototype.onConfigure;
        prototype.onConfigure = function (info) {
            const res = origOnConfigure?.apply(this, arguments);
            setupFastGroupNode(this, isMuter);
            return res;
        };

        const origOnRemoved = prototype.onRemoved;
        prototype.onRemoved = function () {
            activeFastGroupNodes.delete(this);
            return origOnRemoved?.apply(this, arguments);
        };

        const origOnConnectionsChange = prototype.onConnectionsChange;
        prototype.onConnectionsChange = function (type, index, connected, link_info) {
            const res = origOnConnectionsChange?.apply(this, arguments);
            syncVueGroupPortLabels(this);
            return res;
        };

        // Context menu fallback
        const origGetExtraMenuOptions = prototype.getExtraMenuOptions;
        prototype.getExtraMenuOptions = function (canvas, options) {
            origGetExtraMenuOptions?.apply(this, arguments);
            const actionLabel = isMuter ? "Mute all" : "Bypass all";
            const actionItems = [
                { content: "⚙️ Fast Groups Settings...", callback: () => showFastGroupsConfigModal(this) },
                { content: actionLabel, callback: () => this._applyFastGroupsAction?.(actionLabel) },
                { content: "Enable all", callback: () => this._applyFastGroupsAction?.("Enable all") },
                { content: "Toggle all", callback: () => this._applyFastGroupsAction?.("Toggle all") },
            ];
            actionItems.forEach(item => options.unshift(item));
        };
    }
});
