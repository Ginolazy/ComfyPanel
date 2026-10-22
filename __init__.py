"""
ComfyPanel: Serves the web UI, registers custom nodes, and exposes the bridge API.
"""
import os
import inspect
import importlib
from .modules.utility import comfypanel_api, loader_enhancer

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "./web"
__version__ = "2.3.3"

plugin_dir = os.path.dirname(os.path.realpath(__file__))
py_dir = os.path.join(plugin_dir, "modules")

if os.path.isdir(py_dir):
    for filename in sorted(os.listdir(py_dir)):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = f".modules.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name, package=__package__)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if hasattr(obj, "INPUT_TYPES") and hasattr(obj, "FUNCTION"):
                        NODE_CLASS_MAPPINGS[name] = obj
                        NODE_DISPLAY_NAME_MAPPINGS[name] = getattr(obj, "DISPLAY_NAME", name)
            except Exception:
                pass

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]