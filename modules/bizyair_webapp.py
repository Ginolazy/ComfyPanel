import aiohttp
import base64
import datetime
import folder_paths
import hashlib
import hmac
import io
import json
import logging
import os
import requests
import time
import torch
import torchaudio
import uuid
import numpy as np
import comfy.model_management
from comfy_api.input_impl import VideoFromFile
from aiohttp import web
from PIL import Image
from server import PromptServer
from .utility.type_utility import any_type
from .utility.comfypanel_config import read_config, write_config
from .utility.comfypanel_output import download_outputs

BIZYAIR_API_BASE = "https://api.bizyair.ai"
BIZYAIR_META_BASE = "https://meta.bizyair.ai"

def get_bizyair_config() -> str:
    cfg = read_config()
    key = cfg.get("ComfyPanel.BizyAir.apikey", "")
    if not key:
        key = cfg.get("BizyAirPlus.apikey", "")
    return key

def save_bizyair_config(api_key: str) -> None:
    write_config({"ComfyPanel.BizyAir.apikey": api_key})

@PromptServer.instance.routes.get("/bizyair_webapp/get_config")
async def get_bizyair_webapp_config(request):
    try:
        api_key = get_bizyair_config()
        return web.json_response({"success": True, "apiKey": api_key})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/bizyair_webapp/save_config")
async def save_bizyair_webapp_config(request):
    try:
        body = await request.json()
        api_key = body.get("apiKey", "")
        save_bizyair_config(api_key)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/bizyair_webapp/default_app_list")
async def get_default_app_list(request):
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "default", "default_apps.json")
        default_apps = []
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                bizy_data = data.get("bizyair", [])
                for app in bizy_data:
                    if isinstance(app, dict) and "id" in app:
                        default_apps.append(str(app["id"]))
        return web.json_response({"default_apps": default_apps})
    except Exception as e:
        print(f"[BizyAirWebApp] Error reading default config: {e}")
        return web.json_response({"default_apps": []})

@PromptServer.instance.routes.post("/comfypanel/bizyair/webapp_detail")
async def bizyair_webapp_detail(request):
    """Proxy: fetch webapp details from BizyAir meta API."""
    try:
        body = await request.json()
        webapp_id = body.get("webappId")
        if not webapp_id:
            return web.json_response({"code": -1, "msg": "Missing webappId"}, status=400)

        api_key = get_bizyair_config()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = f"{BIZYAIR_META_BASE}/v1/webapp/{webapp_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                result = await resp.json()
                return web.json_response(result, status=resp.status)
    except Exception as e:
        logging.error(f"[BizyAirWebApp] webapp_detail error: {e}")
        return web.json_response({"code": -1, "msg": str(e)}, status=500)

class BizyAirWebApp:
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
                "params_json": ("STRING", {"default": "{}"}),
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
    DISPLAY_NAME = "☁️BizyAir App"

    def _send_progress(self, unique_id, progress_val, status_str, log_msg=None):
        if unique_id:
            PromptServer.instance.send_sync("bizyair_progress", {
                "node_id": unique_id,
                "progress": progress_val,
                "status": status_str,
                "msg": log_msg or status_str
            })

    def _extract_error(self, data):
        err = data.get("error")
        if err: return err
        outputs = data.get("outputs")
        if outputs and isinstance(outputs, list):
            for out in outputs:
                if out.get("error_type") != "NOT_ERROR":
                    msg = out.get("error_msg")
                    if msg: return msg
        return "Unknown error (No detailed error message found)"

    def _tensor_to_bytes(self, tensor):
        if len(tensor.shape) == 4:
            tensor = tensor[0]
        array = 255.0 * tensor.cpu().numpy()
        image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
        bio = io.BytesIO()
        image.save(bio, format="PNG")
        return bio.getvalue()

    def _upload_to_oss(self, filename, data, api_key):
        token_url = f"{BIZYAIR_API_BASE}/v1/upload/token?file_name={filename}&file_type=inputs"
        headers_t = {"Authorization": f"Bearer {api_key}"}

        resp = requests.get(token_url, headers=headers_t)
        if resp.status_code != 200: raise Exception(f"Get token failed: {resp.text}")

        res_json = resp.json()
        if res_json.get("code") != 20000: raise Exception(f"Get token error: {res_json.get('message')}")

        token_data = res_json.get("data", {})
        file_info = token_data.get("file", {})
        storage_info = token_data.get("storage", {})

        object_key = file_info.get("object_key")
        access_key_id = file_info.get("access_key_id")
        access_key_secret = file_info.get("access_key_secret")
        security_token = file_info.get("security_token")
        bucket = storage_info.get("bucket")
        endpoint = storage_info.get("endpoint")

        date = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        headers = {
            "Host": f"{bucket}.{endpoint}",
            "Date": date,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
            "x-oss-security-token": security_token,
        }
        canonical_string = f"PUT\n\n{headers['Content-Type']}\n{date}\nx-oss-security-token:{security_token}\n/{bucket}/{object_key}"
        h = hmac.new(access_key_secret.encode("utf-8"), canonical_string.encode("utf-8"), hashlib.sha1)
        signature = base64.b64encode(h.digest()).decode("utf-8")
        headers["Authorization"] = f"OSS {access_key_id}:{signature}"

        url = f"https://{bucket}.{endpoint}/{object_key}"
        oss_resp = requests.put(url, headers=headers, data=data)
        if oss_resp.status_code not in (200, 201): raise Exception(f"OSS Upload failed: {oss_resp.text}")
        return url

    def _attempt_cancellation(self, request_id, headers, current_status):
        if not request_id: return

        print(f"[BizyAirWebApp] Cancellation detected. Attempting to stop task {request_id}...")
        cancel_url = f"{BIZYAIR_API_BASE}/v1/webapp/task/openapi/cancel?requestId={request_id}"
        interrupt_url = f"{BIZYAIR_API_BASE}/v1/webapp/task/openapi/interrupt?requestId={request_id}"

        def try_request(method, url, label):
            try:
                if method == "DELETE":
                    return requests.delete(url, headers=headers, timeout=5)
                else:
                    return requests.put(url, headers=headers, timeout=5)
            except Exception as e:
                print(f"[BizyAirWebApp] {label} request failed: {e}")
                return None

        if current_status == "Running":
            primary = ("PUT", interrupt_url, "Interrupt")
            fallback = ("DELETE", cancel_url, "Cancel")
        else:
            primary = ("DELETE", cancel_url, "Cancel")
            fallback = ("PUT", interrupt_url, "Interrupt")

        resp = try_request(primary[0], primary[1], primary[2])
        if resp and resp.status_code == 404:
            print(f"[BizyAirWebApp] {primary[2]} returned 404, trying {fallback[2]}...")
            try_request(fallback[0], fallback[1], fallback[2])
        elif resp and (resp.status_code == 200 or resp.status_code == 204):
            print(f"[BizyAirWebApp] {primary[2]} signal sent successfully.")

    def execute_app(self, APP, params_json="{}", prompt=None, extra_pnginfo=None, unique_id=None, **kwargs):
        api_key = get_bizyair_config()
        if not api_key: raise Exception("BizyAir API Key not configured. Please set it via ⚙️ BizyAir Settings.")
        if not APP or APP == "None": raise Exception("No App selected")

        input_values = {}
        mapping_dict = {}
        try:
            if params_json:
                payload_data = json.loads(params_json)
                if "_port_map" in payload_data:
                    mapping_dict = payload_data.pop("_port_map")
                input_values = payload_data
        except Exception:
            pass

        web_app_id = input_values.get("web_app_id")
        if not web_app_id: raise Exception("Missing web_app_id. Please refresh the node.")

        self._send_progress(unique_id, 0.0, "Starting...")

        for label, value in kwargs.items():
            if label not in mapping_dict: continue
            var_name = mapping_dict[label]

            if isinstance(value, torch.Tensor):
                batch_size = value.shape[0]
                urls = []
                for i in range(batch_size):
                    self._send_progress(unique_id, 0.1, f"Uploading {label} ({i+1}/{batch_size})")
                    img_bytes = self._tensor_to_bytes(value[i])
                    fname = f"comfy_upload_{uuid.uuid4().hex[:8]}_{i}.png"
                    urls.append(self._upload_to_oss(fname, img_bytes, api_key))
                input_values[var_name] = urls if batch_size > 1 else (urls[0] if urls else None)
            else:
                input_values[var_name] = value

        self._send_progress(unique_id, 0.2, "Creating Cloud Task...")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Bizyair-Task-Async": "enable"
        }

        payload = {
            "web_app_id": int(web_app_id),
            "backend_id": 0,
            "client_id": f"comfyui_{uuid.uuid4().hex[:8]}",
            "input_values": input_values,
        }

        create_url = f"{BIZYAIR_API_BASE}/v1/webapp/task/openapi/create"
        response = requests.post(create_url, json=payload, headers=headers)

        if response.status_code not in (200, 202):
            raise Exception(f"HTTP Error: {response.status_code}, Body: {response.text}")

        result = response.json()
        request_id = result.get("requestId") or result.get("request_id")
        if not request_id: raise Exception(f"No request_id found in response: {result}")

        initial_status = result.get("status")
        outputs = []
        poll_data = None

        if initial_status == "Success":
            poll_data = result
            outputs = result.get("outputs", [])
        elif initial_status == "Failed":
            raise Exception(f"Task failed immediately: {self._extract_error(result)}")
        elif initial_status == "Cancelled":
            raise Exception("Task was cancelled immediately")

        if poll_data is None:
            query_url = f"{BIZYAIR_API_BASE}/v1/webapp/task/openapi/detail?requestId={request_id}"
            time.sleep(3)

            start_time = time.time()
            simulated_progress = 0.25
            status = initial_status

            try:
                while poll_data is None or poll_data.get("status") not in ["Success", "Failed", "Error"]:
                    comfy.model_management.throw_exception_if_processing_interrupted()
                    time.sleep(1.0)

                    try:
                        poll_resp = requests.get(query_url, headers=headers, timeout=10)
                        if poll_resp.status_code == 200:
                            data = poll_resp.json()
                            poll_data = data.get("data") if data.get("code") == 20000 else data
                            status = poll_data.get("status", "Queuing") if poll_data else "Queuing"
                        elif poll_resp.status_code == 404:
                            status = "Queuing"
                    except Exception:
                        pass

                    status = poll_data.get("status", status) if poll_data else status
                    server_msg = poll_data.get("message_str", "") if poll_data else ""
                    progress_msg = poll_data.get("progress_msg") if poll_data else ""

                    server_prog = float(poll_data.get("progress", 0)) if poll_data else 0
                    if server_prog > 1.0: server_prog /= 100.0

                    if status == "Running":
                        simulated_progress = server_prog if server_prog > 0 else min(simulated_progress + 0.01, 0.95)
                    elif status == "Queuing": simulated_progress = 0.1
                    elif status == "Preparing": simulated_progress = 0.2

                    display_status = status
                    if status == "Running":
                        elapsed = int(time.time() - start_time)
                        cost = poll_data.get("inference_cost_time") if poll_data else None
                        display_time = cost if cost is not None else elapsed
                        display_status = f"Running ({display_time}s)"

                    self._send_progress(unique_id, simulated_progress, display_status, progress_msg)

                    if status in ["Failed", "Error"]:
                        raise Exception(f"Task Failed: {server_msg}")
                    if status == "Success":
                        outputs = poll_data.get("outputs", [])
                        break

            except BaseException as e:
                self._attempt_cancellation(request_id, headers, status)
                raise e

            if not outputs and status != "Success":
                raise Exception("Task timed out or failed to return outputs.")

        if not outputs and request_id:
            self._send_progress(unique_id, 0.99, "Fetching Outputs...")
            try:
                out_resp = requests.get(f"{BIZYAIR_API_BASE}/v1/webapp/task/openapi/outputs?requestId={request_id}", headers=headers)
                if out_resp.status_code == 200:
                    d = out_resp.json()
                    if d.get("code") == 20000: outputs = d.get("data", {}).get("outputs", [])
            except: pass

        self._send_progress(unique_id, 0.99, "Downloading Results...")

        urls = [o.get("object_url") for o in outputs if o.get("object_url")]
        output_dir = os.path.join(folder_paths.get_output_directory(), "bizyair")
        result_outputs = download_outputs(urls, output_dir, f"{request_id}_{web_app_id}")

        self._send_progress(unique_id, 1.0, "Success", "Task Finished")

        return {
            "ui": {
                "status": {"type": "success", "message": "Task Completed", "request_id": request_id}
            },
            "result": (result_outputs,)
        }