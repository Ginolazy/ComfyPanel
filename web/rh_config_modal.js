/** ComfyUI/custom_nodes/ComfyPanel/web/rh_config_modal.js **/

import { showConfigModal as showSharedModal } from "./ui/comfypanel_components.js";

export async function showRHConfigModal(node) {
    const isWebApp = node && node.type === "RHWebApp";
    return showSharedModal({
        node: node,
        title: isWebApp ? "☁️ RunningHub App Settings" : "☁️ RunningHub Workflow Settings",
        showAppList: isWebApp
    });
}
