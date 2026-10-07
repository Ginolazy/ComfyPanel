import re, requests
from .utility.math_utility import math_operation_calc
from .utility.type_utility import handle_error

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

class TextMultiline:
    API_URL = "https://index-translate.bilibili.com/v1/chat/completions"
    MODEL_NAME = "Index-Translate-35B-A3B"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True}),
                "direction": (["none", "translate_to_en", "enhance_to_en", "translate_to_target"], {"default": "none"}),
            },
            "optional": {
                "target_lang": ("STRING", {"default": "zh"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "translate_text"
    CATEGORY = "ComfyPanel/Text"
    DESCRIPTION = "TextMultiline Node – Translate or enhance text using Index-Translate."

    def translate_text(self, text, direction, target_lang="zh"):
        text = text.strip()
        if not text or direction == "none":
            return (text,)

        if direction == "translate_to_en":
            prompt = f"请将以下文本翻译为英语，直接输出翻译结果，不要进行任何解释。\n\n{text}"
        elif direction == "enhance_to_en":
            prompt = (
                "你是一个专业的AI绘画提示词专家。请根据以下描述，扩写为丰富、具象、包含画面细节与氛围的高质量英文提示词（Prompt）。"
                f"直接输出英文提示词，不要输出任何解释：\n\n{text}"
            )
        elif direction == "translate_to_target":
            lang = target_lang.strip() if target_lang else "中文"
            prompt = f"请将以下文本翻译为{lang}，直接输出翻译结果，不要进行任何解释。\n\n{text}"
        else:
            return (text,)

        payload = {
            "model": self.MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}]
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "curl/8.7.1",
            "Accept": "*/*"
        }

        try:
            response = requests.post(
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            output = data["choices"][0]["message"]["content"].strip()
            return (output,)
        except Exception as e:
            return (handle_error(e, "Translation request failed"),)

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