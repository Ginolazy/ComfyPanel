/** ComfyUI/custom_nodes/ComfyPanel/js/switch_any_combo.js **/

export function setupSwitchAnyCombo(nodeType) {
    nodeType.prototype.updateSwitchAnyComboOptions = function () {
        if (!this.inputs || !this.widgets) return;
        const widget = this.widgets.find(w => w.name === "selected");
        if (!widget) return;
        const comboOptions = [];
        this._portToLabelMap = {};
        this._labelToPortMap = {};
        const displayNameCounts = {};
        const tempItems = [];
        for (const input of this.inputs) {
            if (input.name.startsWith("input_")) {
                input.label = input.name;

                if (input.link !== null) {
                    let nodeName = "Unknown Node";
                    const linkInfo = this.graph?.links[input.link];
                    if (linkInfo) {
                        const sourceNode = this.graph.getNodeById(linkInfo.origin_id);
                        if (sourceNode) nodeName = sourceNode.title || sourceNode.type;
                    }
                    const displayName = nodeName;
                    displayNameCounts[displayName] = (displayNameCounts[displayName] || 0) + 1;
                    tempItems.push({ displayName, portName: input.name });
                }
            }
        }
        const displayNamesUsed = {};
        for (const item of tempItems) {
            let uniqueName = item.displayName;
            if (displayNameCounts[item.displayName] > 1) {
                displayNamesUsed[item.displayName] = (displayNamesUsed[item.displayName] || 0) + 1;
                uniqueName = `${item.displayName} (${displayNamesUsed[item.displayName]})`;
            }
            comboOptions.push(uniqueName);
            this._labelToPortMap[uniqueName] = item.portName;
            this._portToLabelMap[item.portName] = uniqueName;
        }
        if (comboOptions.length === 0) {
            comboOptions.push("input_1");
            this._labelToPortMap["input_1"] = "input_1";
            this._portToLabelMap["input_1"] = "input_1";
        }

        // Update input labels to match the friendly names
        for (const input of this.inputs) {
            if (input.name.startsWith("input_")) {
                const friendlyName = this._portToLabelMap[input.name];
                if (friendlyName) {
                    input.label = friendlyName;
                } else {
                    input.label = input.name;
                }
            }
        }

        widget.options.values = comboOptions;
        if (!widget._origSerializeValue) {
            widget._origSerializeValue = widget.serializeValue;
        }
        widget.serializeValue = () => {
            const val = widget.value;
            return this._labelToPortMap?.[val] || val;
        };
        const currentVal = widget.value;
        if (currentVal && currentVal.startsWith("input_")) {
            const friendlyName = this._portToLabelMap[currentVal];
            if (friendlyName) {
                widget.value = friendlyName;
            }
        } else if (!comboOptions.includes(currentVal)) {
            widget.value = comboOptions[0];
        }
        if (this.setDirtyCanvas) this.setDirtyCanvas(true, true);
    };
    const origOnConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
        if (origOnConfigure) origOnConfigure.apply(this, arguments);
        requestAnimationFrame(() => {
            this.updateSwitchAnyComboOptions?.();
        });
    };
    const origOnConnectionsChange = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function (type) {
        if (origOnConnectionsChange) origOnConnectionsChange.apply(this, arguments);
        if (type === 1) {
            setTimeout(() => this.updateSwitchAnyComboOptions?.(), 50);
        }
    };
}
