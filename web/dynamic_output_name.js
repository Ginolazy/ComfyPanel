/** ComfyUI/custom_nodes/ComfyPanel/web/dynamic_output_name.js **/

import { app } from "../../../scripts/app.js";

function updateNodeAnyTypeOutput(node, newType) {
    if (!node || !newType || newType === "*") return;

    for (const output of node.outputs || []) {
        if (output?.type === "*") {
            output.type = newType;
            output.name = newType.toLowerCase();
            output.label = newType;
        }
    }

    app.canvas.setDirty(true);
}

function extendAnyTypeNode(nodeType, nodeData) {
    const oldOnConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
        if (oldOnConnectionsChange) oldOnConnectionsChange.apply(this, arguments);
        if (type !== 1 || !connected || !link_info) return;

        const originNode = app.graph.getNodeById(link_info.origin_id);
        const originType = originNode?.outputs[link_info.origin_slot]?.type || originNode?.outputs[link_info.origin_slot]?.label;
        if (originType && originType !== "*") updateNodeAnyTypeOutput(this, originType);
    };

    const oldOnConstructed = nodeType.prototype.onConstructed;
    nodeType.prototype.onConstructed = function () {
        if (oldOnConstructed) oldOnConstructed.apply(this, arguments);
        const firstLinkedInput = this.inputs?.find(i => i?.link && app.graph.links[i.link]);
        if (!firstLinkedInput) return;

        const link = app.graph.links[firstLinkedInput.link];
        const originNode = app.graph.getNodeById(link.origin_id);
        const originType = originNode?.outputs[link.origin_slot]?.type || originNode?.outputs[link.origin_slot]?.label;
        if (originType && originType !== "*") updateNodeAnyTypeOutput(this, originType);
    };
}

app.registerExtension({
    name: "DynamicAnyTypeOutputName",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const hasAnyType =
            (nodeData.output && nodeData.output.some(o => o === "*")) ||
            (nodeData.RETURN_TYPES && nodeData.RETURN_TYPES.some(t => t === "*"));

        if (hasAnyType) extendAnyTypeNode(nodeType, nodeData);
    },
});
