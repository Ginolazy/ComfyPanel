/** ComfyUI/custom_nodes/ComfyPanel/js/math_operation.js **/
import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "ComfyPanel.MathOperationFloatInt_B_Disable",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        const targetNodes = ["MathOperationFloat", "MathOperationInt"];
        if (!targetNodes.includes(nodeData.name)) return;

        const unaryOps = ["sin", "cos", "tan", "sqrt", "exp", "log", "neg", "abs"];

        const oldOnNodeCreated = nodeType.prototype.onNodeCreated;
        const oldOnConfigure = nodeType.prototype.onConfigure;

        function updateBStatus(node) {
            const opWidget = node.widgets?.find(w => w.name === "operation");
            const bWidget = node.widgets?.find(w => w.name === "B");
            if (!opWidget || !bWidget) return;

            const isUnary = unaryOps.includes(opWidget.value);

            // Gray out and disable B
            bWidget.disabled = isUnary;
            if (bWidget.el) {
                bWidget.el.style.opacity = isUnary ? "0.4" : "1.0";
                bWidget.el.style.pointerEvents = isUnary ? "none" : "auto";
            }
        }

        nodeType.prototype.onNodeCreated = function () {
            if (oldOnNodeCreated) oldOnNodeCreated.apply(this, arguments);
            updateBStatus(this);

            const opWidget = this.widgets.find(w => w.name === "operation");
            if (opWidget) {
                const oldCallback = opWidget.callback;
                opWidget.callback = (...args) => {
                    if (oldCallback) oldCallback.apply(opWidget, args);
                    updateBStatus(this);
                };
            }
        };

        nodeType.prototype.onConfigure = function () {
            if (oldOnConfigure) oldOnConfigure.apply(this, arguments);
            setTimeout(() => updateBStatus(this), 50);
        };
    },
});
