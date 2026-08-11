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
            "optional": {
                "OPT_CONNECTION": ("*",)
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("OPT_CONNECTION",)
    FUNCTION = "passthrough"
    CATEGORY = "ComfyPanel/rgthree (vue)"
    OUTPUT_NODE = True
    DISPLAY_NAME = "Fast Groups Muter (Vue)"

    def passthrough(self, OPT_CONNECTION=None):
        return (OPT_CONNECTION,)

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

    def passthrough(self, OPT_CONNECTION=None):
        return (OPT_CONNECTION,)