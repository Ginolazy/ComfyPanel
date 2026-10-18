import folder_paths
import nodes

orig_filter = folder_paths.filter_files_content_types
def patched_filter(files, content_types):
    result = orig_filter(files, content_types)
    return ["none"] + [f for f in result if f != "none"]
folder_paths.filter_files_content_types = patched_filter

orig_exists = folder_paths.exists_annotated_filepath
def patched_exists(name):
    return True if name == "none" else orig_exists(name)
folder_paths.exists_annotated_filepath = patched_exists

def _patch_node_class(cls):
    """Short-circuit execution when any input is 'none', returning None matching RETURN_TYPES count."""
    func_name = getattr(cls, "FUNCTION", None)
    if not func_name or not hasattr(cls, func_name):
        return
    orig_fn = getattr(cls, func_name)
    return_count = len(getattr(cls, "RETURN_TYPES", (None,))) or 1

    def _patched_fn(*args, **kwargs):
        if "none" in args or "none" in kwargs.values():
            if hasattr(cls, "define_schema"):
                from comfy_api.latest import io
                return io.NodeOutput(*(None for _ in range(return_count)))
            return tuple(None for _ in range(return_count))
        return orig_fn(*args, **kwargs)

    setattr(cls, func_name, classmethod(_patched_fn) if isinstance(cls.__dict__.get(func_name), classmethod) else _patched_fn)

for node_name, node_cls in list(nodes.NODE_CLASS_MAPPINGS.items()):
    if node_name.startswith("Load"):
        _patch_node_class(node_cls)