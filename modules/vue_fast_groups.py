"""
Vue Fast Groups Muter and Bypasser Nodes
Frontend-only nodes designed for ComfyUI / Vue UI mode.
They expose group toggles without restrictive single-toggle collapsing.
"""

class FastGroupsMuterVue:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {}
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("OPT_CONNECTION",)
    FUNCTION = "passthrough"
    CATEGORY = "ComfyPanel/rgthree (vue)"
    OUTPUT_NODE = True
    DISPLAY_NAME = "Fast Groups Muter (Vue)"
    DESCRIPTION = (
        "Fast Groups Muter (Vue)\n"
        "Group control panel redesigned specifically for the ComfyUI Vue (Nodes 2.0) interface.\n"
        "Seamlessly displays and toggles the Mute/Enable status for all groups on the canvas.\n\n"
        "Special thanks to rgthree for the original Fast Groups Muter node concept."
    )

    def passthrough(self):
        return (None,)

class FastGroupsBypasserVue:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {},
            "optional": {}
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("OPT_CONNECTION",)
    FUNCTION = "passthrough"
    CATEGORY = "ComfyPanel/rgthree (vue)"
    OUTPUT_NODE = True
    DISPLAY_NAME = "Fast Groups Bypasser (Vue)"
    DESCRIPTION = (
        "Fast Groups Bypasser (Vue)\n"
        "Group control panel redesigned specifically for the ComfyUI Vue (Nodes 2.0) interface.\n"
        "Seamlessly displays and toggles the Bypass/Enable status for all groups on the canvas.\n\n"
        "Special thanks to rgthree for the original Fast Groups Bypasser node concept."
    )

    def passthrough(self, OPT_CONNECTION=None):
        return (OPT_CONNECTION,)