## ComfyUI/custom_nodes/ComfyPanel/modules/bizyair_webapp.py

import base64
import configparser
import datetime
import folder_paths
import hashlib
import hmac
import io
import json
import mimetypes
import os
import requests
import time
import torch
import uuid
import numpy as np
from aiohttp import web
from PIL import Image
from server import PromptServer
import comfy.model_management
from .utility.type_utility import any_type

def get_api_key():
    try:
        user_dir = folder_paths.get_user_directory()
        settings_file = os.path.join(user_dir, "default", "comfy.settings.json")
        if os.path.exists(settings_file):
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
                return settings.get("BizyAir.BizyAirPlus.apikey")
    except Exception as e:
        print(f"[BizyAirWebApp] Error reading API key from comfy.settings.json: {e}")
    return None

# Expose interface to get API Key for frontend
@PromptServer.instance.routes.get("/bizyair_webapp/get_api_key")
async def get_bizyair_api_key(request):
    try:
        api_key = get_api_key()
        return web.json_response({"api_key": api_key})
    except Exception as e:
        print(f"[BizyAirWebApp] Error in /bizyair_webapp/get_api_key: {e}")
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/bizyair_webapp/default_app_list")
async def get_default_app_list(request):
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "default", "default_apps.json")
        default_apps = []
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Parse structured JSON to extract IDs
                raw_apps = data.get("default_apps", {})
                if isinstance(raw_apps, dict):
                    for category in raw_apps.values():
                        if isinstance(category, list):
                            for app in category:
                                if isinstance(app, dict) and "id" in app:
                                    default_apps.append(str(app["id"]))
                elif isinstance(raw_apps, list):
                    # Legacy support or simple list
                     for app in raw_apps:
                        if isinstance(app, dict) and "id" in app:
                            default_apps.append(str(app["id"]))
                        elif isinstance(app, (str, int)):
                            default_apps.append(str(app))

        return web.json_response({"default_apps": default_apps})
    except Exception as e:
        print(f"[BizyAirWebApp] Error reading default config: {e}")
        return web.json_response({"default_apps": []})

class BizyAirWebApp:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "APP": ([],),  # Populated dynamically
            },
            "optional": {
                # Static input ports (for connection persistence)
                "input_1": (any_type,),
                "input_2": (any_type,),
                "input_3": (any_type,),
                "input_4": (any_type,),
                "input_5": (any_type,),
                "input_6": (any_type,),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
                "input_values_json": ("STRING", {"default": "{}"}), # Hidden input for dynamic widgets
            }
        }

    @classmethod
    def VALIDATE_INPUTS(s, **kwargs):
        # Allow all inputs to validate, avoiding 400 Bad Request
        return True

    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("Result",)
    OUTPUT_IS_LIST = (True,) # Enable list output handling
    FUNCTION = "execute_app"
    CATEGORY = "ComfyPanel"
    DISPLAY_NAME = "☁️BizyAirWebApp"

    def _send_progress(self, unique_id, progress_val, status_str, log_msg=None):
        if unique_id:
            PromptServer.instance.send_sync("bizyair_progress", {
                "node_id": unique_id,
                "progress": progress_val,
                "status": status_str,
                "msg": log_msg or status_str
            })

    def _extract_error(self, data):
        # 1. Top-level 'error'
        err = data.get("error")
        if err: return err

        # 2. 'outputs' array for item-level errors
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
        token_url = f"https://api.bizyair.cn/x/v1/upload/token?file_name={filename}"
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
        """Attempts to cancel or interrupt the task with fallback logic."""
        if not request_id: return

        print(f"[BizyAirWebApp] Cancellation detected. Attempting to stop task {request_id}...")
        cancel_url = f"https://api.bizyair.cn/w/v1/webapp/task/openapi/cancel?requestId={request_id}"
        interrupt_url = f"https://api.bizyair.cn/w/v1/webapp/task/openapi/interrupt?requestId={request_id}"

        def try_request(method, url, label):
            try:
                if method == "DELETE":
                    return requests.delete(url, headers=headers, timeout=5)
                else:
                    return requests.put(url, headers=headers, timeout=5)
            except Exception as e:
                print(f"[BizyAirWebApp] {label} request failed: {e}")
                return None

        # Determine Primary and Fallback based on status
        if current_status == "Running":
            primary = ("PUT", interrupt_url, "Interrupt")
            fallback = ("DELETE", cancel_url, "Cancel")
        else:
            primary = ("DELETE", cancel_url, "Cancel")
            fallback = ("PUT", interrupt_url, "Interrupt")

        # 1. Try Primary
        resp = try_request(primary[0], primary[1], primary[2])
        if resp and resp.status_code == 404:
            # 2. Try Fallback if 404
            print(f"[BizyAirWebApp] {primary[2]} returned 404, trying {fallback[2]}...")
            try_request(fallback[0], fallback[1], fallback[2])
        elif resp and (resp.status_code == 200 or resp.status_code == 204):
            print(f"[BizyAirWebApp] {primary[2]} signal sent successfully.")
        
    def execute_app(self, APP, input_values_json="{}", prompt=None, extra_pnginfo=None, unique_id=None, **kwargs):
        api_key = get_api_key()
        if not api_key: raise Exception("BizyAir API Key not found in comfy.settings.json")
        if not APP or APP == "None": raise Exception("No App selected")

        web_app_id = None
        
        # 1. Parse Input Values
        input_values = {}
        mapping_dict = {}
        try:
            if input_values_json:
                payload_data = json.loads(input_values_json)
                if "_port_map" in payload_data:
                    mapping_dict = payload_data.pop("_port_map")
                input_values = payload_data
        except Exception:
            pass # Fail silently, input_values defaults to {}

        web_app_id = input_values.get("web_app_id")
        if not web_app_id: raise Exception("Missing web_app_id. Please refresh the node.")
        
        # 2. Update Progress: Starting
        self._send_progress(unique_id, 0.0, "Starting...")

        # 3. Process Input Uploads (OSS)
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

        # 4. Create Task
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
        
        create_url = "https://api.bizyair.cn/w/v1/webapp/task/openapi/create"
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

        # 5. Poll Task Status
        if poll_data is None:
            query_url = f"https://api.bizyair.cn/w/v1/webapp/task/openapi/detail?requestId={request_id}"
            time.sleep(3) # Initial wait
            
            start_time = time.time()
            simulated_progress = 0.25
            status = initial_status

            try:
                while poll_data is None or poll_data.get("status") not in ["Success", "Failed", "Error"]:
                    # Check Cancellation
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
                        pass # Network glitches ignored in polling loop
                    
                    # Update Progress Logic
                    status = poll_data.get("status", status) if poll_data else status
                    server_msg = poll_data.get("message_str", "") if poll_data else ""
                    progress_msg = poll_data.get("progress_msg") if poll_data else ""
                    
                    # Simulated Progress
                    server_prog = float(poll_data.get("progress", 0)) if poll_data else 0
                    if server_prog > 1.0: server_prog /= 100.0
                    
                    if status == "Running":
                        simulated_progress = server_prog if server_prog > 0 else min(simulated_progress + 0.01, 0.95)
                    elif status == "Queuing": simulated_progress = 0.1
                    elif status == "Preparing": simulated_progress = 0.2
                    
                    # Timer Display
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

        # 6. Fetch / Download Outputs
        if not outputs and request_id:
             # Try fetching from output endpoint if missing
             self._send_progress(unique_id, 0.99, "Fetching Outputs...")
             try:
                 out_resp = requests.get(f"https://api.bizyair.cn/w/v1/webapp/task/openapi/outputs?requestId={request_id}", headers=headers)
                 if out_resp.status_code == 200:
                     d = out_resp.json()
                     if d.get("code") == 20000: outputs = d.get("data", {}).get("outputs", [])
             except: pass

        self._send_progress(unique_id, 0.99, "Downloading Results...")
        result_outputs = []
        
        output_dir = os.path.join(folder_paths.get_output_directory(), "bizyair")
        os.makedirs(output_dir, exist_ok=True)

        for idx, output in enumerate(outputs):
            file_url = output.get("object_url")
            if not file_url: continue
            
            self._send_progress(unique_id, 0.99, f"Downloading ({idx+1}/{len(outputs)})...")
            ext = os.path.splitext(file_url)[1].lower() or ".png"
            filename = f"{request_id}_{web_app_id}_{idx}{ext}"
            filepath = os.path.join(output_dir, filename)
            
            try:
                with requests.get(file_url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(filepath, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192): f.write(chunk)
                
                # Check file type
                if ext in ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff']:
                    img = Image.open(filepath)
                    img_array = np.array(img.convert("RGBA") if img.mode == 'RGBA' else img.convert("RGB")).astype(np.float32) / 255.0
                    result_outputs.append(torch.from_numpy(img_array).unsqueeze(0))
                elif ext in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
                    import torchaudio
                    waveform, sample_rate = torchaudio.load(filepath)
                    result_outputs.append({"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate})
                else:
                    # Video or others -> VideoFromFile
                    from comfy_api.input_impl import VideoFromFile
                    result_outputs.append(VideoFromFile(filepath))
            except Exception as e:
                print(f"[BizyAirWebApp] Error processing result {idx}: {e}")

        self._send_progress(unique_id, 1.0, "Success", "Task Finished")
        
        return {
            "ui": {
                "status": {"type": "success", "message": "Task Completed", "request_id": request_id}
            },
            "result": (result_outputs,)
        }