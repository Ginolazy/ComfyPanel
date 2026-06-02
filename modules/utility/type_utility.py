## ComfyUI/custom_nodes/ComfyPanel/py/utility/type_utility.py
class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False

any_type = AnyType("*")

def handle_error(e: Exception, msg: str = "Operation failed"):
    raise type(e)(f"[ComfyPanel] {msg}: {e}").with_traceback(e.__traceback__)

def handle_error_safe(e: Exception, msg: str = "Operation failed", port_count: int = 1):
    print(f"[ComfyPanel] {msg}: {e}")
    return tuple([[""] for _ in range(port_count)])