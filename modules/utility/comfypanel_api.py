import aiohttp
import asyncio
import folder_paths
import hashlib
import io
import json
import logging
import os
import platform
import requests
import shutil
import subprocess
import urllib.parse
from aiohttp import web, ClientError
from server import PromptServer
from PIL import Image, ImageOps
from .comfypanel_config import read_config, write_config, get_rh_config

def _is_safe_path(target_path: str, base_dir: str) -> bool:
    """Verify target_path is strictly contained inside base_dir using realpath + commonpath."""
    try:
        real_target = os.path.realpath(target_path)
        real_base = os.path.realpath(base_dir)
        return os.path.commonpath([real_target, real_base]) == real_base
    except Exception:
        return False

ALLOWED_RUNNINGHUB_HOSTS = {
    "runninghub.cn", "www.runninghub.cn", "api.runninghub.cn",
    "runninghub.ai", "www.runninghub.ai", "api.runninghub.ai"
}

def _is_allowed_rh_host(base_url: str) -> bool:
    """Ensure outgoing proxy requests only target official RunningHub endpoints."""
    try:
        parsed = urllib.parse.urlparse(base_url)
        host = (parsed.hostname or "").lower()
        if host in ALLOWED_RUNNINGHUB_HOSTS:
            return True
        if host.endswith(".runninghub.cn") or host.endswith(".runninghub.ai"):
            return True
        return False
    except Exception:
        return False

def _install_comfypanel_cors():
    if not hasattr(PromptServer, 'instance') or PromptServer.instance is None:
        return
    app = getattr(PromptServer.instance, 'app', None)
    if not app:
        return
    for i, mw in enumerate(app.middlewares):
        if getattr(mw, '__name__', '') == 'origin_only_middleware':
            _orig = mw

            @web.middleware
            async def comfypanel_cors_middleware(request: web.Request, handler, _orig=_orig):
                req_origin = request.headers.get('Origin', '')

                if req_origin.startswith('file://'):
                    if request.method == "OPTIONS":
                        resp = web.Response()
                    else:
                        resp = await handler(request)
                    resp.headers['Access-Control-Allow-Origin'] = req_origin
                    resp.headers['Access-Control-Allow-Credentials'] = 'true'
                    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, PS-UXP-Client, ps-uxp-client'
                    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                    return resp
                return await _orig(request, handler)

            app.middlewares[i] = comfypanel_cors_middleware
            return

_install_comfypanel_cors()

def _get_uxp_dir(plugin_root):
    """
    Dynamically find the UXP assets directory by looking for manifest.json.
    This allows the folder (default 'photoshop_plugin/ComfyPanel') to be renamed by the user.
    """
    try:
        if os.path.exists(plugin_root) and os.path.isdir(plugin_root):
            for item in os.listdir(plugin_root):
                item_path = os.path.join(plugin_root, item)
                if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "manifest.json")):
                    return item_path
    except Exception:
        pass

    raise FileNotFoundError(f"Could not find UXP assets directory containing manifest.json in {plugin_root}")

@PromptServer.instance.routes.post("/comfypanel/upload_from_path")
async def upload_from_local_path(request):
    """
    Copy a local file (already on disk) directly into ComfyUI's input folder.
    This avoids the PS → IPC → ComfyUI binary transfer that causes OOM on large images.

    Body JSON: { "filePath": "/abs/path/to/file.png", "fileName": "upload_name.png" }
    Returns: { "success": true, "fileName": "upload_name.png" }
    """
    try:
        body = await request.json()
        src_path = body.get("filePath", "")
        dest_name = body.get("fileName", "")

        if src_path and len(src_path) >= 3 and src_path[0] == '/' and src_path[2] == ':':
            src_path = src_path[1:]

        if not src_path:
            return web.json_response({"success": False, "error": "filePath is required"}, status=400)

        input_dir = folder_paths.get_input_directory()

        abs_src = os.path.realpath(src_path)
        real_input = os.path.realpath(input_dir)

        if _is_safe_path(abs_src, real_input):
            rel_name = os.path.relpath(abs_src, real_input).replace("\\", "/")
            return web.json_response({"success": True, "fileName": rel_name})

        safe_name = os.path.basename(dest_name or src_path)
        if not safe_name:
            return web.json_response({"success": False, "error": "Invalid target filename"}, status=400)

        dest_path = os.path.join(real_input, safe_name)
        if not _is_safe_path(dest_path, real_input):
            return web.json_response({"success": False, "error": "Access denied: destination outside input directory"}, status=403)

        shutil.copy2(src_path, dest_path)
        return web.json_response({"success": True, "fileName": safe_name})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get("/comfypanel/dirs")
async def get_comfy_dirs(request):
    """
    Return absolute paths for ComfyUI input and output directories.
    Used by the plugin to construct file:// URLs directly, avoiding HTTP download.
    """
    return web.json_response({
        "input": folder_paths.get_input_directory(),
        "output": folder_paths.get_output_directory(),
        "temp": folder_paths.get_temp_directory(),
    })

@PromptServer.instance.routes.get("/comfypanel/output_files")
async def list_output_files(request):
    """
    List all media files in ComfyUI's output folder (recursively optional).
    Returns file list with name, path, mtime for use in history panel.
    No filename filtering — let the JS side decide what to show.
    """
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
    VIDEO_EXTS = {'.mp4', '.webm', '.mov', '.avi'}
    AUDIO_EXTS = {'.mp3', '.wav', '.ogg', '.flac'}
    MODEL3D_EXTS = {'.glb', '.gltf', '.obj', '.fbx', '.usdz'}
    ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS | MODEL3D_EXTS

    output_dir = folder_paths.get_output_directory()
    files = []

    dirs_to_scan = [output_dir]
    try:
        for entry in os.scandir(output_dir):
            if entry.is_dir():
                dirs_to_scan.append(entry.path)
    except Exception:
        pass

    seen_paths = set()
    try:
        for scan_dir in dirs_to_scan:
            for entry in os.scandir(scan_dir):
                if entry.is_file() and entry.path not in seen_paths:
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in ALL_EXTS:
                        seen_paths.add(entry.path)

                        rel_name = os.path.relpath(entry.path, output_dir).replace("\\", "/")
                        files.append({
                            "name": rel_name,
                            "nativePath": entry.path,
                            "mtime": entry.stat().st_mtime,
                        })

        files.sort(key=lambda x: x["mtime"], reverse=True)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

    return web.json_response({"success": True, "files": files})

@PromptServer.instance.routes.get("/comfypanel/input_files")
async def list_input_files(request):
    """
    List all media files in ComfyUI's input folder.
    Returns file list with name and nativePath for load media dropdown.
    """
    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
    VIDEO_EXTS = {'.mp4', '.webm', '.mov', '.avi'}
    AUDIO_EXTS = {'.mp3', '.wav', '.ogg', '.flac'}
    MODEL3D_EXTS = {'.glb', '.gltf', '.obj', '.fbx', '.usdz'}
    ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS | MODEL3D_EXTS

    input_dir = folder_paths.get_input_directory()
    files = []
    seen_paths = set()

    try:
        if os.path.exists(input_dir):
            for entry in os.scandir(input_dir):
                if entry.is_file() and entry.path not in seen_paths:
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in ALL_EXTS:
                        seen_paths.add(entry.path)
                        files.append({
                            "name": entry.name,
                            "nativePath": entry.path,
                            "mtime": entry.stat().st_mtime,
                        })
            files.sort(key=lambda x: x["name"].lower())
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

    return web.json_response({"success": True, "files": files})

@PromptServer.instance.routes.get("/comfypanel/thumbnail")
async def get_thumbnail(request):
    """
    Generate or return a cached thumbnail for an image.
    Supports two modes:
      - filename[+subfolder]: looks up in ComfyUI output folder
      - path: absolute path, allowed for ComfyUI dirs or Adobe/UXP/PluginsStorage
    Returns a WebP image.
    """
    try:
        path_param = request.query.get("path", "")
        filename = request.query.get("filename", "")
        subfolder = request.query.get("subfolder", "")
        size = int(request.query.get("size", 256))

        output_dir = folder_paths.get_output_directory()

        input_dir = folder_paths.get_input_directory()
        output_abs = os.path.abspath(output_dir)
        temp_abs = os.path.abspath(folder_paths.get_temp_directory())
        input_abs = os.path.abspath(input_dir)
        allowed_roots = [output_abs, temp_abs, input_abs]

        if path_param:

            try:
                decoded = urllib.parse.unquote(path_param)
            except Exception:
                decoded = path_param
            file_path = os.path.abspath(decoded)
            is_allowed = any(file_path == root or file_path.startswith(root + os.sep)
                             for root in allowed_roots) or (
                         "Adobe" in file_path and "UXP" in file_path and "PluginsStorage" in file_path)
            if not is_allowed:
                return web.Response(status=403, text="Access denied")
        else:
            if not filename:
                return web.Response(status=400, text="No filename")
            temp_dir = folder_paths.get_temp_directory()

            candidate_path = None
            for base in [output_dir, temp_dir, input_dir]:
                p = os.path.abspath(os.path.join(base, subfolder, filename))
                base_abs = os.path.abspath(base)
                if (p == base_abs or p.startswith(base_abs + os.sep)) and os.path.isfile(p):
                    candidate_path = p
                    break

            if not candidate_path:
                candidate_path = os.path.abspath(os.path.join(output_dir, subfolder, filename))

            file_path = candidate_path
            if not any(file_path == root or file_path.startswith(root + os.sep) for root in allowed_roots):
                return web.Response(status=403, text="Access denied")

        if not os.path.isfile(file_path):
            return web.Response(status=404, text="File not found")

        mtime = os.path.getmtime(file_path)

        path_hash = hashlib.md5(file_path.encode()).hexdigest()
        params_hash = hashlib.md5(f"{mtime}_{size}".encode()).hexdigest()

        temp_dir = folder_paths.get_temp_directory()
        cache_dir = os.path.join(temp_dir, "comfypanel_thumbs")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)

        cache_path = os.path.join(cache_dir, f"{path_hash}_{params_hash}.webp")

        if os.path.exists(cache_path):
            return web.FileResponse(cache_path)

        try:
            img = Image.open(file_path)
        except Exception:

            return web.Response(status=415, text="Unsupported file type")

        img = ImageOps.exif_transpose(img)
        img.thumbnail((size, size))

        output = io.BytesIO()
        img.save(output, format="WEBP", quality=85)
        img.close()

        webp_data = output.getvalue()

        try:
            with open(cache_path, "wb") as f:
                f.write(webp_data)
        except Exception:
            pass

        return web.Response(body=webp_data, content_type="image/webp")

    except Exception as e:
        return web.Response(status=500, text=str(e))

@PromptServer.instance.routes.post("/comfypanel/delete_output_file")
async def delete_output_file(request):
    """
    Delete a file from ComfyUI's output folder.
    Body JSON: { "name": "example.png" }
    """
    try:
        body = await request.json()
        name = body.get("name", "")
        if not name:
            return web.json_response({"success": False, "error": "No filename provided"}, status=400)

        output_dir = folder_paths.get_output_directory()
        file_path = os.path.abspath(os.path.join(output_dir, name))

        if not file_path.startswith(os.path.abspath(output_dir)):
            return web.json_response({"success": False, "error": "Access denied"}, status=403)

        if os.path.isfile(file_path):

            try:
                path_hash = hashlib.md5(file_path.encode()).hexdigest()
                temp_dir = folder_paths.get_temp_directory()
                cache_dir = os.path.join(temp_dir, "comfypanel_thumbs")
                if os.path.exists(cache_dir):
                    for f in os.listdir(cache_dir):
                        if f.startswith(path_hash):
                            try:
                                os.remove(os.path.join(cache_dir, f))
                            except Exception:
                                pass
            except Exception:
                pass

            os.remove(file_path)

            parent_dir = os.path.dirname(file_path)
            if parent_dir != os.path.abspath(output_dir):
                try:
                    if not os.listdir(parent_dir):
                        os.rmdir(parent_dir)
                except Exception:
                    pass

            return web.json_response({"success": True})
        else:
            return web.json_response({"success": False, "error": f"File not found: {name}"}, status=404)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get(r"/comfypanel/{folder}/{filepath:.*}")
async def get_comfypanel_static_file(request):
    try:
        folder = request.match_info.get("folder")
        filepath = request.match_info.get("filepath", "")

        if not filepath or folder not in ["custom", "default"]:
            return web.Response(status=403)

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        allowed_dir = os.path.realpath(os.path.join(plugin_root, folder))
        file_path = os.path.realpath(os.path.join(allowed_dir, filepath))

        if not _is_safe_path(file_path, allowed_dir) or not os.path.isfile(file_path):
            return web.Response(status=404)

        return web.FileResponse(file_path)

        return web.Response(status=404)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/open_user_config")
async def open_user_config(request):
    try:

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        config_path = os.path.abspath(os.path.join(plugin_root, "custom", "user_config.js"))

        if not os.path.exists(config_path):
            return web.json_response({"success": False, "error": f"custom/user_config.js not found at {config_path}"}, status=404)

        system = platform.system()
        if system == "Darwin":
            subprocess.call(["open", config_path])
        elif system == "Windows":
            editor_cmd = None
            if shutil.which("code"):
                editor_cmd = ["code", config_path]
            elif shutil.which("notepad++"):
                editor_cmd = ["notepad++", config_path]

            if editor_cmd:
                try:
                    subprocess.Popen(editor_cmd, shell=True)
                except Exception:
                    editor_cmd = None

            if not editor_cmd:
                common_paths = [
                    (os.path.expandvars(r"%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd"), True),
                    (os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\bin\code.cmd"), True),
                    (os.path.expandvars(r"%ProgramFiles(x86)%\Notepad++\notepad++.exe"), False),
                    (os.path.expandvars(r"%ProgramFiles%\Notepad++\notepad++.exe"), False),
                ]
                opened = False
                for path, use_shell in common_paths:
                    if os.path.exists(path):
                        try:
                            subprocess.Popen([path, config_path], shell=use_shell)
                            opened = True
                            break
                        except Exception:
                            continue
                if not opened:
                    try:
                        with open(config_path, "rb") as f:
                            content = f.read()
                        if not content.startswith(b"\xef\xbb\xbf"):
                            with open(config_path, "wb") as f:
                                f.write(b"\xef\xbb\xbf" + content)
                    except Exception:
                        pass
                    subprocess.Popen(["notepad.exe", config_path])
        else:
            subprocess.call(["xdg-open", config_path])

        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get("/comfypanel/userdata")
async def get_userdata_list(request):
    """
    List files in a specific userdata directory (e.g., /comfypanel/userdata?dir=workflows).
    Used by the logic bridge to populate the local workflows list.
    """
    try:
        directory = request.query.get("dir", "workflows")
        recurse = request.query.get("recurse", "false").lower() == "true"

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

        target_dir = folder_paths.get_user_directory() if hasattr(folder_paths, 'get_user_directory') else os.path.join(folder_paths.base_path, "user", "default")
        target_dir = os.path.join(target_dir, directory)

        if not os.path.exists(target_dir):

            target_dir = os.path.join(plugin_root, directory)
            if not os.path.exists(target_dir):
                return web.json_response([])

        files = []
        if recurse:
            for root, _, filenames in os.walk(target_dir):
                for filename in filenames:
                    if filename.endswith(".json"):
                        rel_path = os.path.relpath(os.path.join(root, filename), target_dir)
                        files.append(rel_path.replace("\\", "/"))
        else:
            for filename in os.listdir(target_dir):
                if filename.endswith(".json"):
                    files.append(filename)

        return web.json_response(files)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

_CDN_WORKFLOWS_BASE = "https://cdn.jsdelivr.net/gh/Ginolazy/ComfyPanel-defaults@main/workflows"

@PromptServer.instance.routes.get("/comfypanel/userdata/{filename:.*}")
async def get_userdata_file(request):
    """
    Read a specific JSON file from userdata (e.g., /comfypanel/userdata/workflows/my.json).
    Built-in workflows under default/workflows/ are served from CDN.
    """
    try:
        path = request.match_info.get("filename", "")
        if "%" in path:
            path = urllib.parse.unquote(path)

        if not path:
            return web.json_response({"error": "No filename specified"}, status=400)

        if path.startswith("default/workflows/"):
            filename = path[len("default/workflows/"):]
            cdn_url = f"{_CDN_WORKFLOWS_BASE}/{filename}"
            async with aiohttp.ClientSession() as session:
                async with session.get(cdn_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json(content_type=None)
            return web.json_response(data)

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

        user_dir = folder_paths.get_user_directory() if hasattr(folder_paths, 'get_user_directory') else os.path.join(folder_paths.base_path, "user", "default")
        full_path = os.path.realpath(os.path.join(user_dir, path))

        if not (_is_safe_path(full_path, user_dir) and os.path.isfile(full_path)):

            full_path = os.path.realpath(os.path.join(plugin_root, path))
            if not (_is_safe_path(full_path, plugin_root) and os.path.isfile(full_path)):
                return web.json_response({"error": f"File not found or access denied: {path}"}, status=404)

        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/userdata/{filename:.*}")
async def save_userdata_file(request):
    """
    Save a JSON file to userdata.
    """
    try:
        raw_path = request.match_info.get("filename", "")
        body = await request.json()

        sub_dir = os.path.dirname(raw_path)
        base_name = os.path.basename(raw_path)
        if not base_name or not base_name.endswith(".json"):
            return web.json_response({"success": False, "error": "Only .json files are allowed"}, status=400)

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        allowed_base = os.path.realpath(os.path.join(plugin_root, "custom"))
        os.makedirs(allowed_base, exist_ok=True)

        target_dir = os.path.realpath(os.path.join(allowed_base, sub_dir)) if sub_dir else allowed_base
        if not _is_safe_path(target_dir, allowed_base):
            return web.json_response({"success": False, "error": "Access denied"}, status=403)

        os.makedirs(target_dir, exist_ok=True)
        full_path = os.path.realpath(os.path.join(target_dir, base_name))
        if not _is_safe_path(full_path, allowed_base):
            return web.json_response({"success": False, "error": "Access denied"}, status=403)

        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)

        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get("/comfypanel/builtin_workflows")
async def get_builtin_workflows(request):
    """
    Fetch built-in workflow list from CDN manifest.
    """
    try:
        manifest_url = f"{_CDN_WORKFLOWS_BASE}/manifest.json"
        async with aiohttp.ClientSession() as session:
            async with session.get(manifest_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                workflows = await resp.json(content_type=None)
        return web.json_response({"success": True, "workflows": workflows})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/proxy")
async def runninghub_proxy(request):
    try:
        body = await request.json()
        endpoint = body.get("endpoint", "")
        method = body.get("method", "POST").upper()
        payload = body.get("body")
        headers = body.get("headers", {})
        base_url = body.get("baseUrl", "").strip()
        if not base_url:
            return web.json_response({"success": False, "error": "Missing baseUrl"}, status=400)

        if not _is_allowed_rh_host(base_url):
            return web.json_response({"success": False, "error": "Forbidden: Proxy target must be an official RunningHub host."}, status=403)

        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint

        if endpoint == '/prompt' and method == 'POST' and isinstance(payload, dict):
            prompt = payload.get("prompt", {})
            has_bridge = any(
                isinstance(n, dict) and n.get("class_type") == "RHWorkflow"
                for n in prompt.values()
            )
            if has_bridge:
                try:
                    from ..runninghub_bridge import expand_bridge_nodes

                    api_key = headers.get("Authorization", "").removeprefix("Bearer ").strip()
                    expanded = await expand_bridge_nodes(prompt, base_url, api_key)
                    payload = dict(payload)
                    payload["prompt"] = expanded
                except Exception as expand_err:
                    logging.error(f"[ComfyPanel Proxy] Bridge expand failed: {expand_err}", exc_info=True)
                    return web.json_response({"success": False, "error": f"Bridge expand error: {expand_err}"}, status=500)

        url = f"{base_url}{endpoint}"

        proxy_headers = {
            "Content-Type": "application/json"
        }

        for k, v in headers.items():
            proxy_headers[k] = v

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                if method == "POST":
                    async with session.post(url, json=payload, headers=proxy_headers, timeout=30) as resp:
                        try:
                            resp_json = await resp.json()
                            return web.json_response(resp_json, status=resp.status)
                        except Exception:
                            text = await resp.text()
                            return web.Response(body=text, status=resp.status, content_type=resp.content_type)
                else:
                    async with session.get(url, params=payload, headers=proxy_headers, timeout=30) as resp:
                        try:
                            resp_json = await resp.json()
                            return web.json_response(resp_json, status=resp.status)
                        except Exception:
                            text = await resp.text()
                            return web.Response(body=text, status=resp.status, content_type=resp.content_type)
        except (ClientError, ConnectionResetError, asyncio.TimeoutError) as net_err:
            logging.error(f"[ComfyPanel Proxy] Network error: {net_err}", exc_info=True)
            return web.json_response({"success": False, "error": f"Network request failed: {net_err}"}, status=502)
    except Exception as e:
        logging.error(f"[ComfyPanel Proxy] Proxy exception: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/upload_proxy")
async def runninghub_upload_proxy(request):
    try:
        body = await request.json()
        filename = body.get("filename", "")
        base_url = body.get("baseUrl", "").strip()
        api_key = body.get("apiKey", "")
        if not base_url:
            return web.json_response({"success": False, "error": "Missing baseUrl"}, status=400)

        if not _is_allowed_rh_host(base_url):
            return web.json_response({"success": False, "error": "Forbidden: Proxy target must be an official RunningHub host."}, status=403)

        if not filename:
            return web.json_response({"success": False, "error": "No filename provided"}, status=400)

        input_dir = folder_paths.get_input_directory()
        real_input = os.path.realpath(input_dir)
        file_path = os.path.realpath(os.path.join(real_input, filename))
        if not (_is_safe_path(file_path, real_input) and os.path.isfile(file_path)):
            return web.json_response({"success": False, "error": f"File not found: {filename}"}, status=404)

        url = f"{base_url}/openapi/v2/media/upload/binary"
        try:
            async with aiohttp.ClientSession() as session:
                with open(file_path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field("file", f, filename=filename)
                    headers = {}
                    if api_key:
                        headers["Authorization"] = f"Bearer {api_key}"
                    async with session.post(url, data=data, headers=headers) as resp:
                        resp_json = await resp.json()
                        return web.json_response(resp_json, status=resp.status)
        except (ClientError, ConnectionResetError, asyncio.TimeoutError) as net_err:
            logging.error(f"[ComfyPanel Proxy] Upload proxy network error: {net_err}", exc_info=True)
            return web.json_response({"success": False, "error": f"Upload network error: {net_err}"}, status=502)
        except Exception as e:
            logging.error(f"[ComfyPanel Proxy] Upload proxy exception: {e}", exc_info=True)
            return web.json_response({"success": False, "error": str(e)}, status=500)
    except Exception as e:
        logging.error(f"[ComfyPanel Proxy] Upload proxy exception: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/download_image")
async def runninghub_download_image(request):
    try:
        body = await request.json()
        image_url = body.get("imageUrl", "")
        filename = body.get("filename", "")
        subfolder = body.get("subfolder", "")
        img_type = body.get("type", "output")
        api_key = body.get("apiKey", "")

        if not image_url or not filename:
            return web.json_response({"success": False, "error": "Missing parameters"}, status=400)

        if img_type == "temp":
            base_dir = folder_paths.get_temp_directory()
        else:
            base_dir = folder_paths.get_output_directory()

        if not subfolder and img_type != "temp":
            subfolder = "comfypanel_results"

        target_dir = os.path.abspath(os.path.join(base_dir, subfolder))
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(target_dir, filename))
        if not file_path.startswith(os.path.abspath(base_dir)):
            return web.json_response({"success": False, "error": "Access denied"}, status=403)

        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        with open(file_path, "wb") as f:
                            f.write(data)
                        logging.info(f"[RH] Successfully downloaded {img_type} image to {file_path}")
                        return web.json_response({"success": True, "localPath": file_path})
                    else:
                        err_msg = f"Cloud download returned HTTP {resp.status}"
                        logging.error(f"[RH] Download failed: {err_msg}")
                        return web.json_response({"success": False, "error": err_msg}, status=400)
        except (ClientError, ConnectionResetError, asyncio.TimeoutError) as net_err:
            logging.error(f"[ComfyPanel] Download image network error: {net_err}", exc_info=True)
            return web.json_response({"success": False, "error": f"Download network error: {net_err}"}, status=502)
        except Exception as e:
            logging.error(f"[ComfyPanel] Download image exception: {e}", exc_info=True)
            return web.json_response({"success": False, "error": str(e)}, status=500)
    except Exception as e:
        logging.error(f"[ComfyPanel] Download image exception: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/scan_workflow")
async def runninghub_scan_workflow(request):
    try:
        body = await request.json()
        workflow_file = body.get("workflow_file", "")
        source_type = body.get("source_type", "local_json")
        workflow_val = workflow_file.strip()
        is_api_mode = workflow_val.isdigit() and len(workflow_val) == 19
        if not workflow_file:
            return web.json_response({"success": False, "error": "Missing workflow_file parameter"}, status=400)

        data = None
        if is_api_mode or source_type == "runninghub_api":
            api_key, base_url = get_rh_config()
            if not api_key:
                return web.json_response({"success": False, "error": "RunningHub API Key is not configured!"}, status=400)

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            clean_base_domain = base_url.strip().rstrip("/")
            if not clean_base_domain.startswith("http"):
                clean_base_domain = "https://www.runninghub.cn"

            fetch_url = f"{clean_base_domain}/api/workflow/export"
            try:
                resp = requests.post(fetch_url, json={"workflowId": workflow_val}, headers=headers, timeout=15)
                if resp.status_code != 200:
                    return web.json_response({"success": False, "error": f"RunningHub API returned HTTP {resp.status_code}"}, status=resp.status_code)
                res_json = resp.json()
                if "code" in res_json and res_json.get("code") != 0:
                    msg = res_json.get("msg") or res_json.get("message") or "Unknown error"
                    return web.json_response({"success": False, "error": msg}, status=400)

                if "nodes" in res_json:
                    data = res_json
                elif "data" in res_json:
                    data_val = res_json.get("data")
                    if isinstance(data_val, str):
                        data = json.loads(data_val)
                    elif isinstance(data_val, dict):
                        data = data_val
                    else:
                        data = res_json
                else:
                    data = res_json
            except Exception as e:
                return web.json_response({"success": False, "error": f"Failed to fetch workflow from API: {str(e)}"}, status=500)
        else:

            input_dir = folder_paths.get_input_directory()
            real_input = os.path.realpath(input_dir)
            clean_name = os.path.basename(workflow_file)

            possible_paths = [
                os.path.realpath(os.path.join(real_input, "workflows", workflow_file)),
                os.path.realpath(os.path.join(real_input, "workflows", clean_name)),
                os.path.realpath(os.path.join(real_input, workflow_file)),
                os.path.realpath(os.path.join(real_input, clean_name)),
            ]

            resolved_path = None
            for p in possible_paths:
                if _is_safe_path(p, real_input) and os.path.isfile(p):
                    resolved_path = p
                    break

            if not resolved_path:
                return web.json_response({"success": False, "error": f"Workflow file not found or access denied: {workflow_file}"}, status=404)
            with open(resolved_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        WHITELIST_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "BOOL", "NUMBER"}

        EXCLUDE_WIDGET_KEYWORDS = {
            "name", "model", "ckpt", "lora", "vae", "unet", "clip", "device",
            "dtype", "scheduler", "sampler", "file", "path", "upscale", "save_prefix"
        }

        widgets = []
        nodes_list = data.get("nodes", []) if isinstance(data, dict) else []
        for node in nodes_list:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            node_type = node.get("type", "")

            node_mode = node.get("mode", 0)
            if node_mode in [2, 4]:
                continue

            lower_type = str(node_type).lower()
            node_title = node.get("title", "").strip()

            if "loadimage" in lower_type or "load_image" in lower_type:
                has_link = any(any(x is not None for x in out.get("links", [])) for out in node.get("outputs", []) if isinstance(out, dict))
                if not has_link:
                    continue

                is_mask = "mask" in lower_type
                widgets.append({
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "nodeTitle": node_title,
                    "name": "mask" if is_mask else "image",
                    "type": "MASK_INPUT_SLOT" if is_mask else "IMAGE_INPUT_SLOT",
                    "value": ""
                })
                continue
            elif "loadvideo" in lower_type or "load_video" in lower_type:
                has_link = any(any(x is not None for x in out.get("links", [])) for out in node.get("outputs", []) if isinstance(out, dict))
                if not has_link:
                    continue

                widgets.append({
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "nodeTitle": node_title,
                    "name": "video",
                    "type": "VIDEO_INPUT_SLOT",
                    "value": ""
                })
                continue
            elif "loadaudio" in lower_type or "load_audio" in lower_type:
                has_link = any(any(x is not None for x in out.get("links", [])) for out in node.get("outputs", []) if isinstance(out, dict))
                if not has_link:
                    continue

                widgets.append({
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "nodeTitle": node_title,
                    "name": "audio",
                    "type": "AUDIO_INPUT_SLOT",
                    "value": ""
                })
                continue

            if "saveimage" in lower_type or "save_image" in lower_type:
                has_link = any(inp.get("link") is not None for inp in node.get("inputs", []) if isinstance(inp, dict))
                if not has_link:
                    continue

                widgets.append({
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "nodeTitle": node_title,
                    "name": "image",
                    "type": "IMAGE_OUTPUT_SLOT",
                    "value": ""
                })
                continue
            elif "savevideo" in lower_type or "save_video" in lower_type or "videocombine" in lower_type or "vhs_videocombine" in lower_type:
                has_link = any(inp.get("link") is not None for inp in node.get("inputs", []) if isinstance(inp, dict))
                if not has_link:
                    continue

                widgets.append({
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "nodeTitle": node_title,
                    "name": "video",
                    "type": "VIDEO_OUTPUT_SLOT",
                    "value": ""
                })
                continue
            elif "saveaudio" in lower_type or "save_audio" in lower_type:
                has_link = any(inp.get("link") is not None for inp in node.get("inputs", []) if isinstance(inp, dict))
                if not has_link:
                    continue

                widgets.append({
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "nodeTitle": node_title,
                    "name": "audio",
                    "type": "AUDIO_OUTPUT_SLOT",
                    "value": ""
                })
                continue

            if any(kw in lower_type for kw in ["loader", "checkpoint", "loraloader", "vaeloader", "model"]):
                continue

            from ..runninghub_bridge import scan_standard_node_widgets
            node_widgets = scan_standard_node_widgets(node, node_type)
            for w in node_widgets:
                widget_name = w["name"]
                widget_type = w["type"]
                value = w["value"]

                if widget_type not in WHITELIST_TYPES:
                    continue

                if any(kw in widget_name.lower() for kw in EXCLUDE_WIDGET_KEYWORDS):
                    continue

                widgets.append({
                    "nodeId": node_id,
                    "nodeType": node_type,
                    "nodeTitle": node_title,
                    "name": widget_name,
                    "type": widget_type,
                    "value": value
                })

        return web.json_response({"success": True, "widgets": widgets})
    except Exception as e:
        logging.error(f"[ComfyPanel Linker API] Scan workflow exception: {e}", exc_info=True)
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/save_config")
async def runninghub_save_config(request):
    try:
        body = await request.json()
        api_key = body.get("apiKey", "").strip()
        base_url = body.get("baseUrl", "").strip()
        updates = {}
        if base_url:
            updates["ComfyPanel.RunningHub.baseUrl"] = base_url

        current_cfg = read_config()
        effective_base_url = base_url or current_cfg.get("ComfyPanel.RunningHub.baseUrl", "https://www.runninghub.cn")
        is_en = "runninghub.ai" in effective_base_url
        key_name = "ComfyPanel.RunningHubEn.apikey" if is_en else "ComfyPanel.RunningHubZh.apikey"

        if api_key:
            updates[key_name] = api_key

        if not updates:
            return web.json_response({"success": False, "error": "No valid configuration values provided."}, status=400)
        write_config(updates)
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

def _mask_key(key: str) -> str:
    """Mask sensitive API key to prevent exfiltration."""
    if not key:
        return ""
    if len(key) <= 8:
        return "********"
    return f"{key[:4]}****{key[-4:]}"

@PromptServer.instance.routes.get("/comfypanel/runninghub/get_config")
async def runninghub_get_config(request):
    try:
        query_base_url = request.query.get("baseUrl", "")
        cfg = read_config()
        api_key, base_url = get_rh_config(provided_base_url=query_base_url or None)

        key_zh = cfg.get("ComfyPanel.RunningHubZh.apikey", "")
        key_en = cfg.get("ComfyPanel.RunningHubEn.apikey", "")

        return web.json_response({
            "success": True,
            "apiKey": _mask_key(api_key),
            "baseUrl": base_url,
            "hasApiKey": bool(api_key),
            "apiKeyZh": _mask_key(key_zh),
            "apiKeyEn": _mask_key(key_en),
            "hasApiKeyZh": bool(key_zh),
            "hasApiKeyEn": bool(key_en)
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/upload_workflow")
async def runninghub_upload_workflow(request):
    try:
        post_data = await request.post()
        file_field = post_data.get("file")
        if not file_field:
            return web.json_response({"success": False, "error": "No file uploaded"}, status=400)

        raw_name = getattr(file_field, "filename", "")
        filename = os.path.basename(raw_name)
        if not filename or not filename.endswith('.json'):
            return web.json_response({"success": False, "error": "Only .json files are allowed"}, status=400)

        input_dir = folder_paths.get_input_directory()
        real_input = os.path.realpath(input_dir)
        workflows_dir = os.path.realpath(os.path.join(real_input, "workflows"))
        os.makedirs(workflows_dir, exist_ok=True)

        target_path = os.path.realpath(os.path.join(workflows_dir, filename))
        if not _is_safe_path(target_path, workflows_dir):
            return web.json_response({"success": False, "error": "Access denied: destination outside workflows directory"}, status=403)

        file_data = file_field.file.read()
        with open(target_path, 'wb') as f:
            f.write(file_data)

        logging.info(f"[Linker] Uploaded workflow file saved to: {target_path}")
        return web.json_response({"success": True, "filename": filename})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

_ext_browser_ws = None
_ext_uxp_ws = None
_ext_active_workflow = {"name": "", "toolId": "", "alive": False}

@PromptServer.instance.routes.get("/comfypanel/ws/ext_bridge")
async def comfypanel_ws_ext_bridge(request):
    global _ext_browser_ws, _ext_uxp_ws, _ext_active_workflow
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)

    role = request.query.get("role", "browser")

    if role == "browser":
        _ext_browser_ws = ws
        _ext_active_workflow["alive"] = True

        if _ext_uxp_ws and not _ext_uxp_ws.closed:
            try:
                await _ext_uxp_ws.send_json({
                    "type": "EXT_BROWSER_STATUS",
                    "alive": True,
                    "workflow": _ext_active_workflow
                })
            except Exception:
                pass
    else:
        _ext_uxp_ws = ws
        logging.info("[ComfyPanel ExtBridge] UXP client connected")

        await ws.send_json({
            "type": "EXT_BROWSER_STATUS",
            "alive": (_ext_browser_ws is not None and not _ext_browser_ws.closed),
            "workflow": _ext_active_workflow
        })

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    payload = json.loads(msg.data)
                except Exception:
                    payload = {}

                msg_type = payload.get("type")

                if msg_type == "EXT_WORKFLOW_STATE":
                    _ext_active_workflow = {
                        "name": payload.get("name", ""),
                        "toolId": payload.get("toolId", ""),
                        "alive": True
                    }
                    if _ext_uxp_ws and not _ext_uxp_ws.closed:
                        try:
                            await _ext_uxp_ws.send_json({
                                "type": "EXT_BROWSER_STATUS",
                                "alive": True,
                                "workflow": _ext_active_workflow
                            })
                        except Exception:
                            pass

                elif role == "uxp" and _ext_browser_ws and not _ext_browser_ws.closed:
                    try:
                        await _ext_browser_ws.send_str(msg.data)
                    except Exception:
                        pass
                elif role == "browser" and _ext_uxp_ws and not _ext_uxp_ws.closed:
                    try:
                        await _ext_uxp_ws.send_str(msg.data)
                    except Exception:
                        pass

            elif msg.type == aiohttp.WSMsgType.ERROR:
                break
    finally:
        if role == "browser" and _ext_browser_ws == ws:
            _ext_browser_ws = None
            _ext_active_workflow["alive"] = False
            if _ext_uxp_ws and not _ext_uxp_ws.closed:
                try:
                    await _ext_uxp_ws.send_json({
                        "type": "EXT_BROWSER_STATUS",
                        "alive": False,
                        "workflow": {"name": "", "toolId": "", "alive": False}
                    })
                except Exception:
                    pass
        elif role == "uxp" and _ext_uxp_ws == ws:
            _ext_uxp_ws = None

    return ws