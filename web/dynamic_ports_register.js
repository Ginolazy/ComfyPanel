/** ComfyUI/custom_nodes/ComfyPanel/js/dynamic_ports_register.js **/

import { app } from "../../../scripts/app.js";
import { DynamicPorts } from "./dynamic_ports.js";
import { setupOutputPortSync } from "./preview_pause.js"; // Port synchronization logic, used for all three nodes
import { setupSwitchAnyCombo } from "./switch_any_combo.js";

// ========== Register AnyPause ==========
app.registerExtension({
    name: "ComfyPanel.AnyPause",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "AnyPause") return;

        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "input",
            inputType: "*",
            startIndex: 1
        });
        setupOutputPortSync(nodeType, app);
    },
});

// ========== Register AnyPreview ==========
app.registerExtension({
    name: "ComfyPanel.AnyPreview",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "AnyPreview") return;
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "input",
            inputType: "*",
            startIndex: 1
        });
        setupOutputPortSync(nodeType, app);
    },
});

// ========== Register AnyPreviewPause ==========
app.registerExtension({
    name: "ComfyPanel.AnyPreviewPause",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "AnyPreviewPause") return;
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "input",
            inputType: "*",
            startIndex: 1
        });
        setupOutputPortSync(nodeType, app);
    },
});

// ========== Register AutoMute ==========
app.registerExtension({
    name: "ComfyPanel.AutoMute.DynamicPorts",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "AutoMute") return;
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "control_nodes",
            inputType: "*",
            startIndex: 1
        });
    },
});

// ========== Register ImageMask_SwitchAuto ==========
app.registerExtension({
    name: "ComfyPanel.ImageMask_SwitchAuto",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ImageMask_SwitchAuto") return;
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "image",
            inputType: "IMAGE",
            secondaryInputName: "mask",
            secondaryInputType: "MASK",
            startIndex: 1
        });
    },
});

// ========== Register MakeAnyList ==========
app.registerExtension({
    name: "ComfyPanel.MakeAnyList",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "MakeAnyList") return;
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "input",
            inputType: "*",
            startIndex: 1
        });
    },
});

// ========== Register MakeBatch ==========
app.registerExtension({
    name: "ComfyPanel.MakeMaskBatch",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "MakeBatch") return;
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "input",
            inputType: "*",
            startIndex: 1
        });
    },
});

// ========== Register SwitchAnyCombo ==========
app.registerExtension({
    name: "ComfyPanel.SwitchAnyCombo",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "SwitchAnyCombo") return;
        if (nodeData.input && nodeData.input.optional) {
            const optional = nodeData.input.optional;
            const keysToRemove = [];
            for (const key in optional) {
                if (key === "_mapping" || (key.startsWith("input_") && key !== "input_1")) {
                    keysToRemove.push(key);
                }
            }
            for (const key of keysToRemove) {
                delete optional[key];
            }
        }
        setupSwitchAnyCombo(nodeType);
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "input",
            inputType: "*",
            startIndex: 1
        });
        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            if (origOnNodeCreated) origOnNodeCreated.apply(this, arguments);
            this.updateSwitchAnyComboOptions?.();
            this.setSize(this.computeSize());
        };
    },
});

// ========== Register TextConcat ==========
app.registerExtension({
    name: "ComfyPanel.TextConcat",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "TextConcat") return;
        DynamicPorts.setupDynamicInputs(nodeType, {
            baseInputName: "text",
            inputType: "STRING",
            startIndex: 1
        });
    },
});