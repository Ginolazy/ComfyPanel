import inspect
import folder_paths
import nodes

orig_filter = folder_paths.filter_files_content_types
folder_paths.filter_files_content_types = lambda files, types: ["none"] + [f for f in orig_filter(files, types) if f != "none"]

orig_exists = folder_paths.exists_annotated_filepath
folder_paths.exists_annotated_filepath = lambda name: True if name == "none" else orig_exists(name)

def _patch_method(cls, name, null_value_fn):
    attr = inspect.getattr_static(cls, name, None)
    if not attr:
        return
    is_cm = isinstance(attr, classmethod)
    orig_fn = attr.__func__ if is_cm else getattr(cls, name)

    if is_cm:
        def patched(cls_, *args, **kwargs):
            if "none" in args or "none" in kwargs.values():
                return null_value_fn()
            return orig_fn(cls_, *args, **kwargs)
        setattr(cls, name, classmethod(patched))
    else:
        def patched(*args, **kwargs):
            if "none" in args or "none" in kwargs.values():
                return null_value_fn()
            return orig_fn(*args, **kwargs)
        setattr(cls, name, patched)

def _patch_node(cls):
    if not isinstance(cls, type) or getattr(cls, "_cp_patched", False):
        return
    cls._cp_patched = True

    is_v3 = hasattr(cls, "define_schema")
    exec_name = "execute" if is_v3 else getattr(cls, "FUNCTION", None)
    if not exec_name:
        return

    count = 1
    if is_v3:
        try:
            count = len(cls.define_schema().outputs)
        except Exception:
            pass
    else:
        count = len(getattr(cls, "RETURN_TYPES", ())) or 1

    if is_v3:
        from comfy_api.latest import io
        _patch_method(cls, exec_name, lambda: io.NodeOutput(*(None for _ in range(count))))
        _patch_method(cls, "fingerprint_inputs", lambda: "none")
    else:
        _patch_method(cls, exec_name, lambda: tuple(None for _ in range(count)))
        _patch_method(cls, "IS_CHANGED", lambda: "none")

for name, cls in list(nodes.NODE_CLASS_MAPPINGS.items()):
    if name.startswith("Load"):
        _patch_node(cls)