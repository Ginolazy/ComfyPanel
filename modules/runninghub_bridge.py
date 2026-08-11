REQUIRED_DEPENDENCIES = ("requests", "torch", "numpy", "folder_paths", "PIL")

import comfy.model_management
import cv2
import folder_paths
import io
import json
import logging
import nodes
import numpy as np
import os
import random
import re
import requests
import time
import torch
import torchaudio
import urllib.parse
import uuid
import wave
import aiohttp
from aiohttp import web
from comfy_api.input_impl import VideoFromFile
from comfy_extras.nodes_audio import load as load_audio
from PIL import Image
from server import PromptServer
from .utility.type_utility import any_type
from .utility.comfypanel_config import read_config, write_config
from .utility.comfypanel_output import download_outputs

def get_rh_config(provided_base_url=None):
    cfg = read_config()
    base_url = provided_base_url or cfg.get("ComfyPanel.RunningHub.baseUrl", "https://www.runninghub.cn")
    is_en = "runninghub.ai" in base_url
    api_key_name = "ComfyPanel.RunningHubEn.apikey" if is_en else "ComfyPanel.RunningHubZh.apikey"
    api_key = cfg.get(api_key_name, "")
    return api_key, base_url

def upload_to_runninghub(value, api_key, base_url):
    """
    通用上传函数：支持 torch.Tensor、numpy.ndarray 和文件名字符串
    Unified upload function: supports torch.Tensor, numpy.ndarray, and filename strings
    """

    if isinstance(value, list):
        if len(value) == 0:
            return ""
        value = value[0]

    if isinstance(value, (torch.Tensor, np.ndarray)):

        if isinstance(value, torch.Tensor):
            img_np = value.cpu().numpy()
        else:
            img_np = value

        if img_np.ndim == 4:
            img_np = img_np[0]

        img_np = (img_np * 255.0).astype(np.uint8)
        img = Image.fromarray(img_np)

        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)

        filename = "uxp_upload.png"
        mime_type = "image/png"

    elif isinstance(value, str):
        input_dir = folder_paths.get_input_directory()
        file_path = os.path.join(input_dir, value)
        if not os.path.isfile(file_path):
            file_path = value
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"File not found in ComfyUI input directory: {value}")

        bio = io.BytesIO()
        with open(file_path, "rb") as f:
            bio.write(f.read())
        bio.seek(0)

        filename = os.path.basename(file_path)

        lower_fn = filename.lower()
        if lower_fn.endswith((".png", ".jpg", ".jpeg")):
            mime_type = "image/png"
        elif lower_fn.endswith((".wav", ".mp3", ".flac", ".ogg")):
            mime_type = "audio/wav"
        elif lower_fn.endswith((".mp4", ".avi", ".mov", ".webm")):
            mime_type = "video/mp4"
        else:
            mime_type = "application/octet-stream"
    else:
        raise ValueError(f"Upload value must be a torch.Tensor, numpy.ndarray, or filename string, got: {type(value)}")

    url = f"{base_url.strip().rstrip('/')}/openapi/v2/media/upload/binary"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    files = {"file": (filename, bio, mime_type)}
    resp = requests.post(url, files=files, headers=headers)
    if resp.status_code == 200:
        res_data = resp.json()
        if res_data.get("code") == 0 and "data" in res_data:
            file_name = res_data["data"].get("fileName")
            logging.info(f"[RunningHub] Media uploaded successfully. Cloud Filename: {file_name}")
            return file_name
    raise ConnectionError(f"Failed to upload media to RunningHub: {resp.text}")

def process_and_upload_media(value, api_key, base_url, field_name_hint=""):
    """
    处理并上传各种媒体类型到 RunningHub
    支持: 图片tensor, 视频tensor, 音频dict, 文件名字符串等
    Process and upload various media types to RunningHub
    Supports: image tensor, video tensor, audio dict, filename string, etc.
    """

    temp_val = value
    if isinstance(temp_val, list) and len(temp_val) > 0:
        if isinstance(temp_val[0], (torch.Tensor, np.ndarray)):
            temp_val = temp_val[0]
        elif isinstance(temp_val[0], str):
            temp_val = temp_val[0]
        elif isinstance(temp_val[0], dict):
            temp_val = temp_val[0]

    if isinstance(temp_val, dict) and "waveform" in temp_val and "sample_rate" in temp_val:
        waveform = temp_val["waveform"]
        sample_rate = temp_val["sample_rate"]
        if isinstance(waveform, torch.Tensor):
            waveform = waveform.cpu().numpy()
        if waveform.ndim == 3:
            waveform = waveform[0]

        temp_fn = f"rh_temp_{uuid.uuid4().hex}.wav"
        temp_dir = folder_paths.get_input_directory()
        temp_path = os.path.join(temp_dir, temp_fn)

        audio_data = np.clip(waveform, -1.0, 1.0)
        audio_data = (audio_data * 32767).astype(np.int16)

        with wave.open(temp_path, "wb") as wav_file:
            nchannels = audio_data.shape[0] if audio_data.ndim > 1 else 1
            sampwidth = 2
            wav_file.setnchannels(nchannels)
            wav_file.setsampwidth(sampwidth)
            wav_file.setframerate(sample_rate)
            if nchannels > 1:
                frames = audio_data.T.tobytes()
            else:
                frames = audio_data.tobytes()
            wav_file.writeframes(frames)

        try:
            return upload_to_runninghub(temp_fn, api_key, base_url)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    if isinstance(temp_val, dict):
        temp_val = temp_val.get("filename") or temp_val.get("image") or temp_val.get("video") or temp_val.get("audio")

    if isinstance(temp_val, str):
        return upload_to_runninghub(temp_val, api_key, base_url)

    if isinstance(temp_val, (torch.Tensor, np.ndarray)):
        val_np = temp_val.cpu().numpy() if isinstance(temp_val, torch.Tensor) else temp_val

        is_video = "video" in field_name_hint.lower() and val_np.ndim == 4 and val_np.shape[0] > 1

        if is_video:

            temp_fn = f"rh_temp_{uuid.uuid4().hex}.mp4"
            temp_dir = folder_paths.get_input_directory()
            temp_path = os.path.join(temp_dir, temp_fn)

            height, width = val_np.shape[1], val_np.shape[2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_path, fourcc, 25.0, (width, height))
            for frame in val_np:
                frame_bgr = cv2.cvtColor((np.clip(frame, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
            out.release()

            try:
                logging.info(f"[RunningHub] Converted video tensor to MP4, uploading...")
                return upload_to_runninghub(temp_fn, api_key, base_url)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
        else:

            if val_np.ndim == 4:
                val_np = val_np[0]
            val_np = np.clip(val_np, 0, 1)
            img_data = (val_np * 255).astype(np.uint8)
            img = Image.fromarray(img_data)
            temp_fn = f"rh_temp_{uuid.uuid4().hex}.png"
            temp_dir = folder_paths.get_input_directory()
            temp_path = os.path.join(temp_dir, temp_fn)
            img.save(temp_path)
            try:
                return upload_to_runninghub(temp_fn, api_key, base_url)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

    raise ValueError(f"Unsupported media type for upload: {type(temp_val)}")

def upload_image_to_runninghub(image_tensor, api_key, base_url):
    """Backward compatibility wrapper for image uploads"""
    return process_and_upload_media(image_tensor, api_key, base_url, "image")

def upload_media_to_runninghub(val, api_key, base_url):
    """Backward compatibility wrapper for file uploads"""
    return process_and_upload_media(val, api_key, base_url, "")

def send_progress_update(unique_id, progress_val, status_str, log_msg=None):
    """发送节点进度更新到前端"""
    if unique_id:
        PromptServer.instance.send_sync("runninghub_webapp_progress", {
            "node_id": unique_id,
            "progress": progress_val,
            "status": status_str,
            "msg": log_msg or status_str
        })

@PromptServer.instance.routes.get("/rh_webapp/get_config")
async def get_rh_webapp_config(request):
    try:
        api_key, base_url = get_rh_config()
        return web.json_response({"apiKey": api_key, "baseUrl": base_url})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/rh_webapp/default_app_list")
async def get_rh_default_app_list(request):
    try:
        _, base_url = get_rh_config()
        is_international = "runninghub.ai" in base_url

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
                                if not isinstance(app, dict):
                                    continue

                                shared_id = app.get("id")
                                if shared_id:
                                    default_apps.append(str(shared_id))
                                region_id = app.get("idEn") if is_international else app.get("idZh")
                                if region_id:
                                    default_apps.append(str(region_id))
        return web.json_response({"default_apps": default_apps})
    except Exception as e:
        print(f"[RHWebApp] Error reading default config: {e}")
        return web.json_response({"default_apps": []})

@PromptServer.instance.routes.post("/comfypanel/runninghub/webapp_detail")
async def runninghub_webapp_detail(request):
    """
    Fetch webapp details from RunningHub API for RHWebApp node.
    """
    try:
        body = await request.json()
        webapp_id = body.get("webappId")
        if not webapp_id:
            return web.json_response({"code": -1, "msg": "Missing webappId"}, status=400)

        api_key, base_url = get_rh_config()
        clean_base = base_url.strip().rstrip("/")
        if not clean_base.startswith("http"):
            clean_base = "https://www.runninghub.cn"

        url = f"{clean_base}/api/webapp/detail"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"webappId": str(webapp_id)}, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                result = await resp.json()
                return web.json_response(result, status=resp.status)
    except Exception as e:
        logging.error(f"[RHWebApp] webapp_detail error: {e}")
        return web.json_response({"code": -1, "msg": str(e)}, status=500)

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
                "prompt": "PROMPT",
            }
        }

    RETURN_TYPES = (any_type,) * 30
    DISPLAY_NAME = "☁️RunningHub Workflow"
    FUNCTION = "execute_workflow"
    CATEGORY = "ComfyPanel"
    DESCRIPTION = "Flexible RunningHub workflow loader supporting two methods: A.Directly input a RunningHub Workflow ID to run online. B.Open locally after downloading the workflow file from RunningHub."

    def execute_workflow(self, workflow_file, params_json="{}", unique_id=None, prompt=None, **kwargs):
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
            resolved_path = _find_workflow_file_path(workflow_file)
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

        if kwargs:
            for k, val in kwargs.items():
                if val is not None:
                    parts = k.rsplit("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        target_node_id = int(parts[1])

                        uploaded_fn = None
                        try:
                            if prompt and unique_id in prompt:
                                node_inputs = prompt[unique_id].get("inputs", {})
                                if k in node_inputs and isinstance(node_inputs[k], list) and len(node_inputs[k]) == 2:
                                    src_nid = str(node_inputs[k][0])
                                    src_node = prompt.get(src_nid)
                                    if src_node:
                                        src_inputs = src_node.get("inputs", {})
                                        raw_fn = src_inputs.get("image") or src_inputs.get("audio") or src_inputs.get("video") or src_inputs.get("upload")
                                        if raw_fn and isinstance(raw_fn, str):
                                            uploaded_fn = process_and_upload_media(raw_fn, api_key, runninghub_base_url, k)
                        except Exception as trace_err:
                            logging.warning(f"[RHWorkflow] Failed to trace parent raw file: {trace_err}")

                        if not uploaded_fn:
                            try:
                                uploaded_fn = process_and_upload_media(val, api_key, runninghub_base_url, k)
                            except Exception as fallback_err:
                                logging.error(f"[RHWorkflow] Failed to process media for slot '{k}': {fallback_err}", exc_info=True)

                        if not uploaded_fn:
                            raise ValueError(f"Failed to trace or process media file for input slot '{k}'")

                        if uploaded_fn:
                            workflow_data = self._rewrite_single_media_input(workflow_data, target_node_id, uploaded_fn)

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
            logging.info(f"[RHWorkflow] Submitting to URL: {run_url}")
            logging.debug(f"[RHWorkflow] Payload size: {len(json.dumps(prompt_json))} bytes")

            resp = requests.post(run_url, json={"prompt": prompt_json}, headers=comfy_headers)
            if resp.status_code != 200:
                raise ConnectionError(f"RunningHub ComfyUI Proxy /prompt failed with HTTP {resp.status_code}: {resp.text}")

            res_data = resp.json()
            logging.debug(f"[RHWorkflow] Response: {res_data}")

            if "error" in res_data:
                raise ValueError(f"ComfyUI execution error: {res_data['error']}")

            task_id = res_data.get("prompt_id")
            if not task_id:

                error_msg = f"No prompt_id returned from ComfyUI proxy. Response: {res_data}"
                if res_data == {}:
                    error_msg += "\n\nPossible causes:"
                    error_msg += "\n1. RunningHub API Key may be invalid or expired"
                    error_msg += "\n2. Insufficient credits or permissions"
                    error_msg += "\n3. Workflow JSON format issue"
                    error_msg += f"\n4. Check API URL: {run_url}"
                raise ValueError(error_msg)

            logging.info(f"[RHWorkflow] Task submitted successfully. PromptID (TaskID): {task_id}. Polling status...")

            if "/proxy/" in clean_base or "/proxy-plus/" in clean_base:
                history_url = f"{clean_base}/history/{task_id}"
            else:
                history_url = f"{clean_base}/proxy/{api_key}/history/{task_id}"

            outputs_by_node = {}
            max_retries = 360
            send_progress_update(unique_id, 0.1, "Submitted", "Submitted, polling status...")
            for step in range(max_retries):

                comfy.model_management.throw_exception_if_processing_interrupted()

                time.sleep(5)
                progress_val = min(0.1 + (step / max_retries) * 0.8, 0.95)
                send_progress_update(unique_id, progress_val, f"Running ({step*5}s)")
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

                            node_urls = []
                            for m_info in media_files:
                                filename_out = m_info.get("filename")
                                subfolder_out = m_info.get("subfolder", "")
                                img_type_out = m_info.get("type", "output")

                                if filename_out:
                                    if "/proxy/" in clean_base or "/proxy-plus/" in clean_base:
                                        media_url = f"{clean_base}/view?filename={filename_out}&subfolder={subfolder_out}&type={img_type_out}"
                                    else:
                                        media_url = f"{clean_base}/proxy/{api_key}/view?filename={filename_out}&subfolder={subfolder_out}&type={img_type_out}"
                                    node_urls.append(media_url)
                            if node_urls:
                                outputs_by_node[node_id] = node_urls
                        break
                    else:
                        logging.info(f"[RHWorkflow] Task {task_id} is still in progress...")
                else:
                    logging.warning(f"[RHWorkflow] Failed to poll history (HTTP {status_resp.status_code}), retrying...")

            if not outputs_by_node:
                raise TimeoutError("RunningHub task timed out or returned no outputs")

            send_progress_update(unique_id, 0.95, "Downloading results...")

            output_results = []
            sorted_output_node_ids = sorted(outputs_by_node.keys(), key=lambda x: int(x) if x.isdigit() else 99999)

            for node_id in sorted_output_node_ids:
                urls = outputs_by_node[node_id]
                node_files = []

                for media_url in urls:
                    logging.info(f"[RHWorkflow] Downloading output media: {media_url}")
                    parsed_url = urllib.parse.urlparse(media_url)
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    filename = query_params.get("filename", [""])[0]
                    if not filename:
                        filename = os.path.basename(parsed_url.path)

                    ext = os.path.splitext(filename)[1].lower()

                    media_resp = requests.get(media_url)
                    if media_resp.status_code == 200:
                        media_bytes = media_resp.content

                        if ext in [".png", ".jpg", ".jpeg", ".webp"]:

                            img = Image.open(io.BytesIO(media_bytes)).convert("RGB")
                            img_np = np.array(img).astype(np.float32) / 255.0
                            img_tensor = torch.from_numpy(img_np)[None, :]
                            node_files.append(img_tensor)

                        elif ext in [".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"]:

                            temp_fn = f"rh_out_{uuid.uuid4().hex}{ext}"
                            temp_dir = folder_paths.get_input_directory()
                            temp_path = os.path.join(temp_dir, temp_fn)

                            try:

                                with open(temp_path, "wb") as f:
                                    f.write(media_bytes)

                                try:
                                    waveform, sample_rate = load_audio(temp_path)

                                    audio_dict = {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
                                    node_files.append(audio_dict)
                                    logging.info(f"[RHWorkflow] Successfully loaded output audio: {filename}")
                                except Exception as load_err:
                                    logging.error(f"[RHWorkflow] Failed to load audio via comfy_extras: {load_err}")
                            finally:
                                if os.path.exists(temp_path):
                                    try:
                                        os.remove(temp_path)
                                    except Exception:
                                        pass

                        elif ext in [".mp4", ".avi", ".mov", ".webm", ".gif"]:

                            dest_fn = f"rh_out_{uuid.uuid4().hex}{ext}"
                            dest_path = os.path.join(folder_paths.get_input_directory(), dest_fn)
                            with open(dest_path, "wb") as f:
                                f.write(media_bytes)
                            node_files.append(dest_fn)
                            logging.info(f"[RHWorkflow] Saved output video/gif to input directory: {dest_fn}")

                        else:

                            node_files.append(media_bytes)
                    else:
                        logging.warning(f"[RHWorkflow] Failed to download media from {media_url}")

                if node_files:
                    if all(isinstance(x, torch.Tensor) for x in node_files):

                        grouped_node_tensor = torch.cat(node_files, dim=0)
                        output_results.append(grouped_node_tensor)
                    elif len(node_files) == 1:
                        output_results.append(node_files[0])
                    else:
                        output_results.append(node_files)

            if not output_results:
                raise ValueError("No media files were successfully downloaded from task results")

            res_tuple = tuple(output_results)
            padding_len = len(self.RETURN_TYPES) - len(res_tuple)
            if padding_len > 0:
                res_tuple = res_tuple + (None,) * padding_len
            send_progress_update(unique_id, 1.0, "Success", "Success!")
            return res_tuple

        except BaseException as e:

            status = "Cancelled" if "interrupt" in str(e).lower() or isinstance(e, KeyboardInterrupt) else "Failed"
            send_progress_update(unique_id, 0.0, status, str(e))
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

            widgets = scan_standard_node_widgets(node, class_type)

            if not widgets:

                ui_widgets = []
                if "inputs" in node and isinstance(node["inputs"], list):
                    for inp in node["inputs"]:
                        if isinstance(inp, dict) and "widget" in inp:
                            w_name = inp["widget"].get("name") or inp.get("name")
                            if w_name:
                                ui_widgets.append(w_name)

                widgets_values = node.get("widgets_values", [])
                for idx, w_name in enumerate(ui_widgets):
                    val = None
                    if idx < len(widgets_values):
                        val = widgets_values[idx]
                    if val is None:
                        val = ""
                    inputs[w_name] = val
            else:
                for w in widgets:
                    w_name = w["name"]
                    val = w["value"]

                    if w_name == "audioUI":
                        if not val:

                            audio_val = inputs.get("audio")
                            if audio_val and isinstance(audio_val, str):
                                rand_val = random.random()
                                encoded_fn = urllib.parse.quote(audio_val)
                                val = f"/api/view?filename={encoded_fn}&type=input&subfolder=&rand={rand_val:.15f}"
                            else:
                                val = ""

                    if val is None:
                        val = ""

                    inputs[w_name] = val

            if "inputs" in node and isinstance(node["inputs"], list):
                for inp in node["inputs"]:
                    if isinstance(inp, dict):
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
                    break
        elif isinstance(workflow_data, dict):
            node_key = str(target_node_id)
            if node_key in workflow_data:
                node = workflow_data[node_key]
                if "inputs" in node and isinstance(node["inputs"], dict):
                    for k in ["image", "video", "audio", "upload"]:
                        if k in node["inputs"]:
                            node["inputs"][k] = filename
                            break
                    else:
                        node["inputs"]["image"] = filename
        return workflow_data

    def _override_workflow_parameter(self, workflow_data, target_node_id, param_name, value):
        if "nodes" in workflow_data and isinstance(workflow_data["nodes"], list):
            for node in workflow_data["nodes"]:
                if node.get("id") == target_node_id:
                    widgets = scan_standard_node_widgets(node, node.get("type"))
                    for w in widgets:
                        if w["name"] == param_name:
                            idx = w["idx"]
                            if "widgets_values" not in node or not isinstance(node["widgets_values"], list):
                                node["widgets_values"] = []
                            while len(node["widgets_values"]) <= idx:
                                node["widgets_values"].append(None)

                            try:
                                orig_val = node["widgets_values"][idx]
                                if orig_val is not None:
                                    if isinstance(orig_val, int):
                                        node["widgets_values"][idx] = int(value)
                                    elif isinstance(orig_val, float):
                                        node["widgets_values"][idx] = float(value)
                                    elif isinstance(orig_val, bool):
                                        node["widgets_values"][idx] = bool(value)
                                    else:
                                        node["widgets_values"][idx] = value
                                else:
                                    node["widgets_values"][idx] = value
                            except Exception:
                                node["widgets_values"][idx] = value

                            break
                    break
        elif isinstance(workflow_data, dict):
            node_key = str(target_node_id)
            if node_key in workflow_data:
                node = workflow_data[node_key]
                if "inputs" in node and isinstance(node["inputs"], dict):
                    node["inputs"][param_name] = value
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
    DISPLAY_NAME = "☁️RunningHub App"

    def execute_app(self, APP, params_json="{}", prompt=None, extra_pnginfo=None, unique_id=None, **kwargs):
        try:
            api_key, base_url = get_rh_config()
            if not api_key:
                raise Exception("RunningHub API Key is not configured. Please configure it in ComfyPanel settings.")
            if not APP or APP == "None":
                raise Exception("No App selected")

            web_app_id = None
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
            if not web_app_id:
                raise Exception("Missing web_app_id. Please reload or refresh the node.")

            send_progress_update(unique_id, 0.0, "Starting...")

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

                try:
                    send_progress_update(unique_id, 0.1, f"Uploading input {label}...")
                    field_val_str = process_and_upload_media(value, api_key, base_url, field_name)
                except Exception as upload_err:
                    logging.error(f"[RHWebApp] Failed to upload media for field '{field_name}': {upload_err}")

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

            send_progress_update(unique_id, 0.2, "Creating WebApp Task...")

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
                            send_progress_update(unique_id, simulated_progress, f"{status_str} ({elapsed}s)")
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

            send_progress_update(unique_id, 0.99, "Downloading results...")
            output_dir = os.path.join(folder_paths.get_output_directory(), "runninghub_webapp")
            result_outputs = download_outputs(outputs, output_dir, f"rh_{task_id}_{web_app_id}")

            send_progress_update(unique_id, 1.0, "Success", "Task Finished")

            return {
                "ui": {
                    "status": {"type": "success", "message": "Task Completed", "task_id": task_id}
                },
                "result": (result_outputs,)
            }

        except BaseException as e:

            status = "Cancelled" if "interrupt" in str(e).lower() or isinstance(e, KeyboardInterrupt) else "Failed"
            send_progress_update(unique_id, 0.0, status, str(e))
            logging.error(f"[RHWebApp] Error executing app: {e}", exc_info=True)
            raise e

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

            if not (isinstance(v, list) and len(v) == 2):
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

def scan_standard_node_widgets(node, class_type):
    node_class = nodes.NODE_CLASS_MAPPINGS.get(class_type)
    if not node_class:
        return []
    try:
        input_types = node_class.INPUT_TYPES()
    except Exception:
        return []

    linked_input_names = set()
    if "inputs" in node and isinstance(node["inputs"], list):
        for inp in node["inputs"]:
            if isinstance(inp, dict) and inp.get("link") is not None:
                linked_input_names.add(inp.get("name"))

    widgets_values = node.get("widgets_values", [])
    expected_slots = []
    widget_val_idx = 0

    def process_section_inputs(inputs_dict, prefix=""):
        nonlocal widget_val_idx
        for name, config in inputs_dict.items():
            if name in linked_input_names:
                continue
            if not isinstance(config, (list, tuple)) or len(config) == 0:
                continue

            w_type = str(config[0])
            full_name = f"{prefix}.{name}" if prefix else name
            expected_slots.append({"name": full_name, "type": w_type})

            val = None
            if widget_val_idx < len(widgets_values):
                val = widgets_values[widget_val_idx]

            widget_val_idx += 1

            if name in ["seed", "noise_seed"]:
                expected_slots.append({"name": f"{prefix}.control_after_generate" if prefix else "control_after_generate", "type": "COMBO", "virtual": True})
                widget_val_idx += 1

            if w_type == "COMFY_DYNAMICCOMBO_V3" and isinstance(val, str) and len(config) > 1 and isinstance(config[1], dict):
                options = config[1].get("options", [])
                for opt in options:
                    if isinstance(opt, dict) and opt.get("key") == val:
                        opt_inputs = opt.get("inputs", {})
                        for sub_sec in ["required", "optional"]:
                            if sub_sec in opt_inputs and isinstance(opt_inputs[sub_sec], dict):
                                process_section_inputs(opt_inputs[sub_sec], prefix=full_name)

    for section in ["required", "optional"]:
        if section in input_types and isinstance(input_types[section], dict):
            process_section_inputs(input_types[section])

    ui_widgets = []
    if "inputs" in node and isinstance(node["inputs"], list):
        for inp in node["inputs"]:
            if isinstance(inp, dict) and "widget" in inp:
                w_name = inp["widget"].get("name") or inp.get("name")
                if w_name and w_name not in linked_input_names:
                    ui_widgets.append(w_name)

    expected_names = [slot["name"] for slot in expected_slots if not slot.get("virtual")]

    final_slots = []
    for slot in expected_slots:
        if not slot.get("virtual"):
            final_slots.append(slot)

    for ui_w in ui_widgets:
        if ui_w not in expected_names:
            final_slots.append({"name": ui_w, "type": "STRING"})

    widgets_list = []
    for idx, slot in enumerate(final_slots):
        val = None
        if idx < len(widgets_values):
            val = widgets_values[idx]

        widgets_list.append({
            "nodeId": node.get("id"),
            "nodeType": class_type,
            "name": slot["name"],
            "type": slot["type"],
            "value": val,
            "idx": idx
        })

    return widgets_list