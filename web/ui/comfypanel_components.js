/** ComfyUI/custom_nodes/ComfyPanel/web/ui/comfypanel_components.js **/

// Automatically inject CSS into DOM
export function ensureStyleLoaded() {
    if (document.getElementById("comfypanel-ui-style")) return;
    const link = document.createElement("link");
    link.id = "comfypanel-ui-style";
    link.rel = "stylesheet";
    link.type = "text/css";
    link.href = new URL("./comfypanel_ui.css", import.meta.url).href;
    document.head.appendChild(link);
}

/**
 * Generic base modal dialog factory
 * @param {Object} options
 * @param {String} options.id Unique ID for modal overlay
 * @param {String} options.title Dialog title
 * @param {String} options.badge Badge text in top right
 * @param {String} options.saveText Save button text
 * @param {Function} options.onSave Callback when save button clicked (receives { modal, body, saveBtn })
 */
function createModalBase(options = {}) {
    ensureStyleLoaded();

    const {
        id = "cp-generic-modal",
        title = "Settings",
        badge = "Node",
        saveText = "💾 Save & Close",
        onSave = null
    } = options;

    // Remove existing modal with the same ID
    const oldOverlay = document.getElementById(id);
    if (oldOverlay) oldOverlay.remove();

    const overlay = document.createElement("div");
    overlay.id = id;
    overlay.className = "cp-modal-overlay";

    const modal = document.createElement("div");
    modal.className = "cp-modal";

    // Header
    const header = document.createElement("div");
    header.className = "cp-modal-header";
    header.innerHTML = `
        <span class="cp-modal-title">${title}</span>
        <span class="cp-modal-badge">${badge}</span>
    `;

    // Form body container
    const body = document.createElement("div");
    body.className = "cp-modal-body";

    // Footer actions
    const footer = document.createElement("div");
    footer.className = "cp-modal-footer";

    const cancelBtn = document.createElement("button");
    cancelBtn.className = "cp-btn-cancel";
    cancelBtn.textContent = "Cancel";
    cancelBtn.onclick = () => overlay.remove();

    const saveBtn = document.createElement("button");
    saveBtn.className = "cp-btn-save";
    saveBtn.textContent = saveText;

    saveBtn.onclick = async () => {
        if (typeof onSave === "function") {
            saveBtn.disabled = true;
            saveBtn.textContent = "Saving...";
            try {
                await onSave({ modal, body, saveBtn, overlay });
            } catch (e) {
                console.error("[ComfyPanelUI] Modal save error:", e);
            } finally {
                saveBtn.disabled = false;
                saveBtn.textContent = saveText;
            }
        }
        overlay.remove();
    };

    footer.appendChild(cancelBtn);
    footer.appendChild(saveBtn);
    modal.appendChild(header);
    modal.appendChild(body);
    modal.appendChild(footer);
    overlay.appendChild(modal);

    return {
        overlay,
        modal,
        body,
        open: () => document.body.appendChild(overlay),
        close: () => overlay.remove()
    };
}

/**
 * Password input group helper with plaintext/ciphertext (👁️/🙈) toggle
 */
function createPasswordGroup(options = {}) {
    const {
        label = "API Key",
        value = "",
        placeholder = "Enter Key...",
        tip = "Saved to comfy.settings.json",
        inputId = "cp-input-key"
    } = options;

    const group = document.createElement("div");
    group.className = "cp-form-group";

    group.innerHTML = `
        <label class="cp-form-label">${label}</label>
        <div class="cp-input-group">
            <input id="${inputId}" type="password" value="${value}" placeholder="${placeholder}" class="cp-input" />
            <button type="button" class="cp-toggle-btn">👁️</button>
        </div>
        ${tip ? `<span class="cp-form-tip">${tip}</span>` : ""}
    `;

    const input = group.querySelector(`#${inputId}`);
    const toggleBtn = group.querySelector(".cp-toggle-btn");

    toggleBtn.onclick = () => {
        if (input.type === "password") {
            input.type = "text";
            toggleBtn.textContent = "🙈";
        } else {
            input.type = "password";
            toggleBtn.textContent = "👁️";
        }
    };

    return group;
}

// ============================================================================
// Exported Configuration Modal Dialogs
// ============================================================================

/**
 * Open RunningHub generic configuration modal dialog
 */
export async function showConfigModal(options = {}) {
    const { node, title = "☁️ RunningHub Settings", showAppList = false } = options;

    let currentApiKey = node?.properties?.runninghub_api_key || "";
    let currentBaseUrl = node?.properties?.runninghub_base_url || "https://www.runninghub.cn";
    let currentAppList = node?.properties?.app_list || "";

    let configData = { apiKeyZh: "", apiKeyEn: "" };
    try {
        const res = await fetch("/comfypanel/runninghub/get_config");
        const data = await res.json();
        if (data && data.success) {
            configData = data;
            if (data.baseUrl) currentBaseUrl = data.baseUrl;
            currentApiKey = currentBaseUrl.includes(".ai") ? data.apiKeyEn : data.apiKeyZh;
        }
    } catch (e) {
        console.warn("[ComfyPanelUI] Failed to fetch RH config:", e);
    }

    const { overlay, body, open } = createModalBase({
        id: "cp-config-modal-overlay",
        title,
        badge: node?.type || "Node",
        onSave: async ({ body }) => {
            const apiKeyInput = body.querySelector("#cp-modal-apikey");
            const baseUrlSelect = body.querySelector("#cp-modal-baseurl");
            const appListInput = body.querySelector("#cp-modal-applist");

            const newApiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
            const newBaseUrl = baseUrlSelect ? baseUrlSelect.value : "https://www.runninghub.cn";
            const newAppList = appListInput ? appListInput.value.trim() : "";

            if (node && node.properties) {
                node.properties.runninghub_base_url = newBaseUrl;
                if (showAppList) node.properties.app_list = newAppList;
                delete node.properties.runninghub_api_key;

                if (typeof node.onPropertyChanged === "function") {
                    node.onPropertyChanged("runninghub_base_url", newBaseUrl);
                    if (showAppList) node.onPropertyChanged("app_list", newAppList);
                }
            }

            await fetch("/comfypanel/runninghub/save_config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ apiKey: newApiKey, baseUrl: newBaseUrl })
            });

            if (showAppList && window.globalAppListManager) {
                window.globalAppListManager.refresh();
            }
        }
    });

    // 1. API Key
    const keyGroup = createPasswordGroup({
        label: "RunningHub API Key",
        value: currentApiKey,
        placeholder: "Enter API Key...",
        inputId: "cp-modal-apikey"
    });
    body.appendChild(keyGroup);

    // 2. Base URL
    const urlGroup = document.createElement("div");
    urlGroup.className = "cp-form-group";
    urlGroup.innerHTML = `
        <label class="cp-form-label">Base URL Domain</label>
        <select id="cp-modal-baseurl" class="cp-select">
            <option value="https://www.runninghub.cn" ${currentBaseUrl.includes(".cn") ? "selected" : ""}>https://www.runninghub.cn (China)</option>
            <option value="https://www.runninghub.ai" ${currentBaseUrl.includes(".ai") ? "selected" : ""}>https://www.runninghub.ai (Global)</option>
        </select>
    `;
    body.appendChild(urlGroup);

    // Sync: Switching domain dropdown automatically updates API key input value
    const keyInput = keyGroup.querySelector("#cp-modal-apikey");
    const urlSelect = urlGroup.querySelector("#cp-modal-baseurl");
    urlSelect.onchange = () => {
        keyInput.value = urlSelect.value.includes(".ai") ? configData.apiKeyEn : configData.apiKeyZh;
    };

    // 3. Optional App List (RHWebApp)
    if (showAppList) {
        const appGroup = document.createElement("div");
        appGroup.className = "cp-form-group";
        appGroup.innerHTML = `
            <label class="cp-form-label">Custom App ID List (Line/Comma Separated)</label>
            <textarea id="cp-modal-applist" rows="4" placeholder="e.g. 1823912903123912039&#10;1920391203912039102" class="cp-textarea"></textarea>
        `;
        body.appendChild(appGroup);
        setTimeout(() => {
            const ta = appGroup.querySelector("#cp-modal-applist");
            if (ta) ta.value = currentAppList;
        }, 0);
    }

    open();
}

/**
 * Open AutoMute configuration modal dialog
 */
export async function showAutoMuteConfigModal(node) {
    const props = node?.properties || {};
    const currentMatchTitle = props.matchTitle || "";
    const currentMatchCase = !!props.matchCase;
    const currentMatchExact = !!props.matchExact;
    const currentConnectedOnly = props.connectedOnly !== undefined ? !!props.connectedOnly : true;

    const { body, open } = createModalBase({
        id: "cp-automute-modal-overlay",
        title: "🎛️ AutoMute Rules Config",
        badge: "AutoMute",
        saveText: "💾 Save & Apply",
        onSave: async ({ body }) => {
            const titleInput = body.querySelector("#cp-automute-matchtitle");
            const caseInput = body.querySelector("#cp-automute-matchcase");
            const exactInput = body.querySelector("#cp-automute-matchexact");
            const connectedInput = body.querySelector("#cp-automute-connectedonly");

            if (node && node.properties) {
                node.properties.matchTitle = titleInput ? titleInput.value.trim() : "";
                node.properties.matchCase = caseInput ? caseInput.checked : false;
                node.properties.matchExact = exactInput ? exactInput.checked : false;
                node.properties.connectedOnly = connectedInput ? connectedInput.checked : true;

                if (typeof node.onPropertyChanged === "function") {
                    node.onPropertyChanged("matchTitle", node.properties.matchTitle);
                    node.onPropertyChanged("matchCase", node.properties.matchCase);
                    node.onPropertyChanged("matchExact", node.properties.matchExact);
                    node.onPropertyChanged("connectedOnly", node.properties.connectedOnly);
                } else {
                    if (typeof node.refreshMonitoredNodes === "function") node.refreshMonitoredNodes();
                    if (typeof node.updateMuteState === "function") node.updateMuteState();
                }
            }
        }
    });

    const createCheckboxGroup = (id, labelText, checked) => {
        const grp = document.createElement("div");
        grp.className = "cp-form-group";
        grp.style.cssText = "flex-direction: row; align-items: center; justify-content: space-between;";
        grp.innerHTML = `
            <label class="cp-form-label" style="margin:0;">${labelText}</label>
            <input id="${id}" type="checkbox" ${checked ? "checked" : ""} style="cursor:pointer;" />
        `;
        return grp;
    };

    // 1. Match Title Group
    const titleGroup = document.createElement("div");
    titleGroup.className = "cp-form-group";
    titleGroup.innerHTML = `
        <label class="cp-form-label">Target Titles / Groups (Comma Separated)</label>
        <input id="cp-automute-matchtitle" type="text" value="${currentMatchTitle}" placeholder="e.g. Sampler, FLUX, KSampler" class="cp-input" />
        <span class="cp-form-tip">Matches group titles or node names</span>
    `;

    body.appendChild(titleGroup);
    body.appendChild(createCheckboxGroup("cp-automute-matchcase", "Match Case", currentMatchCase));
    body.appendChild(createCheckboxGroup("cp-automute-matchexact", "Match Exact Name", currentMatchExact));
    body.appendChild(createCheckboxGroup("cp-automute-connectedonly", "Control Links First", currentConnectedOnly));

    open();
}

/**
 * Open BizyAir configuration modal dialog
 */
export async function showBizyAirConfigModal(node) {
    let currentApiKey = "";
    let currentAppList = node?.properties?.app_list || "";

    try {
        const res = await fetch("/bizyair_webapp/get_config");
        const data = await res.json();
        if (data && data.success && data.apiKey) {
            currentApiKey = data.apiKey;
        }
    } catch (e) {
        console.warn("[BizyAirUI] Failed to fetch config:", e);
    }

    const { body, open } = createModalBase({
        id: "cp-bizyair-modal-overlay",
        title: "☁️ BizyAir App Settings",
        badge: node?.type || "BizyAirWebApp",
        onSave: async ({ body }) => {
            const apiKeyInput = body.querySelector("#cp-bizyair-apikey");
            const appListInput = body.querySelector("#cp-bizyair-applist");

            const newApiKey = apiKeyInput ? apiKeyInput.value.trim() : "";
            const newAppList = appListInput ? appListInput.value.trim() : "";

            if (node && node.properties) {
                node.properties.app_list = newAppList;
                delete node.properties.bizyair_api_key;

                if (typeof node.onPropertyChanged === "function") {
                    node.onPropertyChanged("app_list", newAppList);
                }
            }

            await fetch("/bizyair_webapp/save_config", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ apiKey: newApiKey })
            });
        }
    });

    // 1. API Key
    const keyGroup = createPasswordGroup({
        label: "BizyAir API Key",
        value: currentApiKey,
        placeholder: "Enter BizyAir API Key...",
        inputId: "cp-bizyair-apikey"
    });
    body.appendChild(keyGroup);

    // 2. App List
    const appGroup = document.createElement("div");
    appGroup.className = "cp-form-group";
    appGroup.innerHTML = `
        <label class="cp-form-label">Custom App ID List (Line/Comma Separated)</label>
        <textarea id="cp-bizyair-applist" rows="4" placeholder="e.g. 56109&#10;56110" class="cp-textarea"></textarea>
    `;
    body.appendChild(appGroup);

    setTimeout(() => {
        const ta = appGroup.querySelector("#cp-bizyair-applist");
        if (ta) ta.value = currentAppList;
    }, 0);

    open();
}

/**
 * Open Fast Groups (Vue) configuration modal dialog (supports all rgthree filter & sort options)
 */
export async function showFastGroupsConfigModal(node) {
    if (!node) return;
    node.properties = node.properties || {};
    const currentMatchColors = node.properties.matchColors || "";
    const currentMatchTitle = node.properties.matchTitle || "";
    const currentShowNav = node.properties.showNav !== undefined ? !!node.properties.showNav : true;
    const currentShowAllGraphs = node.properties.showAllGraphs !== undefined ? !!node.properties.showAllGraphs : true;
    const currentSort = node.properties.sort || "position";
    const currentCustomSortAlphabet = node.properties.customSortAlphabet || "";
    const currentToggleRestriction = node.properties.toggleRestriction || "default";
    const { body, open } = createModalBase({
        id: "cp-fast-groups-modal-overlay",
        title: "⚙️ Fast Groups Settings",
        badge: node.type || "FastGroupsVue",
        onSave: async ({ body }) => {
            const matchColors = body.querySelector("#cp-fg-matchcolors")?.value?.trim() || "";
            const matchTitle = body.querySelector("#cp-fg-matchtitle")?.value?.trim() || "";
            const showNav = !!body.querySelector("#cp-fg-shownav")?.checked;
            const showAllGraphs = !!body.querySelector("#cp-fg-showallgraphs")?.checked;
            const sort = body.querySelector("#cp-fg-sort")?.value || "position";
            const customSortAlphabet = body.querySelector("#cp-fg-customsort")?.value?.trim() || "";
            const toggleRestriction = body.querySelector("#cp-fg-restriction")?.value || "default";
            node.properties.matchColors = matchColors;
            node.properties.matchTitle = matchTitle;
            node.properties.showNav = showNav;
            node.properties.showAllGraphs = showAllGraphs;
            node.properties.sort = sort;
            node.properties.customSortAlphabet = customSortAlphabet;
            node.properties.toggleRestriction = toggleRestriction;
            if (typeof node.onPropertyChanged === "function") {
                node.onPropertyChanged("matchColors", matchColors);
                node.onPropertyChanged("matchTitle", matchTitle);
                node.onPropertyChanged("showNav", showNav);
                node.onPropertyChanged("showAllGraphs", showAllGraphs);
                node.onPropertyChanged("sort", sort);
                node.onPropertyChanged("customSortAlphabet", customSortAlphabet);
                node.onPropertyChanged("toggleRestriction", toggleRestriction);
            }
            if (typeof node._refreshVueGroupWidgets === "function") {
                node._refreshVueGroupWidgets();
            }
            if (app.graph) {
                app.graph.setDirtyCanvas(true, true);
            }
        }
    });
    const createInputGroup = (id, label, value, placeholder = "") => {
        const div = document.createElement("div");
        div.className = "cp-form-group";
        div.innerHTML = `
            <label class="cp-form-label">${label}</label>
            <input id="${id}" type="text" value="${value}" placeholder="${placeholder}" class="cp-input" />
        `;
        return div;
    };
    const createSelectGroup = (id, label, options, selectedValue) => {
        const div = document.createElement("div");
        div.className = "cp-form-group";
        const optsHtml = options.map(o => `<option value="${o.value}" ${o.value === selectedValue ? "selected" : ""}>${o.label}</option>`).join("");
        div.innerHTML = `
            <label class="cp-form-label">${label}</label>
            <select id="${id}" class="cp-select">${optsHtml}</select>
        `;
        return div;
    };
    const createCheckboxGroup = (id, label, checked) => {
        const div = document.createElement("div");
        div.className = "cp-form-group cp-form-group-checkbox";
        div.innerHTML = `
            <label class="cp-checkbox-label">
                <input id="${id}" type="checkbox" ${checked ? "checked" : ""} class="cp-checkbox" />
                <span>${label}</span>
            </label>
        `;
        return div;
    };
    body.appendChild(createInputGroup("cp-fg-matchcolors", "matchColors (Group colors filter, comma-separated)", currentMatchColors, "e.g. red, pale_blue, #a4d399"));
    body.appendChild(createInputGroup("cp-fg-matchtitle", "matchTitle (Group title regex/string filter)", currentMatchTitle, "e.g. KSampler, FLUX"));
    body.appendChild(createCheckboxGroup("cp-fg-shownav", "showNav (Show quick navigation buttons)", currentShowNav));
    body.appendChild(createCheckboxGroup("cp-fg-showallgraphs", "showAllGraphs (Include groups in all subgraphs)", currentShowAllGraphs));

    body.appendChild(createSelectGroup("cp-fg-sort", "sort (Group sorting rule)", [
        { value: "position", label: "position (Canvas physical position)" },
        { value: "alphanumeric", label: "alphanumeric (Alphabetical / numerical order)" },
        { value: "custom alphabet", label: "custom alphabet (Custom alphabet rules)" }
    ], currentSort));
    body.appendChild(createInputGroup("cp-fg-customsort", "customSortAlphabet (Custom alphabet order rules)", currentCustomSortAlphabet, "e.g. sdxl,pro,sd,n,p"));

    body.appendChild(createSelectGroup("cp-fg-restriction", "toggleRestriction (Toggle restriction mode)", [
        { value: "default", label: "default (No restrictions)" },
        { value: "max one", label: "max one (At most one active)" },
        { value: "always one", label: "always one (Always keep exactly one active)" }
    ], currentToggleRestriction));
    open();
}
