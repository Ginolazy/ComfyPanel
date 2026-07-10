"""
ComfyPanel Serves the web UI and provides local file upload endpoint to bypass binary IPC.
"""

try:
    import folder_paths
except Exception as e:
    folder_paths = None
    print(f"[ComfyPanel] folder_paths unavailable during import: {e}")

try:
    from .modules.utility import (Pytorch_Fix_IntelMac, comfypanel_api)
except Exception as e:
    Pytorch_Fix_IntelMac = None
    comfypanel_api = None
    print(f"[ComfyPanel] Optional utility import failed during startup: {e}")

"""
ComfyPanel Custom Node for comfyui
"""
import os
import importlib.util
import inspect
import re
import sys
from collections import defaultdict
from importlib import metadata as importlib_metadata

try:
    from packaging.version import Version as _Version
except Exception:
    _Version = None

plugin_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(plugin_dir)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "./web"
__version__ = "1.2.8"

def _parse_version(version):
    if _Version is not None:
        return _Version(str(version))
    return tuple(int(part) for part in re.findall(r"\d+", str(version)))

def _get_installed_version(package):
    candidates = [package, package.lower(), package.replace("_", "-"), package.replace("_", "-").lower()]
    for candidate in candidates:
        try:
            return importlib_metadata.version(candidate)
        except importlib_metadata.PackageNotFoundError:
            continue
    raise importlib_metadata.PackageNotFoundError(package)

def _module_dependency_available(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False

def _dependencies_available(dependencies):
    if not dependencies:
        return True
    if isinstance(dependencies, str):
        dependencies = [dependencies]
    return all(_module_dependency_available(dep) for dep in dependencies)

def _get_required_dependencies(module_obj, node_cls):
    for candidate in (
        getattr(node_cls, "REQUIRED_DEPENDENCIES", None),
        getattr(module_obj, "REQUIRED_DEPENDENCIES", None),
    ):
        if candidate:
            if isinstance(candidate, str):
                return [candidate]
            return list(candidate)
    return []

def check_dependencies():
    required_packages = {
        "torch": "2.0.0",
        "torchvision": "0.15.0",
        "numpy": "1.24.0",
        "Pillow": "9.0.0",
        "kornia": "0.7.0",
        "scipy": "1.10.0",
        "requests": "2.28.0"
    }

    missing_packages = []
    outdated_packages = []

    for package, min_version in required_packages.items():
        try:
            installed_version = _get_installed_version(package)
            if _parse_version(installed_version) < _parse_version(min_version):
                outdated_packages.append(package)
        except importlib_metadata.PackageNotFoundError:
            missing_packages.append(package)

    if missing_packages or outdated_packages:
        for package in missing_packages:
            print(f"[\033[91mComfyPanel\033[0m] Cannot import core module: '{package}'")
        if outdated_packages:
            print(f"[\033[91mComfyPanel\033[0m] Requires newer versions of: {', '.join(outdated_packages)}")

    return True

check_dependencies()

py_dir = os.path.join(plugin_dir, "modules")
if os.path.isdir(py_dir):
    for filename in filter(lambda f: f.endswith(".py") and f != "__init__.py", os.listdir(py_dir)):
        module_path = os.path.join(py_dir, filename)
        module_name = filename[:-3]

        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec and (module := importlib.util.module_from_spec(spec)):
                module.__package__ = "modules"

                module_required_dependencies = getattr(module, "REQUIRED_DEPENDENCIES", None)
                if module_required_dependencies and not _dependencies_available(module_required_dependencies):
                    missing = [dep for dep in ([module_required_dependencies] if isinstance(module_required_dependencies, str) else module_required_dependencies) if not _module_dependency_available(dep)]
                    print(f"[ComfyPanel] Skipping module {module_name}: missing {', '.join(missing)}")
                    continue

                spec.loader.exec_module(module)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if hasattr(obj, "INPUT_TYPES") and hasattr(obj, "FUNCTION"):
                        required_dependencies = _get_required_dependencies(module, obj)
                        if required_dependencies and not _dependencies_available(required_dependencies):
                            missing = [dep for dep in required_dependencies if not _module_dependency_available(dep)]
                            print(f"[ComfyPanel] Skipping node {name}: missing {', '.join(missing)}")
                            continue
                        NODE_CLASS_MAPPINGS[name] = obj
                        NODE_DISPLAY_NAME_MAPPINGS[name] = getattr(obj, "DISPLAY_NAME", name)
        except Exception as e:
            print(f"[ComfyPanel] Failed to load module {module_name}: {str(e)}")
else:
    print(f"[ComfyPanel] Directory not found: {py_dir}")

category_map = defaultdict(list)
for name, cls in NODE_CLASS_MAPPINGS.items():
    category = getattr(cls, "CATEGORY", "Other")
    display_name = getattr(cls, "DISPLAY_NAME", name)
    category_map[category].append((name, cls, display_name))

NODE_CLASS_MAPPINGS.clear()
NODE_DISPLAY_NAME_MAPPINGS.clear()
for cat in sorted(category_map.keys(), key=lambda x: x.lower()):
    for name, cls, display_name in category_map[cat]:
        NODE_CLASS_MAPPINGS[name] = cls
        NODE_DISPLAY_NAME_MAPPINGS[name] = display_name

js_dir = os.path.join(plugin_dir, "web")
if not os.path.exists(js_dir):
    print(f"[ComfyPanel] Directory not found: {js_dir}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]