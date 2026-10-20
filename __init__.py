"""
ComfyPanel: Serves the web UI, registers custom nodes, and exposes the bridge API.
"""
import os
import inspect
import importlib
from .modules.utility import comfypanel_api, loader_enhancer

WEB_DIRECTORY = "./web"
__version__ = "2.3.2"

plugin_dir = os.path.dirname(os.path.realpath(__file__))
py_dir = os.path.join(plugin_dir, "modules")

DYNAMIC_NODES = {}
DYNAMIC_DISPLAY = {}

if os.path.isdir(py_dir):
    for filename in sorted(os.listdir(py_dir)):
        if filename.endswith(".py") and filename != "__init__.py" and filename != "third_party.py":
            module_name = f".modules.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name, package=__package__)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if hasattr(obj, "INPUT_TYPES") and hasattr(obj, "FUNCTION"):
                        DYNAMIC_NODES[name] = obj
                        DYNAMIC_DISPLAY[name] = getattr(obj, "DISPLAY_NAME", name)
            except Exception:
                pass

NODE_CLASS_MAPPINGS = {

    "AnyPause": DYNAMIC_NODES.get("AnyPause"),
    "AnyPreview": DYNAMIC_NODES.get("AnyPreview"),
    "AnyPreviewPause": DYNAMIC_NODES.get("AnyPreviewPause"),
    "AutoMute": DYNAMIC_NODES.get("AutoMute"),
    "MakeAnyList": DYNAMIC_NODES.get("MakeAnyList"),
    "PrimitivePlus": DYNAMIC_NODES.get("PrimitivePlus"),
    "SwitchAny": DYNAMIC_NODES.get("SwitchAny"),
    "SwitchAnyCombo": DYNAMIC_NODES.get("SwitchAnyCombo"),
    "SwitchAnyMute": DYNAMIC_NODES.get("SwitchAnyMute"),
    "SwitchAuto": DYNAMIC_NODES.get("SwitchAuto"),
    "SwitchOutput": DYNAMIC_NODES.get("SwitchOutput"),

    "CropByMask": DYNAMIC_NODES.get("CropByMask"),
    "CropByMaskRestore": DYNAMIC_NODES.get("CropByMaskRestore"),
    "ImageConcat": DYNAMIC_NODES.get("ImageConcat"),
    "ImageConcatRestore": DYNAMIC_NODES.get("ImageConcatRestore"),
    "ImageMask_Scale": DYNAMIC_NODES.get("ImageMask_Scale"),
    "ImageMask_ScaleRestore": DYNAMIC_NODES.get("ImageMask_ScaleRestore"),
    "ImageMask_Align": DYNAMIC_NODES.get("ImageMask_Align"),
    "ImageMask_AlignRestore": DYNAMIC_NODES.get("ImageMask_AlignRestore"),

    "RHWebApp": DYNAMIC_NODES.get("RHWebApp"),
    "RHWorkflow": DYNAMIC_NODES.get("RHWorkflow"),
    "BizyAirWebApp": DYNAMIC_NODES.get("BizyAirWebApp"),

    "FastGroupsBypasserVue": DYNAMIC_NODES.get("FastGroupsBypasserVue"),
    "FastGroupsMuterVue": DYNAMIC_NODES.get("FastGroupsMuterVue"),

    "BlendByMask": DYNAMIC_NODES.get("BlendByMask"),
    "ImageMask_Composite": DYNAMIC_NODES.get("ImageMask_Composite"),
    "ImageMask_Constrain": DYNAMIC_NODES.get("ImageMask_Constrain"),
    "ImageMask_Swap": DYNAMIC_NODES.get("ImageMask_Swap"),
    "ImageMask_Switch": DYNAMIC_NODES.get("ImageMask_Switch"),
    "ImageMask_SwitchAuto": DYNAMIC_NODES.get("ImageMask_SwitchAuto"),
    "ImageMask_Transform": DYNAMIC_NODES.get("ImageMask_Transform"),

    "ImageBatchToImageList": DYNAMIC_NODES.get("ImageBatchToImageList"),
    "ImageBlank": DYNAMIC_NODES.get("ImageBlank"),
    "ImageFilterAdjustments": DYNAMIC_NODES.get("ImageFilterAdjustments"),
    "ImageListToImageBatch": DYNAMIC_NODES.get("ImageListToImageBatch"),
    "ImageRemoveAlpha": DYNAMIC_NODES.get("ImageRemoveAlpha"),
    "ImageSwap": DYNAMIC_NODES.get("ImageSwap"),
    "MakeBatch": DYNAMIC_NODES.get("MakeBatch"),
    "ScaleAny": DYNAMIC_NODES.get("ScaleAny"),
    "SwitchMaskAuto": DYNAMIC_NODES.get("SwitchMaskAuto"),

    "Float": DYNAMIC_NODES.get("Float"),
    "Int": DYNAMIC_NODES.get("Int"),
    "MathOperation": DYNAMIC_NODES.get("MathOperation"),
    "ShowText": DYNAMIC_NODES.get("ShowText"),
    "StringListToString": DYNAMIC_NODES.get("StringListToString"),
    "TextConcat": DYNAMIC_NODES.get("TextConcat"),
    "TextMultiline": DYNAMIC_NODES.get("TextMultiline"),
}

NODE_CLASS_MAPPINGS.update({k: v for k, v in DYNAMIC_NODES.items() if k not in NODE_CLASS_MAPPINGS})
NODE_DISPLAY_NAME_MAPPINGS = DYNAMIC_DISPLAY

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]