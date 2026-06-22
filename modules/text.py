## ComfyUI/custom_nodes/ComfyPanel/modules/text.py

import re, shlex, subprocess
from .utility.math_utility import math_operation_calc
from .utility.type_utility import handle_error

# Float
class Float:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("FLOAT", {"default": 0.0, "min": -999999, "max": 999999, "step": 0.0001}),
            }
        }

    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("float",)
    FUNCTION = "get_value"
    CATEGORY = "ComfyPanel/Text"

    def get_value(self, value):
        return (value,)

# Int
class Int:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("INT", {"default": 0, "min": -999999, "max": 999999, "step": 1}),
            }
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("int",)
    FUNCTION = "get_value"
    CATEGORY = "ComfyPanel/Text"

    def get_value(self, value):
        return (value,)

# MathOperation
class MathOperation:
    INPUT_TYPE_A = "FLOAT"
    INPUT_TYPE_B = "FLOAT"
    RETURN_TYPE_ORDER = ("FLOAT", "INT")
    RETURN_NAMES = ("float_result", "int_result")
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "operation": ([
                    "add", "subtract", "multiply", "divide", "modulo", "power",
                    "sin", "cos", "tan", "sqrt", "exp", "log", "neg", "abs"
                ],),
                "precision": ("INT", {"default": 0, "min": -1, "max": 100}),
                "A": (cls.INPUT_TYPE_A, {"default": 0.0, "min": -999999, "max": 999999, "step": 0.0001}),
                "B": (cls.INPUT_TYPE_B, {"default": 0.0, "min": -999999, "max": 999999, "step": 0.0001}),
            }
        }

    RETURN_TYPES = RETURN_TYPE_ORDER
    RETURN_NAMES = RETURN_NAMES
    FUNCTION = "calculate"
    CATEGORY = "ComfyPanel/Text"

    def calculate(self, operation, A, B, precision=0):
        float_result, int_result = math_operation_calc(operation, A, B, precision)
        return float_result, int_result
        
# StringListToString
class StringListToString:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "join_with": ("STRING", {"default": "\\n"}),
                "string_list": ("STRING", {"forceInput": True}),
            }
        }

    INPUT_IS_LIST = True
    RETURN_TYPES = ("STRING",)
    FUNCTION = "doit"
    CATEGORY = "ComfyPanel/Text"

    def doit(self, join_with, string_list):
        if join_with[0] == "\\n":
            join_with[0] = "\n"

        joined_text = join_with[0].join(string_list)

        return (joined_text,)

# Text Concat
class TextConcat:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "separator": ("STRING", {"default": "\\n"}),
            },
        }
    
    RETURN_TYPES = ("STRING",)
    FUNCTION = "concatenate"
    CATEGORY = "ComfyPanel/Text"
    
    def concatenate(self, separator, **kwargs):
        if separator == "\\n":
            separator = "\n"
        elif separator == "\\t":
            separator = "\t"
        elif separator == "\\r":
            separator = "\r"
        elif separator == "\\s":
            separator = " "
        
        texts = []
        
        for key, value in kwargs.items():
            if key.startswith("text_") and value is not None:
                index = int(key.split("_")[1])
                texts.append((index, value))
        texts.sort(key=lambda x: x[0])
        result = separator.join(text for _, text in texts if text)
        return (result,)

# Text Multiline note
class TextMultiline:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "direction": (["auto", "zh-en", "en-zh", "none"], {"default": "none"})
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "translate_text"
    CATEGORY = "ComfyPanel/Text"
    DESCRIPTION = "TextMultiline Node – Mac Translation Magic 🪄: Works with macOS Shortcuts for fun, customizable text translations. Only on Mac!"

    def is_translatable(self, text):
        return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", text))

    def is_english(self, text):
        letters = re.findall(r"[A-Za-z]", text)
        chinese = re.findall(r"[\u4e00-\u9fff]", text)
        return len(letters) > len(chinese) * 1.5

    def translate_text(self, text, direction):
        text = text.strip()
        if not text:
            return ("",)
        if direction == "none":
            return (text,)
        if not self.is_translatable(text):
            return (text,)
        if direction == "auto":
            direction = "zh-en" if not self.is_english(text) else "en-zh"
        shortcut_name = "Translate_ZHToEN" if direction == "zh-en" else "Translate_ENToZH"
        try:
            cmd = f"printf %s {shlex.quote(text)} | shortcuts run {shortcut_name}"
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=True,
                check=True
            )
            output = re.sub(r'\n\s*\n+', '\n', result.stdout.strip())
            return (output,)
        except subprocess.CalledProcessError as e:
            return (handle_error(e, f"Translation shortcut '{shortcut_name}' failed"),)
        except Exception as e:
            return (handle_error(e, "Unexpected error during translation"),)

## -------------------------- Third-party -------------------------- ##
# ShowText
class ShowText:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    CATEGORY = "ComfyPanel/Text"
    INPUT_IS_LIST = True
    OUTPUT_IS_LIST = (True,)
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING",)
    FUNCTION = "notify"

    def notify(self, text, unique_id=None, extra_pnginfo=None):
        if unique_id is not None and extra_pnginfo is not None:
            if isinstance(extra_pnginfo, list) and extra_pnginfo and isinstance(extra_pnginfo[0], dict):
                workflow = extra_pnginfo[0].get("workflow")
                if workflow:
                    node = next((x for x in workflow["nodes"] if str(x["id"]) == str(unique_id[0])), None)
                    if node:
                        node["widgets_values"] = [text]

        return {"ui": {"text": text}, "result": (text,)}
