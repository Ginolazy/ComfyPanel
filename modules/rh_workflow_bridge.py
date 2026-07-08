REQUIRED_DEPENDENCIES = ("requests", "torch", "numpy", "folder_paths", "PIL")

import os
import json
import logging
import time
import requests
from PIL import Image
import io
import numpy as np
import torch
import folder_paths
from .utility.type_utility import any_type

class RHWorkflowBridge:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "workflow_file": ("STRING", {"default": ""}),
            },
            "optional": {

            },
            "hidden": {

                "params_json": ("STRING", {"default": "{}"}),
            }
        }

    RETURN_TYPES = (any_type,)
    DISPLAY_NAME = "☁️RHWorkflowBridge"
    FUNCTION = "execute_workflow"
    CATEGORY = "ComfyPanel"

    def execute_workflow(self, workflow_file, params_json="{}", **kwargs):

        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "runninghub_config.json")
        api_key = ""
        runninghub_base_url = "https://www.runninghub.cn"
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    api_key = config.get("runninghub_api_key", "").strip()
                    runninghub_base_url = config.get("runninghub_base_url", "https://www.runninghub.cn").strip()
            except Exception as e:
                logging.error(f"[RHWorkflowBridge] Failed to read config: {e}")

        if not api_key:
            raise ValueError("RunningHub API Key is required! Please configure it in ComfyPanel or right-click -> Properties -> runninghub_api_key of this node.")

        possible_paths = [
            workflow_file,
            os.path.join(folder_paths.get_input_directory(), workflow_file)
        ]

        resolved_path = None
        for p in possible_paths:
            if os.path.exists(p) and os.path.isfile(p):
                resolved_path = p
                break

        if not resolved_path:
            raise FileNotFoundError(f"Workflow file not found: {workflow_file}")

        try:
            with open(resolved_path, "r", encoding="utf-8") as f:
                workflow_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Failed to parse workflow JSON: {e}")

        try:
            params = json.loads(params_json) if params_json else {}
        except Exception:
            params = {}

        for k, val in params.items():
            if k.startswith("param_"):
                parts = k.split("_", 2)
                if len(parts) >= 3:
                    try:
                        target_node_id = int(parts[1])
                    except ValueError:
                        continue
                    param_name = parts[2]
                    workflow_data = self._override_workflow_parameter(workflow_data, target_node_id, param_name, val)
                    logging.info(f"[RHWorkflowBridge] Applied param override: node={target_node_id} name='{param_name}' value={val}")

        for k, val in kwargs.items():
            if k.startswith("param_") and val is not None:
                parts = k.split("_", 2)
                if len(parts) >= 3:
                    try:
                        target_node_id = int(parts[1])
                    except ValueError:
                        continue
                    param_name = parts[2]
                    workflow_data = self._override_workflow_parameter(workflow_data, target_node_id, param_name, val)
                    logging.info(f"[RHWorkflowBridge] Applied linked param override: node={target_node_id} name='{param_name}' value={val}")

        if kwargs:
            headers_upload = {
                "Authorization": f"Bearer {api_key}",
                "User-Language": "zh_CN"
            }
            for k, val in kwargs.items():
                if val is not None:

                    parts = k.rsplit("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        target_node_id = int(parts[1])

                        if isinstance(val, torch.Tensor) or (isinstance(val, list) and len(val) > 0 and isinstance(val[0], torch.Tensor)):
                            logging.info(f"[RHWorkflowBridge] Uploading dynamic image input for slot '{k}'...")
                            uploaded_fn = self._upload_image(val, api_key, runninghub_base_url, headers_upload)

                            workflow_data = self._rewrite_single_media_input(workflow_data, target_node_id, uploaded_fn)
                        else:

                            logging.warning(f"[RHWorkflowBridge] Dynamic slot '{k}' received non-tensor value: {type(val)}")

        prompt_json = {}
        if "nodes" in workflow_data and isinstance(workflow_data["nodes"], list):
            prompt_json = self._convert_ui_to_api_format(workflow_data)
        else:
            prompt_json = workflow_data

        logging.info("[RHWorkflowBridge] Submitting workflow task to RunningHub ComfyUI Proxy...")

        clean_base = runninghub_base_url.strip().rstrip("/")
        if "/proxy/" in clean_base or "/proxy-plus/" in clean_base:
            run_url = f"{clean_base}/prompt"
        else:
            run_url = f"{clean_base}/proxy/{api_key}/prompt"

        try:
            comfy_headers = {
                "Content-Type": "application/json"
            }
            logging.info(f"[RHWorkflowBridge] Submission URL: {run_url}")
            resp = requests.post(run_url, json={"prompt": prompt_json}, headers=comfy_headers)
            if resp.status_code != 200:
                raise ConnectionError(f"RunningHub ComfyUI Proxy /prompt failed with HTTP {resp.status_code}: {resp.text}")

            res_data = resp.json()
            if "error" in res_data:
                raise ValueError(f"ComfyUI execution error: {res_data['error']}")

            task_id = res_data.get("prompt_id")
            if not task_id:
                raise ValueError(f"No prompt_id returned from ComfyUI proxy: {res_data}")

            logging.info(f"[RHWorkflowBridge] Task submitted successfully. PromptID (TaskID): {task_id}. Polling status...")

            if "/proxy/" in clean_base or "/proxy-plus/" in clean_base:
                history_url = f"{clean_base}/history/{task_id}"
            else:
                history_url = f"{clean_base}/proxy/{api_key}/history/{task_id}"

            outputs = []
            max_retries = 120
            for _ in range(max_retries):
                time.sleep(5)
                status_resp = requests.get(history_url, headers=comfy_headers)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    if task_id in status_data:

                        task_history = status_data[task_id]
                        outputs_info = task_history.get("outputs", {})

                        sorted_node_ids = sorted(outputs_info.keys(), key=lambda x: int(x) if x.isdigit() else 99999)
                        for node_id in sorted_node_ids:
                            node_out = outputs_info[node_id]

                            media_files = []
                            if "images" in node_out:
                                media_files.extend(node_out["images"])
                            if "gifs" in node_out:
                                media_files.extend(node_out["gifs"])
                            if "videos" in node_out:
                                media_files.extend(node_out["videos"])
                            if "audio" in node_out:
                                media_files.extend(node_out["audio"])

                            for m_info in media_files:
                                filename_out = m_info.get("filename")
                                subfolder_out = m_info.get("subfolder", "")
                                img_type_out = m_info.get("type", "output")

                                if filename_out:
                                    if "/proxy/" in clean_base or "/proxy-plus/" in clean_base:
                                        media_url = f"{clean_base}/view?filename={filename_out}&subfolder={subfolder_out}&type={img_type_out}"
                                    else:
                                        media_url = f"{clean_base}/proxy/{api_key}/view?filename={filename_out}&subfolder={subfolder_out}&type={img_type_out}"
                                    outputs.append(media_url)
                        break
                    else:
                        logging.info(f"[RHWorkflowBridge] Task {task_id} is still in progress...")
                else:
                    logging.warning(f"[RHWorkflowBridge] Failed to poll history (HTTP {status_resp.status_code}), retrying...")

            if not outputs:
                raise TimeoutError("RunningHub task timed out or returned no outputs")

            downloaded_tensors = []
            for img_url in outputs:
                logging.info(f"[RHWorkflowBridge] Downloading output image: {img_url}")
                img_resp = requests.get(img_url)
                if img_resp.status_code == 200:
                    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
                    img_np = np.array(img).astype(np.float32) / 255.0
                    img_tensor = torch.from_numpy(img_np)[None, :]
                    downloaded_tensors.append(img_tensor)
                else:
                    logging.warning(f"[RHWorkflowBridge] Failed to download image from {img_url}")

            if not downloaded_tensors:
                raise ValueError("No images were successfully downloaded from task results")

            out_tensor = torch.cat(downloaded_tensors, dim=0)
            return (out_tensor,)

        except Exception as e:
            logging.error(f"[RHWorkflowBridge] Error executing remote workflow: {e}", exc_info=True)
            raise e

    def _convert_ui_to_api_format(self, workflow_data):
        prompt_api = {}
        if "nodes" in workflow_data:
            for node in workflow_data["nodes"]:
                node_id = str(node.get("id"))
                class_type = node.get("type")
                inputs = {}

                if "widgets_values" in node and isinstance(node["widgets_values"], list):

                    widget_slots_inputs = []
                    if "inputs" in node and isinstance(node["inputs"], list):
                        for inp in node["inputs"]:
                            if isinstance(inp, dict) and (inp.get("widget") or inp.get("type") == "COMBO"):
                                widget_slots_inputs.append(inp)
                                w_name = inp.get("widget", {}).get("name") or inp.get("name")
                                if w_name in ["seed", "noise_seed"]:
                                    widget_slots_inputs.append({"name": "control_after_generate", "type": "COMBO", "virtual": True})

                    widget_slots_outputs = []
                    if "outputs" in node and isinstance(node["outputs"], list):
                        for out in node["outputs"]:
                            if isinstance(out, dict) and out.get("widget"):
                                widget_slots_outputs.append(out)

                    widget_slots = widget_slots_inputs + widget_slots_outputs

                    for widget_idx, slot in enumerate(widget_slots):
                        if slot.get("virtual"):
                            continue
                        slot_name = slot.get("name")
                        if slot.get("widget") and isinstance(slot["widget"], dict):
                            slot_name = slot["widget"].get("name") or slot_name
                        if slot_name and widget_idx < len(node["widgets_values"]):

                            inputs[slot_name] = node["widgets_values"][widget_idx]

                if "inputs" in node and isinstance(node["inputs"], list):
                    for inp in node["inputs"]:
                        link_id = inp.get("link")
                        if link_id is not None:
                            source_node_id, source_slot = self._find_link_source(workflow_data, link_id)
                            if source_node_id is not None:
                                inputs[inp.get("name")] = [str(source_node_id), source_slot]

                prompt_api[node_id] = {
                    "inputs": inputs,
                    "class_type": class_type
                }
        return prompt_api

    def _find_link_source(self, workflow_data, link_id):
        if "links" in workflow_data and isinstance(workflow_data["links"], list):
            for l in workflow_data["links"]:
                if l and len(l) >= 4 and l[0] == link_id:
                    return l[1], l[2]
        return None, None

    def _upload_image(self, image_tensor, api_key, base_url, headers):
        img_np = image_tensor[0].cpu().numpy()
        img_np = (img_np * 255).astype(np.uint8)
        img = Image.fromarray(img_np)

        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)

        url = f"{base_url}/openapi/v2/media/upload/binary"
        files = {"file": ("uxp_upload.png", bio, "image/png")}

        resp = requests.post(url, files=files, headers=headers)
        if resp.status_code == 200:
            res_data = resp.json()
            if res_data.get("code") == 0 and "data" in res_data:
                file_name = res_data["data"].get("fileName")
                logging.info(f"[RHWorkflowBridge] Image uploaded successfully to RunningHub. Cloud Filename: {file_name}")
                return file_name
        raise ConnectionError(f"Failed to upload image to RunningHub: {resp.text}")

    def _rewrite_single_media_input(self, workflow_data, target_node_id, filename):

        if "nodes" in workflow_data and isinstance(workflow_data["nodes"], list):
            for node in workflow_data["nodes"]:
                if node.get("id") == target_node_id:

                    if "widgets_values" in node and isinstance(node["widgets_values"], list):
                        node["widgets_values"][0] = filename
                        logging.info(f"[RHWorkflowBridge] Rewrote media node {target_node_id} widget value to: {filename}")
                    break

        elif isinstance(workflow_data, dict):
            node_key = str(target_node_id)
            if node_key in workflow_data:
                node = workflow_data[node_key]
                if "inputs" in node and isinstance(node["inputs"], dict):

                    for k in ["image", "video", "audio", "upload"]:
                        if k in node["inputs"]:
                            node["inputs"][k] = filename
                            logging.info(f"[RHWorkflowBridge] Rewrote API media node {target_node_id} input '{k}' to: {filename}")
                            break
                    else:

                        node["inputs"]["image"] = filename
                        logging.info(f"[RHWorkflowBridge] Fallback rewrote API media node {target_node_id} image to: {filename}")
        return workflow_data

    def _override_workflow_parameter(self, workflow_data, target_node_id, param_name, value):
        if "nodes" in workflow_data and isinstance(workflow_data["nodes"], list):
            for node in workflow_data["nodes"]:
                if node.get("id") == target_node_id:

                    widget_slots_inputs = []
                    if "inputs" in node and isinstance(node["inputs"], list):
                        for inp in node["inputs"]:
                            if isinstance(inp, dict) and (inp.get("widget") or inp.get("type") == "COMBO"):
                                widget_slots_inputs.append(inp)
                                w_name = inp.get("widget", {}).get("name") or inp.get("name")
                                if w_name in ["seed", "noise_seed"]:
                                    widget_slots_inputs.append({"name": "control_after_generate", "type": "COMBO", "virtual": True})

                    widget_slots_outputs = []
                    if "outputs" in node and isinstance(node["outputs"], list):
                        for out in node["outputs"]:
                            if isinstance(out, dict) and out.get("widget"):
                                widget_slots_outputs.append(out)

                    widget_slots = widget_slots_inputs + widget_slots_outputs

                    target_slot = None
                    for slot in widget_slots:

                        slot_name = slot.get("name")
                        if slot.get("widget") and isinstance(slot["widget"], dict):
                            slot_name = slot["widget"].get("name") or slot_name
                        if slot_name == param_name:
                            target_slot = slot
                            break

                    if target_slot is not None:
                        try:
                            widget_idx = widget_slots.index(target_slot)
                            if "widgets_values" not in node or not isinstance(node["widgets_values"], list):
                                node["widgets_values"] = []
                            while len(node["widgets_values"]) <= widget_idx:
                                node["widgets_values"].append(None)
                            node["widgets_values"][widget_idx] = value
                            logging.info(f"[RHWorkflowBridge] Overrode UI node {target_node_id} parameter '{param_name}' = {value}")
                        except Exception as e:
                            logging.error(f"[RHWorkflowBridge] Failed to override parameter: {e}")
                    break
        elif isinstance(workflow_data, dict):
            node_key = str(target_node_id)
            if node_key in workflow_data:
                node = workflow_data[node_key]
                if "inputs" in node and isinstance(node["inputs"], dict):
                    node["inputs"][param_name] = value
                    logging.info(f"[RHWorkflowBridge] Overrode API node {target_node_id} parameter '{param_name}' = {value}")
        return workflow_data

def _find_workflow_file_path(workflow_file: str):
    """查找 inner 工作流文件的完整路径，找不到返回 None。优先从 input/workflows/ 查找。"""
    input_dir = folder_paths.get_input_directory()
    possible_paths = [
        workflow_file,
        os.path.join(input_dir, "workflows", workflow_file),
        os.path.join(input_dir, workflow_file),
    ]
    for p in possible_paths:
        if os.path.exists(p) and os.path.isfile(p):
            return p
    return None

def _remap_inner_workflow(inner: dict, remap: dict) -> dict:
    """
    重映射 inner workflow 中的节点 ID。
    - 更新 dict 的 key
    - 更新所有 inputs 中形如 [old_node_id, slot_idx] 的连线引用
    """
    remapped = {}
    for old_id, node_data in inner.items():
        new_id = remap.get(str(old_id), str(old_id))
        new_node = json.loads(json.dumps(node_data))
        for inp_key, inp_val in new_node.get("inputs", {}).items():
            if isinstance(inp_val, list) and len(inp_val) == 2:
                src_id = str(inp_val[0])
                if src_id in remap:
                    new_node["inputs"][inp_key] = [remap[src_id], inp_val[1]]
        remapped[new_id] = new_node
    return remapped

async def _upload_local_file_to_rh(filename: str, base_url: str, api_key: str):
    """
    将 ComfyUI input 目录中的本地文件上传到 RunningHub。
    返回云端 fileName 字符串，失败返回 None。
    """
    try:
        import aiohttp
        import re
        input_dir = folder_paths.get_input_directory()
        file_path = os.path.join(input_dir, filename)
        if not os.path.isfile(file_path):
            logging.warning(f"[expand_bridge_nodes] Local file not found for upload: {filename}")
            return None

        match = re.match(r"(https?://[^/]+)", base_url.strip())
        domain = match.group(1) if match else base_url.strip().rstrip("/")
        url = f"{domain}/openapi/v2/media/upload/binary"

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with aiohttp.ClientSession() as session:
            with open(file_path, "rb") as f:
                form = aiohttp.FormData()
                form.add_field("file", f, filename=filename)
                async with session.post(url, data=form, headers=headers) as resp:
                    res_json = await resp.json()
                    if res_json.get("code") == 0 and "data" in res_json:
                        cloud_fn = res_json["data"].get("fileName")
                        logging.info(f"[expand_bridge_nodes] Uploaded {filename} → cloud: {cloud_fn}")
                        return cloud_fn
    except Exception as e:
        logging.warning(f"[expand_bridge_nodes] Upload failed for {filename}: {e}")
    return None

async def expand_bridge_nodes(outer_prompt: dict, base_url: str, api_key: str) -> dict:
    """
    将 outer_prompt 中所有 RHWorkflowBridge 节点内联展开：
      1. 读取并转换 inner 工作流为 API 格式
      2. 解决与 outer 的 node ID 冲突（重新分配冲突 ID）
      3. 应用 param_* 参数覆盖
      4. 处理媒体输入槽：inner Load* 连线重定向到 outer Load*，删除 inner Load* 节点
      5. 处理输出槽：inner Save* 删除，outer Save* 重连到 inner 上游节点
      6. 合并剩余 inner 节点到 outer_prompt

    webview Run 和 PS Run 都经过 /comfypanel/runninghub/proxy，统一在此处理。
    前端 uploadPromptImages 已在 proxy 调用前将 outer Load* 节点的 filename 替换为 RH 云端 URL，
    此函数不需要重复上传。
    """
    bridge_helper = RHWorkflowBridge()
    result = {str(k): v for k, v in outer_prompt.items()}

    bridge_node_ids = [
        nid for nid, node in result.items()
        if isinstance(node, dict) and node.get("class_type") == "RHWorkflowBridge"
    ]

    if not bridge_node_ids:
        return result

    for bridge_id in bridge_node_ids:
        bridge_node = result.get(bridge_id)
        if not bridge_node:
            continue
        inputs = bridge_node.get("inputs", {})
        workflow_file = inputs.get("workflow_file", "")
        params_json_str = inputs.get("params_json", "{}")

        resolved_path = _find_workflow_file_path(workflow_file)
        if not resolved_path:
            raise ValueError(f"RHWorkflowBridge: inner workflow file '{workflow_file}' not found in ComfyUI input directory")

        with open(resolved_path, "r", encoding="utf-8") as f:
            inner_data = json.load(f)

        if "nodes" in inner_data and isinstance(inner_data["nodes"], list):
            inner_prompt = bridge_helper._convert_ui_to_api_format(inner_data)
        else:
            inner_prompt = inner_data

        inner_prompt = {str(k): v for k, v in inner_prompt.items()}

        outer_ids = set(result.keys()) - {bridge_id}
        inner_ids = set(inner_prompt.keys())
        all_digit_ids = [int(k) for k in (outer_ids | inner_ids) if k.isdigit()]
        next_free = (max(all_digit_ids) + 1) if all_digit_ids else 1

        remap = {}
        for iid in inner_ids:
            if iid in outer_ids:
                remap[iid] = str(next_free)
                next_free += 1
            else:
                remap[iid] = iid

        inner_prompt = _remap_inner_workflow(inner_prompt, remap)

        try:
            params = json.loads(params_json_str) if params_json_str else {}
        except Exception:
            params = {}

        def _apply_param(raw_node_id_str, param_name, value):
            """将参数值写入 inner_prompt 对应节点的 inputs。"""
            mapped_id = remap.get(raw_node_id_str, raw_node_id_str)
            if mapped_id in inner_prompt:
                inner_prompt[mapped_id]["inputs"][param_name] = value
                logging.info(f"[expand_bridge_nodes] Override inner node {mapped_id}.{param_name} = {value!r}")

        for k, v in params.items():
            if k.startswith("param_"):
                parts = k.split("_", 2)
                if len(parts) >= 3:
                    try:
                        raw_node_id = str(int(parts[1]))
                    except ValueError:
                        continue
                    _apply_param(raw_node_id, parts[2], v)

        for k, v in inputs.items():
            if not k.startswith("param_") and not k.startswith("Param_"):
                continue
            k_lower = k.lower()
            if not k_lower.startswith("param_"):
                continue
            parts = k_lower.split("_", 2)
            if len(parts) < 3:
                continue
            try:
                raw_node_id = str(int(parts[1]))
            except ValueError:
                continue
            param_name = parts[2]

            actual_v = v
            if isinstance(v, list) and len(v) == 2:
                src_node_id = str(v[0])
                src_node = result.get(src_node_id, {})
                src_inputs = src_node.get("inputs", {})

                for vkey in ("value", "int", "float", "string", "text", "number"):
                    if vkey in src_inputs:
                        actual_v = src_inputs[vkey]
                        break
            _apply_param(raw_node_id, param_name, actual_v)

        MEDIA_PREFIXES = ("image_", "video_", "audio_", "mask_")
        inner_load_nodes_to_remove = set()

        for slot_name, slot_val in inputs.items():
            slot_name_lower = slot_name.lower()
            if not any(slot_name_lower.startswith(p) for p in MEDIA_PREFIXES):
                continue

            prefix = next(p for p in MEDIA_PREFIXES if slot_name_lower.startswith(p))
            inner_raw_id = slot_name_lower[len(prefix):]

            if not inner_raw_id.isdigit():
                continue

            mapped_id = remap.get(inner_raw_id, inner_raw_id)
            if mapped_id not in inner_prompt:
                continue

            if isinstance(slot_val, list) and len(slot_val) == 2:

                outer_src_id = str(slot_val[0])

                for node in inner_prompt.values():
                    for inp_key, inp_val in node.get("inputs", {}).items():
                        if isinstance(inp_val, list) and len(inp_val) == 2 and str(inp_val[0]) == mapped_id:
                            node["inputs"][inp_key] = [outer_src_id, inp_val[1]]

                inner_load_nodes_to_remove.add(mapped_id)
                logging.info(f"[expand_bridge_nodes] Slot '{slot_name}': rewired inner Load* {mapped_id} → outer node {outer_src_id}")

        for nid in inner_load_nodes_to_remove:
            inner_prompt.pop(nid, None)

        SAVE_KEYWORDS = ("saveimage", "save_image", "saveaudio", "save_audio",
                         "savevideo", "save_video", "vhs_videocombine")

        inner_save_ids = sorted(
            [nid for nid, n in inner_prompt.items()
             if any(kw in (n.get("class_type") or "").lower() for kw in SAVE_KEYWORDS)],
            key=lambda x: int(x) if x.isdigit() else 99999
        )

        slot_to_upstream = {}
        for slot_idx, save_id in enumerate(inner_save_ids):
            save_inputs = inner_prompt[save_id].get("inputs", {})
            for mkey in ("images", "image", "video", "audio"):
                upstream = save_inputs.get(mkey)
                if isinstance(upstream, list) and len(upstream) == 2:
                    slot_to_upstream[slot_idx] = upstream
                    break

        for node_id, node in list(result.items()):
            if node_id == bridge_id:
                continue
            for inp_key, inp_val in node.get("inputs", {}).items():
                if isinstance(inp_val, list) and len(inp_val) == 2 and str(inp_val[0]) == bridge_id:
                    slot_idx = inp_val[1]
                    upstream = slot_to_upstream.get(slot_idx)
                    if upstream:
                        node["inputs"][inp_key] = upstream
                        logging.info(f"[expand_bridge_nodes] Outer node {node_id}.{inp_key}: bridge[{slot_idx}] → {upstream}")

        for save_id in inner_save_ids:
            inner_prompt.pop(save_id, None)
            logging.info(f"[expand_bridge_nodes] Removed inner Save* node {save_id}")

        del result[bridge_id]

        result.update(inner_prompt)

    return result