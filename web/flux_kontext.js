import { app } from "../../scripts/app.js";

/**
 * FluxKontext Node Extension
 * Handles dynamic widget visibility (e.g., solid_color input)
 */

app.registerExtension({
    name: "ComfyPanel.FluxKontext",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "FluxKontextImageCompensate") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                const node = this;

                // Function to update visibility
                this.updateVisibility = function () {
                    const paddingWidget = node.widgets.find(w => w.name === "comp_mode");
                    if (!paddingWidget) return;

                    const isSolidColor = paddingWidget.value === "Solid Color";
                    const targetWidgetName = "solid_color";

                    const targetWidget = node.widgets.find(w => w.name === targetWidgetName);
                    if (targetWidget) {
                        targetWidget.disabled = !isSolidColor;
                    }

                    // Redraw to show disabled state
                    node.setDirtyCanvas(true, true);
                };

                // Finds widgets and Setup Callback
                setTimeout(() => {
                    const paddingWidget = node.widgets.find(w => w.name === "comp_mode");
                    if (paddingWidget) {
                        const originalCallback = paddingWidget.callback;
                        paddingWidget.callback = (value) => {
                            node.updateVisibility();
                            if (originalCallback) {
                                originalCallback.call(paddingWidget, value);
                            }
                        };
                        // Initial update
                        node.updateVisibility();
                    }
                }, 50);

                return r;
            };
        }
    }
});
