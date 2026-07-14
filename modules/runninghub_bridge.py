REQUIRED_DEPENDENCIES = ("requests", "torch", "numpy", "folder_paths", "PIL")

import os
import json
import logging
import time
import requests
import io
import uuid
import numpy as np
import torch
import folder_paths
from PIL import Image
from aiohttp import web
from server import PromptServer
import comfy.model_management
from .utility.type_utility import any_type

def get_rh_config():
    config_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    config_path = os.path.join(config_dir, ".runninghub_config")
    api_key = ""
    runninghub_base_url = "https://www.runninghub.cn"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if key == "runninghub_api_key":
                        api_key = val
                    elif key == "runninghub_base_url":
                        runninghub_base_url = val
        except Exception as e:
            logging.error(f"[RunningHub] Failed to read config: {e}")
    return api_key, runninghub_base_url

def upload_image_to_runninghub(image_tensor, api_key, base_url):

    if isinstance(image_tensor, list):
        if len(image_tensor) == 0:
            return ""
        image_tensor = image_tensor[0]

    if len(image_tensor.shape) == 4:
        image_tensor = image_tensor[0]

    img_np = image_tensor.cpu().numpy()
    img_np = (img_np * 255.0).astype(np.uint8)
    img = Image.fromarray(img_np)

    bio = io.BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)

    url = f"{base_url.strip().rstrip('/')}/openapi/v2/media/upload/binary"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["User-Language"] = "zh_CN"

    files = {"file": ("uxp_upload.png", bio, "image/png")}
    resp = requests.post(url, files=files, headers=headers)
    if resp.status_code == 200:
        res_data = resp.json()
        if res_data.get("code") == 0 and "data" in res_data:
            file_name = res_data["data"].get("fileName")
            logging.info(f"[RunningHub] Image uploaded successfully. Cloud Filename: {file_name}")
            return file_name
    raise ConnectionError(f"Failed to upload image to RunningHub: {resp.text}")

@PromptServer.instance.routes.get("/rh_webapp/get_config")
async def get_rh_webapp_config(request):
    try:
        api_key, base_url = get_rh_config()
        return web.json_response({"apiKey": api_key, "baseUrl": base_url})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/webapp_detail")
async def runninghub_webapp_detail(request):
    try:
        body = await request.json()
        webapp_id = body.get("webappId")
        if not webapp_id:
            return web.json_response({"success": False, "error": "Missing webappId"}, status=400)

        api_key, base_url = get_rh_config()
        clean_base = base_url.strip().rstrip("/")
        if not clean_base.startswith("http"):
            clean_base = "https://www.runninghub.cn"

        url = f"{clean_base}/api/webapp/detail"
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["token"] = api_key

        resp = requests.post(url, json={"webappId": str(webapp_id)}, headers=headers, timeout=15)
        if resp.status_code != 200:
            return web.json_response({"success": False, "error": f"RunningHub detail API returned HTTP {resp.status_code}"}, status=resp.status_code)

        res_json = resp.json()
        return web.json_response(res_json)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get("/rh_webapp/default_app_list")
async def get_rh_default_app_list(request):
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "default", "default_apps.json")
        default_apps = []
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                raw_apps = data.get("runninghub", {})
                if isinstance(raw_apps, dict):
                    for category in raw_apps.values():
                        if isinstance(category, list):
                            for app in category:
                                if isinstance(app, dict) and "id" in app:
                                    default_apps.append(str(app["id"]))
        return web.json_response({"default_apps": default_apps})
    except Exception as e:
        print(f"[RHWebApp] Error reading default config: {e}")
        return web.json_response({"default_apps": []})

class RHWorkflow:
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
                "unique_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = (any_type,)
    DISPLAY_NAME = "☁️RunningHub Workflow"
    FUNCTION = "execute_workflow"
    CATEGORY = "ComfyPanel"

    def _send_progress(self, unique_id, progress_val, status_str, log_msg=None):
        if unique_id:
            PromptServer.instance.send_sync("runninghub_webapp_progress", {
                "node_id": unique_id,
                "progress": progress_val,
                "status": status_str,
                "msg": log_msg or status_str
            })

    def execute_workflow(self, workflow_file, params_json="{}", unique_id=None, **kwargs):
        api_key, runninghub_base_url = get_rh_config()

        workflow_id = workflow_file.strip()
        is_api_mode = workflow_id.isdigit() and len(workflow_id) == 19

        workflow_data = None
        if is_api_mode:
            if not api_key:
                raise ValueError("RunningHub API Key is required! Please configure it in ComfyPanel or RunningHub config.")
            workflow_id = workflow_file.strip()
            if not workflow_id:
                raise ValueError("Workflow ID must not be empty under runninghub_api mode!")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            clean_base_domain = runninghub_base_url.strip().rstrip("/")
            if not clean_base_domain.startswith("http"):
                clean_base_domain = "https://www.runninghub.cn"

            fetch_url = f"{clean_base_domain}/api/openapi/getJsonApiFormat"
            payload = {
                "apiKey": api_key,
                "workflowId": workflow_id
            }

            logging.info(f"[RHWorkflow] Fetching workflow {workflow_id} from {fetch_url}...")
            try:
                resp = requests.post(fetch_url, json=payload, headers=headers, timeout=15)
                if resp.status_code != 200:
                    raise ConnectionError(f"Failed to fetch workflow via RunningHub API, HTTP {resp.status_code}: {resp.text}")
                res_json = resp.json()
                if res_json.get("code") != 0:
                    msg = res_json.get("msg") or res_json.get("message") or "Unknown error"
                    raise ValueError(f"RunningHub API returned error: {msg}")

                data_val = res_json.get("data")
                if isinstance(data_val, str):
                    try:
                        parsed = json.loads(data_val)
                        if isinstance(parsed, dict) and "prompt" in parsed:
                            prompt_val = parsed.get("prompt")
                            workflow_data = json.loads(prompt_val) if isinstance(prompt_val, str) else prompt_val
                        else:
                            workflow_data = parsed
                    except Exception:
                        workflow_data = data_val
                elif isinstance(data_val, dict):
                    if "prompt" in data_val:
                        prompt_val = data_val.get("prompt")
                        workflow_data = json.loads(prompt_val) if isinstance(prompt_val, str) else prompt_val
                    else:
                        workflow_data = data_val
                else:
                    workflow_data = res_json
            except Exception as e:
                raise ValueError(f"Failed to retrieve or parse workflow from RunningHub API: {e}")
        else:
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
                    logging.info(f"[RHWorkflow] Applied param override: node={target_node_id} name='{param_name}' value={val}")

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
                    logging.info(f"[RHWorkflow] Applied linked param override: node={target_node_id} name='{param_name}' value={val}")

        if kwargs:
            for k, val in kwargs.items():
                if val is not None:
                    parts = k.rsplit("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        target_node_id = int(parts[1])
                        if isinstance(val, torch.Tensor) or (isinstance(val, list) and len(val) > 0 and isinstance(val[0], torch.Tensor)):
                            logging.info(f"[RHWorkflow] Uploading dynamic image input for slot '{k}'...")
                            uploaded_fn = upload_image_to_runninghub(val, api_key, runninghub_base_url)
                            workflow_data = self._rewrite_single_media_input(workflow_data, target_node_id, uploaded_fn)
                        else:
                            logging.warning(f"[RHWorkflow] Dynamic slot '{k}' received non-tensor value: {type(val)}")

        prompt_json = {}
        if "nodes" in workflow_data and isinstance(workflow_data["nodes"], list):
            prompt_json = self._convert_ui_to_api_format(workflow_data)
        else:
            prompt_json = workflow_data

        logging.info("[RHWorkflow] Submitting workflow task to RunningHub ComfyUI Proxy...")

        clean_base = runninghub_base_url.strip().rstrip("/")
        if "/proxy/" in clean_base or "/proxy-plus/" in clean_base:
            run_url = f"{clean_base}/prompt"
        else:
            run_url = f"{clean_base}/proxy/{api_key}/prompt"

        try:
            comfy_headers = {
                "Content-Type": "application/json"
            }
            logging.info(f"[RHWorkflow] Submission URL: {run_url}")
            resp = requests.post(run_url, json={"prompt": prompt_json}, headers=comfy_headers)
            if resp.status_code != 200:
                raise ConnectionError(f"RunningHub ComfyUI Proxy /prompt failed with HTTP {resp.status_code}: {resp.text}")

            res_data = resp.json()
            if "error" in res_data:
                raise ValueError(f"ComfyUI execution error: {res_data['error']}")

            task_id = res_data.get("prompt_id")
            if not task_id:
                raise ValueError(f"No prompt_id returned from ComfyUI proxy: {res_data}")

            logging.info(f"[RHWorkflow] Task submitted successfully. PromptID (TaskID): {task_id}. Polling status...")

            if "/proxy/" in clean_base or "/proxy-plus/" in clean_base:
                history_url = f"{clean_base}/history/{task_id}"
            else:
                history_url = f"{clean_base}/proxy/{api_key}/history/{task_id}"

            outputs = []
            max_retries = 120
            self._send_progress(unique_id, 0.1, "Submitted", "Submitted, polling status...")
            for step in range(max_retries):
                time.sleep(5)
                progress_val = min(0.1 + (step / max_retries) * 0.8, 0.95)
                self._send_progress(unique_id, progress_val, f"Running ({step*5}s)")
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
                        logging.info(f"[RHWorkflow] Task {task_id} is still in progress...")
                else:
                    logging.warning(f"[RHWorkflow] Failed to poll history (HTTP {status_resp.status_code}), retrying...")

            if not outputs:
                raise TimeoutError("RunningHub task timed out or returned no outputs")

            self._send_progress(unique_id, 0.95, "Downloading results...")
            downloaded_tensors = []
            for img_url in outputs:
                logging.info(f"[RHWorkflow] Downloading output image: {img_url}")
                img_resp = requests.get(img_url)
                if img_resp.status_code == 200:
                    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
                    img_np = np.array(img).astype(np.float32) / 255.0
                    img_tensor = torch.from_numpy(img_np)[None, :]
                    downloaded_tensors.append(img_tensor)
                else:
                    logging.warning(f"[RHWorkflow] Failed to download image from {img_url}")

            if not downloaded_tensors:
                raise ValueError("No images were successfully downloaded from task results")

            out_tensor = torch.cat(downloaded_tensors, dim=0)
            self._send_progress(unique_id, 1.0, "Success", "Success!")
            return (out_tensor,)

        except Exception as e:
            self._send_progress(unique_id, 0.0, "Failed", str(e))
            logging.error(f"[RHWorkflow] Error executing remote workflow: {e}", exc_info=True)
            raise e

    def _convert_ui_to_api_format(self, workflow_data):
        nodes = workflow_data.get("nodes", [])
        links = workflow_data.get("links", [])

        prompt_api = {}
        for node in nodes:
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

                for idx, val in enumerate(node["widgets_values"]):
                    if idx < len(widget_slots):
                        slot = widget_slots[idx]
                        if slot.get("virtual"):
                            continue
                        name = slot.get("name")
                        if slot.get("widget") and isinstance(slot["widget"], dict):
                            name = slot["widget"].get("name") or name
                        inputs[name] = val

            if "inputs" in node and isinstance(node["inputs"], list):
                for inp_idx, inp in enumerate(node["inputs"]):
                    link_id = inp.get("link")
                    if link_id is not None:
                        src_node_id, src_slot = self._find_link_source(workflow_data, link_id)
                        if src_node_id is not None:
                            inputs[inp.get("name")] = [str(src_node_id), src_slot]

            prompt_api[node_id] = {
                "class_type": class_type,
                "inputs": inputs
            }
        return prompt_api

    def _find_link_source(self, workflow_data, link_id):
        if "links" in workflow_data and isinstance(workflow_data["links"], list):
            for l in workflow_data["links"]:
                if l and len(l) >= 4 and l[0] == link_id:
                    return l[1], l[2]
        return None, None

    def _rewrite_single_media_input(self, workflow_data, target_node_id, filename):
        if "nodes" in workflow_data and isinstance(workflow_data["nodes"], list):
            for node in workflow_data["nodes"]:
                if node.get("id") == target_node_id:
                    if "widgets_values" in node and isinstance(node["widgets_values"], list):
                        node["widgets_values"][0] = filename
                        logging.info(f"[RHWorkflow] Rewrote media node {target_node_id} widget value to: {filename}")
                    break
        elif isinstance(workflow_data, dict):
            node_key = str(target_node_id)
            if node_key in workflow_data:
                node = workflow_data[node_key]
                if "inputs" in node and isinstance(node["inputs"], dict):
                    for k in ["image", "video", "audio", "upload"]:
                        if k in node["inputs"]:
                            node["inputs"][k] = filename
                            logging.info(f"[RHWorkflow] Rewrote API media node {target_node_id} input '{k}' to: {filename}")
                            break
                    else:
                        node["inputs"]["image"] = filename
                        logging.info(f"[RHWorkflow] Fallback rewrote API media node {target_node_id} image to: {filename}")
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
                            logging.info(f"[RHWorkflow] Overrode UI node {target_node_id} parameter '{param_name}' = {value}")
                        except Exception as e:
                            logging.error(f"[RHWorkflow] Failed to override parameter: {e}")
                    break
        elif isinstance(workflow_data, dict):
            node_key = str(target_node_id)
            if node_key in workflow_data:
                node = workflow_data[node_key]
                if "inputs" in node and isinstance(node["inputs"], dict):
                    node["inputs"][param_name] = value
                    logging.info(f"[RHWorkflow] Overrode API node {target_node_id} parameter '{param_name}' = {value}")
        return workflow_data

class RHWebApp:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "APP": ([],),
            },
            "optional": {

            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
                "input_values_json": ("STRING", {"default": "{}"}),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(s, **kwargs):
        return True

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("Result",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "execute_app"
    CATEGORY = "ComfyPanel"
    DISPLAY_NAME = "☁️RunningHub App"

    def _send_progress(self, unique_id, progress_val, status_str, log_msg=None):
        if unique_id:
            PromptServer.instance.send_sync("runninghub_webapp_progress", {
                "node_id": unique_id,
                "progress": progress_val,
                "status": status_str,
                "msg": log_msg or status_str
            })

    def execute_app(self, APP, input_values_json="{}", prompt=None, extra_pnginfo=None, unique_id=None, **kwargs):
        api_key, base_url = get_rh_config()
        if not api_key:
            raise Exception("RunningHub API Key is not configured. Please configure it in ComfyPanel settings.")
        if not APP or APP == "None":
            raise Exception("No App selected")

        web_app_id = None
        input_values = {}
        mapping_dict = {}
        try:
            if input_values_json:
                payload_data = json.loads(input_values_json)
                if "_port_map" in payload_data:
                    mapping_dict = payload_data.pop("_port_map")
                input_values = payload_data
        except Exception:
            pass

        web_app_id = input_values.get("web_app_id")
        if not web_app_id:
            raise Exception("Missing web_app_id. Please reload or refresh the node.")

        self._send_progress(unique_id, 0.0, "Starting...")

        node_info_list = []

        for key, val in input_values.items():
            if key == "web_app_id":
                continue
            if "." in key:
                parts = key.split(".", 1)
                node_info_list.append({
                    "nodeId": parts[0],
                    "fieldName": parts[1],
                    "fieldValue": str(val)
                })

        for label, value in kwargs.items():
            if label not in mapping_dict:
                continue
            var_name = mapping_dict[label]
            if "." not in var_name:
                continue
            parts = var_name.split(".", 1)
            node_id = parts[0]
            field_name = parts[1]

            field_val_str = ""
            if isinstance(value, torch.Tensor) or (isinstance(value, list) and len(value) > 0 and isinstance(value[0], torch.Tensor)):
                self._send_progress(unique_id, 0.1, f"Uploading input {label}...")
                field_val_str = upload_image_to_runninghub(value, api_key, base_url)
            else:
                field_val_str = str(value)

            found = False
            for item in node_info_list:
                if item["nodeId"] == node_id and item["fieldName"] == field_name:
                    item["fieldValue"] = field_val_str
                    found = True
                    break
            if not found:
                node_info_list.append({
                    "nodeId": node_id,
                    "fieldName": field_name,
                    "fieldValue": field_val_str
                })

        self._send_progress(unique_id, 0.2, "Creating WebApp Task...")

        run_url = f"{base_url.strip().rstrip('/')}/task/openapi/ai-app/run"
        headers = {
            "Content-Type": "application/json"
        }

        payload = {
            "webappId": str(web_app_id),
            "apiKey": api_key,
            "nodeInfoList": node_info_list
        }

        resp = requests.post(run_url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise Exception(f"Failed to submit WebApp task, HTTP {resp.status_code}: {resp.text}")

        res_data = resp.json()
        if res_data.get("code") != 0:
            msg = res_data.get("msg") or res_data.get("message") or "Unknown error"
            raise Exception(f"RunningHub WebApp run error: {msg}")

        task_id = None
        data_field = res_data.get("data")
        if isinstance(data_field, dict):
            task_id = data_field.get("taskId") or data_field.get("id")
        else:
            task_id = data_field

        if not task_id:
            raise Exception(f"No taskId returned from task creation: {res_data}")

        task_id = str(task_id)
        logging.info(f"[RHWebApp] Task created successfully. TaskID: {task_id}. Polling...")

        outputs = []
        poll_url = f"{base_url.strip().rstrip('/')}/task/openapi/outputs"
        poll_payload = {
            "apiKey": api_key,
            "taskId": task_id
        }

        start_time = time.time()
        simulated_progress = 0.25
        max_retries = 180

        for attempt in range(max_retries):
            comfy.model_management.throw_exception_if_processing_interrupted()
            time.sleep(5)

            try:
                poll_resp = requests.post(poll_url, json=poll_payload, headers=headers, timeout=15)
                if poll_resp.status_code == 200:
                    poll_res = poll_resp.json()
                    code = poll_res.get("code")

                    if code == 0:
                        data_items = poll_res.get("data")
                        items = data_items if isinstance(data_items, list) else ([data_items] if data_items else [])
                        for item in items:
                            if not item:
                                continue
                            url = item if isinstance(item, str) else (item.get("url") or item.get("fileUrl") or item.get("file_url") or item.get("imgUrl") or item.get("videoUrl") or item.get("audioUrl") or item.get("object_url"))
                            if url:
                                outputs.append(url)
                        if outputs:
                            break
                    elif code in [804, 813]:
                        status_str = "Queuing" if code == 813 else "Running"
                        simulated_progress = min(simulated_progress + 0.02, 0.95)
                        elapsed = int(time.time() - start_time)
                        self._send_progress(unique_id, simulated_progress, f"{status_str} ({elapsed}s)")
                    elif code == 805:
                        failed_data = poll_res.get("data")
                        reason = "Unknown error"
                        if isinstance(failed_data, dict):
                            reason = failed_data.get("failedReason") or failed_data.get("exception_message") or failed_data.get("message") or reason
                        raise Exception(f"RunningHub WebApp execution failed: {reason}")
                    else:
                        msg = poll_res.get("msg") or "Error querying task"
                        raise Exception(f"RunningHub WebApp task error: {msg}")
            except Exception as e:
                if "execution failed" in str(e) or "task error" in str(e):
                    raise e
                logging.warning(f"[RHWebApp] Polling network error: {e}")

        if not outputs:
            raise TimeoutError("RunningHub WebApp execution timed out or returned no output files.")

        self._send_progress(unique_id, 0.99, "Downloading results...")
        result_outputs = []

        output_dir = os.path.join(folder_paths.get_output_directory(), "runninghub_webapp")
        os.makedirs(output_dir, exist_ok=True)

        for idx, file_url in enumerate(outputs):
            self._send_progress(unique_id, 0.99, f"Downloading result ({idx+1}/{len(outputs)})...")
            ext = os.path.splitext(file_url.split('?')[0])[1].lower() or ".png"
            filename = f"rh_{task_id}_{web_app_id}_{idx}{ext}"
            filepath = os.path.join(output_dir, filename)

            try:
                with requests.get(file_url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)

                if ext in ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff']:
                    img = Image.open(filepath)
                    img_array = np.array(img.convert("RGBA") if img.mode == 'RGBA' else img.convert("RGB")).astype(np.float32) / 255.0
                    result_outputs.append(torch.from_numpy(img_array).unsqueeze(0))
                elif ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
                    import torchaudio
                    waveform, sample_rate = torchaudio.load(filepath)
                    result_outputs.append({"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate})
                else:
                    try:
                        from comfy_api.input_impl import VideoFromFile
                        result_outputs.append(VideoFromFile(filepath))
                    except ImportError:
                        result_outputs.append(filepath)
            except Exception as e:
                logging.error(f"[RHWebApp] Error processing result {idx}: {e}")

        self._send_progress(unique_id, 1.0, "Success", "Task Finished")

        return {
            "ui": {
                "status": {"type": "success", "message": "Task Completed", "task_id": task_id}
            },
            "result": (result_outputs,)
        }

def _find_workflow_file_path(workflow_file: str):
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
    bridge_helper = RHWorkflow()
    result = {str(k): v for k, v in outer_prompt.items()}

    bridge_node_ids = [
        nid for nid, node in result.items()
        if isinstance(node, dict) and node.get("class_type") == "RHWorkflow"
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
            raise ValueError(f"RHWorkflow: inner workflow file '{workflow_file}' not found in ComfyUI input directory")

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