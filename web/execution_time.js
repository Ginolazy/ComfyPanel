/** ComfyUI/custom_nodes/ComfyPanel/js/execution_time.js **/
import { api } from "../../../scripts/api.js";
import { app } from "../../../scripts/app.js";

function formatExecutionTime(time) {
    return `${(time / 1000).toFixed(2)}s`;
}

function drawBadge(node, orig, restArgs) {
    let ctx = restArgs[0];
    if (orig) orig.apply(node, restArgs);
    if (!node.flags?.collapsed && node.constructor.title_mode != LiteGraph.NO_TITLE) {
        const t = node.cc_execution_time;
        if (t !== undefined) {
            const text = formatExecutionTime(t);
            ctx.save();
            ctx.font = "12px sans-serif";
            const textSize = ctx.measureText(text);
            const padding = 6;
            ctx.fillStyle = "#0F1F0F";
            ctx.beginPath();
            ctx.roundRect(0, -LiteGraph.NODE_TITLE_HEIGHT - 20, textSize.width + padding * 2, 20, 5);
            ctx.fill();
            ctx.fillStyle = "white";
            ctx.fillText(text, padding, -LiteGraph.NODE_TITLE_HEIGHT - padding);
            ctx.restore();
        }
    }
}

app.registerExtension({
    name: "ComfyPanel.NodeExecutionTime",
    async setup() {
        // === Key: Clear all old execution times before each execution ===
        api.addEventListener("execution_start", () => {
            for (const node of app.graph._nodes) {
                if (node.cc_execution_time !== undefined) {
                    delete node.cc_execution_time;
                }
            }
            app.graph.setDirtyCanvas(true, false);
            console.log("[ComfyPanel] Cleared all previous execution times");
        });

        // Compatibility with old events (if any)
        api.addEventListener("prompt_queued", () => {
            for (const node of app.graph._nodes) {
                if (node.cc_execution_time !== undefined) {
                    delete node.cc_execution_time;
                }
            }
            app.graph.setDirtyCanvas(true, false);
        });

        // Update execution time when each node finishes execution
        api.addEventListener("ComfyPanel.node.executed", ({ detail }) => {
            const node = app.graph.getNodeById(detail.node);
            if (node) {
                node.cc_execution_time = detail.execution_time;
                app.graph.setDirtyCanvas(true, false);
            }
        });
    },

    async nodeCreated(node) {
        if (!node.cc_et_swizzled) {
            const orig = node.onDrawForeground ?? Object.getPrototypeOf(node).onDrawForeground;
            node.onDrawForeground = function (ctx) { drawBadge(node, orig, arguments); };
            node.cc_et_swizzled = true;
        }
    },

    async loadedGraphNode(node) {
        if (!node.cc_et_swizzled) {
            const orig = node.onDrawForeground ?? Object.getPrototypeOf(node).onDrawForeground;
            node.onDrawForeground = function (ctx) { drawBadge(node, orig, arguments); };
            node.cc_et_swizzled = true;
        }
    }
});