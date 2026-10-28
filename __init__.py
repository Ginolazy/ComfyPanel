"""
ComfyPanel: Serves the web UI, registers custom nodes, and exposes the bridge API.
"""
import os
import inspect
import importlib
from .modules.utility import comfypanel_api, loader_enhancer

WEB_DIRECTORY = "./web"
__version__ = "2.3.7"

plugin_dir = os.path.dirname(os.path.realpath(__file__))
py_dir = os.path.join(plugin_dir, "modules")

NODE_CLASS_MAPPINGS = {

    "AnyPause": None,
    "AnyPreview": None,
    "AnyPreviewPause": None,
    "AutoMute": None,
    "MakeAnyList": None,
    "PrimitivePlus": None,
    "SwitchAny": None,
    "SwitchAnyCombo": None,
    "SwitchAnyMute": None,
    "SwitchAuto": None,
    "SwitchOutput": None,

    "CropByMask": None,
    "CropByMaskRestore": None,
    "ImageConcat": None,
    "ImageConcatRestore": None,
    "ImageMask_Scale": None,
    "ImageMask_ScaleRestore": None,
    "ImageMask_Align": None,
    "ImageMask_AlignRestore": None,

    "RHWebApp": None,
    "RHWorkflow": None,
    "BizyAirWebApp": None,

    "FastGroupsBypasserVue": None,
    "FastGroupsMuterVue": None,

    "BlendByMask": None,
    "ImageMask_Composite": None,
    "ImageMask_Constrain": None,
    "ImageMask_Swap": None,
    "ImageMask_Switch": None,
    "ImageMask_SwitchAuto": None,
    "ImageMask_Transform": None,

    "ImageBatchToImageList": None,
    "ImageBlank": None,
    "ImageFilterAdjustments": None,
    "ImageListToImageBatch": None,
    "ImageRemoveAlpha": None,
    "ImageSwap": None,
    "MakeBatch": None,
    "ScaleAny": None,
    "SwitchMaskAuto": None,

    "Float": None,
    "Int": None,
    "MathOperation": None,
    "ShowText": None,
    "StringListToString": None,
    "TextConcat": None,
    "TextMultiline": None,
}

DYNAMIC_NODES = {}
DYNAMIC_DISPLAY = {}

if os.path.isdir(py_dir):
    for filename in sorted(os.listdir(py_dir)):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = f".modules.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name, package=__package__)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if hasattr(obj, "INPUT_TYPES") and hasattr(obj, "FUNCTION"):
                        DYNAMIC_NODES[name] = obj
                        DYNAMIC_DISPLAY[name] = getattr(obj, "DISPLAY_NAME", name)
            except Exception:
                pass

NODE_CLASS_MAPPINGS.update(DYNAMIC_NODES)
NODE_CLASS_MAPPINGS = {k: v for k, v in NODE_CLASS_MAPPINGS.items() if v is not None}
NODE_DISPLAY_NAME_MAPPINGS = DYNAMIC_DISPLAY

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]