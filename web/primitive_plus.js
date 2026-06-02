/** ComfyUI/custom_nodes/ComfyPanel/js/primitive_plus.js **/
import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "PrimitivePlus",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "PrimitivePlus") {
            const origOnNodeCreated = nodeType.prototype.onNodeCreated;
            const origOnConnectionsChange = nodeType.prototype.onConnectionsChange;
            const origSerialize = nodeType.prototype.serialize;
            const origConfigure = nodeType.prototype.configure;

            nodeType.prototype.onNodeCreated = function () {
                if (origOnNodeCreated) origOnNodeCreated.apply(this, arguments);
                if (!this.outputs || this.outputs.length === 0) {
                    this.addOutput("connect_to_widget_input_1", "*");
                } else if (this.outputs.length > 1) {
                    this.outputs.length = 1;
                }
                this.connectionState = {};
                this.properties = this.properties || {};
                this.properties.portLabels = this.properties.portLabels || {};
                this.size = [this.size[0], 32]; // Initial size
                const origOnResize = this.onResize;
                this.onResize = function (newSize) {
                    if (origOnResize) origOnResize.apply(this, arguments);
                    this.updateLabelsForWidth();
                };
                setTimeout(() => {
                    this.managePorts();
                }, 10);
                this.onWidgetChange = function (outputName, value) {
                    const connection = this.connectionState[outputName];
                    if (connection) {
                        const targetNode = app.graph.getNodeById(connection.nodeId);
                        if (targetNode && targetNode.widgets) {
                            const targetWidget = targetNode.widgets.find(w => w.name === connection.inputName);
                            if (targetWidget) {
                                targetWidget.value = value;
                                if (targetWidget.callback) {
                                    targetWidget.callback(value, targetWidget, targetNode);
                                }
                                targetNode.setDirtyCanvas(true, true);
                            }
                        }
                    }
                    return value;
                };
            };

            // --- Serialization ---
            nodeType.prototype.serialize = function () {
                const o = origSerialize ? origSerialize.apply(this, arguments) : {};
                if (o.widgets) {
                    o.widgets = o.widgets.filter(w => !w.name || !w.name.startsWith("connect_to_widget_input_"));
                    if (o.widgets.length === 0) {
                        delete o.widgets;
                    }
                }
                return o;
            };

            // --- Configuration / Restore ---
            nodeType.prototype.configure = function (o) {
                if (origConfigure) origConfigure.apply(this, arguments);
                if (o.outputs && this.outputs && this.outputs.length > o.outputs.length) {
                    this.outputs.length = o.outputs.length;
                }
                if (this.widgets) {
                    for (let i = this.widgets.length - 1; i >= 0; i--) {
                        if (this.widgets[i].name && this.widgets[i].name.startsWith("connect_to_widget_input_")) {
                            this.widgets.splice(i, 1);
                        }
                    }
                }
                if (this.properties.portLabels) {
                    for (let i = 0; i < this.outputs.length; i++) {
                        if (this.properties.portLabels[i]) {
                            this.outputs[i].label = this.truncatePortLabel(this.properties.portLabels[i]);
                        }
                    }
                }
                setTimeout(() => {
                    this.managePorts();
                    this.refreshWidgets();
                }, 50);
            };

            // --- Port Management ---
            nodeType.prototype.managePorts = function () {
                if (!this.outputs) this.outputs = [];
                let lastConnectedIndex = -1;
                for (let i = 0; i < this.outputs.length; i++) {
                    if (this.isOutputConnected(i)) {
                        lastConnectedIndex = i;
                    }
                }
                const neededPorts = lastConnectedIndex + 2; // e.g. if 0 is connected, we need index 0 and 1. so 2 ports.
                while (this.outputs.length < neededPorts) {
                    const idx = this.outputs.length + 1;
                    this.addOutput(`connect_to_widget_input_${idx}`, "*");
                }
                while (this.outputs.length > neededPorts && this.outputs.length > 1) {
                    const removeIdx = this.outputs.length - 1;
                    if (this.properties.portLabels) {
                        delete this.properties.portLabels[removeIdx];
                    }
                    this.removeOutput(removeIdx);
                }
                for (let i = 0; i < this.outputs.length; i++) {
                    if (this.properties.portLabels[i]) {
                        const truncatedLabel = this.truncatePortLabel(this.properties.portLabels[i]);
                        if (this.outputs[i].label !== truncatedLabel) {
                            this.outputs[i].label = truncatedLabel;
                        }
                    }
                }
            };

            // --- Widget Reconstruction ---
            nodeType.prototype.refreshWidgets = function () {
                if (this.widgets) {
                    for (let i = this.widgets.length - 1; i >= 0; i--) {
                        const w = this.widgets[i];
                        if (w.name && w.name.startsWith("connect_to_widget_input_")) {
                            const portExists = this.outputs && this.outputs.some(o => o.name === w.name);
                            if (!portExists) {
                                this.removeLocalWidget(w.name);
                            }
                        }
                    }
                }
                for (let i = 0; i < this.outputs.length; i++) {
                    const output = this.outputs[i];
                    const outputName = output.name;

                    if (!this.isOutputConnected(i)) {
                        this.removeLocalWidget(outputName);
                        continue;
                    }
                    const linkId = output.links[0]; // Assuming single link for simplicity, or grab first valid
                    const link = app.graph.links[linkId];
                    if (!link) continue;
                    const targetNode = app.graph.getNodeById(link.target_id);
                    if (!targetNode) continue;
                    const targetInput = targetNode.inputs[link.target_slot];
                    if (!targetInput) continue;
                    let targetWidget = null;
                    if (targetNode.widgets) {
                        targetWidget = targetNode.widgets.find(w => w.name === targetInput.name);
                    }
                    if (targetWidget) {
                        let existingWidget = this.findWidgetByName(outputName);
                        if (!existingWidget) {
                            this.createLocalWidget(outputName, targetWidget, targetNode);
                            if (!this.properties.portLabels[i]) {
                                const tTitle = targetNode.title || targetNode.type;
                                let fullLabel = `${tTitle}: ${targetInput.name}`;
                                this.properties.portLabels[i] = fullLabel; // Save full label
                                this.outputs[i].label = this.truncatePortLabel(fullLabel); // Display truncated
                            } else {
                                this.outputs[i].label = this.truncatePortLabel(this.properties.portLabels[i]);
                            }
                        } else {
                            this.outputs[i].label = this.truncatePortLabel(this.properties.portLabels[i]);
                        }
                    } else {
                        this.removeLocalWidget(outputName);
                    }
                }
                this.sortWidgets();
                if (this.computeSize) {
                    try {
                        const minSize = this.computeSize();
                        const currentSize = this.size;
                        this.setSize([
                            Math.max(currentSize[0], minSize[0]),
                            Math.max(currentSize[1], minSize[1])
                        ]);
                    } catch (e) { }
                }
                this.setDirtyCanvas(true, true);
            };

            // --- Sorting & Sizing ---
            nodeType.prototype.sortWidgets = function () {
                if (!this.widgets) return;
                this.widgets.sort((a, b) => {
                    const getIdx = (name) => {
                        const match = name.match(/connect_to_widget_input_(\d+)/);
                        return match ? parseInt(match[1]) : 99999;
                    };
                    return getIdx(a.name) - getIdx(b.name);
                });
            };

            // --- Weight labels ---
            nodeType.prototype.computeTruncatedLabel = function (fullLabel, margin = 16, charWidth = 10) {
                if (!fullLabel) return "";
                const nodeWidth = this.size[0] || 210;
                const portWidth = 10;
                const availableWidth = nodeWidth - margin - portWidth;
                const maxChars = Math.floor(availableWidth / charWidth);
                if (fullLabel.length <= maxChars) return fullLabel;
                return "..." + fullLabel.slice(-maxChars + 3);
            };
            nodeType.prototype.truncateWidgetLabel = function (fullLabel) {
                return this.computeTruncatedLabel(fullLabel, 32, 10);
            };
            nodeType.prototype.truncatePortLabel = function (fullLabel) {
                return this.computeTruncatedLabel(fullLabel, 10, 7);
            };
            // UPort labels
            nodeType.prototype.updateLabelsForWidth = function () {
                if (!this.outputs || !this.properties.portLabels) return;
                for (let i = 0; i < this.outputs.length; i++) {
                    if (this.properties.portLabels[i]) {
                        this.outputs[i].label = this.truncatePortLabel(this.properties.portLabels[i]);
                        const outputName = this.outputs[i].name;
                        const widget = this.findWidgetByName(outputName);
                        if (widget) {
                            widget.label = this.truncateWidgetLabel(this.properties.portLabels[i]);
                        }
                    }
                }
                this.setDirtyCanvas(true, true);
            };
            nodeType.prototype.findWidgetByName = function (name) {
                if (!this.widgets) return null;
                return this.widgets.find(w => w.name === name);
            }
            nodeType.prototype.removeLocalWidget = function (name) {
                if (!this.widgets) return;
                const idx = this.widgets.findIndex(w => w.name === name);
                if (idx !== -1) {
                    const w = this.widgets[idx];
                    if (w.inputEl) {
                        try { w.inputEl.remove(); } catch (e) { }
                    }
                    if (w.element) {
                        try { w.element.remove(); } catch (e) { }
                    }
                    this.widgets.splice(idx, 1);
                    const portIdx = this.outputs.findIndex(o => o.name === name);
                    if (portIdx !== -1) {
                        this.outputs[portIdx].label = null;
                        delete this.properties.portLabels[portIdx];
                    }
                }
            };

            nodeType.prototype.createLocalWidget = function (name, targetWidget, targetNode) {
                let options = { ...targetWidget.options };
                const isCombo = targetWidget.type === "combo" || Array.isArray(options.values);
                const isNumber = targetWidget.type === "number" || typeof targetWidget.value === "number";
                const isBoolean = targetWidget.type === "toggle" || typeof targetWidget.value === "boolean";

                this.connectionState[name] = {
                    nodeId: targetNode.id,
                    slot: null,
                    inputName: targetWidget.name
                };

                let w;
                const self = this;
                const callbackViaState = (v) => self.onWidgetChange(name, v);
                const callbackDirect = (v) => {
                    targetWidget.value = v;
                    if (targetWidget.callback) {
                        targetWidget.callback(v, app.canvas, targetNode, app.canvas.getPointerPos());
                    }
                    targetNode.setDirtyCanvas(true, true);
                };

                if (isCombo) {
                    w = this.addWidget("combo", name, targetWidget.value, callbackDirect, options);
                } else if (isBoolean) {
                    w = this.addWidget("toggle", name, targetWidget.value, callbackViaState, options);
                } else if (isNumber) {
                    w = this.addWidget("number", name, targetWidget.value, callbackDirect, options);
                } else {
                    if (targetWidget.type === "customtext" || options?.multiline) {
                        options.multiline = true;
                        const widgetObj = ComfyWidgets["STRING"](this, name, ["STRING", options], app);
                        w = widgetObj.widget;
                        w.value = targetWidget.value;
                        w.callback = callbackDirect;
                    } else {
                        w = this.addWidget("string", name, targetWidget.value, callbackDirect, options);
                    }
                }
                const wLabel = targetWidget.label || targetWidget.name;
                const portIdx = this.outputs.findIndex(o => o.name === name);
                if (portIdx !== -1 && this.properties.portLabels[portIdx]) {
                    w.fullLabel = this.properties.portLabels[portIdx];
                    w.label = this.truncateWidgetLabel(w.fullLabel);
                } else {
                    w.label = wLabel;
                }
                return w;
            };

            // --- Event Handlers ---
            nodeType.prototype.onConnectionsChange = function (type, index, connected, link_info) {
                if (origOnConnectionsChange) origOnConnectionsChange.apply(this, arguments);
                if (type !== 2) return;
                try {
                    this.managePorts();
                    setTimeout(() => {
                        try { this.refreshWidgets(); } catch (e) { }
                    }, 20);
                } catch (e) {
                }
            };

        }
    }
});
