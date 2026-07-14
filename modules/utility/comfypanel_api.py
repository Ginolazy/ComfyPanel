import shutil
import os
import io
import hashlib
import logging
import urllib.parse
import folder_paths
import platform
import subprocess
import json
from aiohttp import web
from server import PromptServer
from PIL import Image, ImageOps
from .comfypanel_tunnel import tunnel_manager

def _patch_origin_middleware():
    app = PromptServer.instance.app
    for i, mw in enumerate(app.middlewares):
        name = getattr(mw, '__name__', '')
        if 'origin' in name.lower():
            original = mw

            @web.middleware
            async def patched(request, handler, _orig=original):
                normalized = request.path.lstrip('/')
                req_origin = request.headers.get('Origin', '')
                is_file_origin = req_origin.startswith('file://')
                allowed_prefixes = ['comfypanel/', 'comfypanel', 'view', 'api/view']
                const_match = any(normalized == prefix or normalized.startswith(prefix + '/') or normalized.startswith(prefix)
                                  for prefix in allowed_prefixes)
                if is_file_origin or const_match:
                    if request.method == "OPTIONS":
                        resp = web.Response()
                    else:
                        resp = await handler(request)

                    if req_origin:
                        resp.headers['Access-Control-Allow-Origin'] = req_origin
                        resp.headers['Access-Control-Allow-Credentials'] = 'true'
                    else:
                        resp.headers['Access-Control-Allow-Origin'] = '*'

                    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, token, PS-UXP-Client, ps-uxp-client'
                    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                    return resp
                return await _orig(request, handler)

            app.middlewares[i] = patched
            logging.info("[ComfyPanel] Patched origin middleware to whitelist /comfypanel/ routes")
            return
    logging.debug("[ComfyPanel] No origin middleware found (CORS mode or newer ComfyUI), skipping patch")

try:
    _patch_origin_middleware()
except Exception as e:
    logging.warning(f"[ComfyPanel] Failed to patch origin middleware: {e}")

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

        if not src_path or not os.path.isfile(src_path):
            return web.json_response({"success": False, "error": f"Source file not found: {src_path}"}, status=400)

        input_dir = folder_paths.get_input_directory()

        abs_src = os.path.abspath(src_path)
        abs_input = os.path.abspath(input_dir)

        if abs_src.startswith(abs_input) and os.path.isfile(abs_src):
            rel_name = os.path.relpath(abs_src, abs_input).replace("\\", "/")
            return web.json_response({"success": True, "fileName": rel_name, "optimization": "zero_copy"})

        if not dest_name:
            dest_name = os.path.basename(src_path)

        dest_path = os.path.join(abs_input, dest_name)
        shutil.copy2(src_path, dest_path)
        return web.json_response({"success": True, "fileName": dest_name, "optimization": "copy"})
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

        if path_param:

            try:
                decoded = urllib.parse.unquote(path_param)
            except Exception:
                decoded = path_param
            file_path = os.path.abspath(decoded)
            output_abs = os.path.abspath(output_dir)
            temp_abs = os.path.abspath(folder_paths.get_temp_directory())
            is_allowed = any(file_path == root or file_path.startswith(root + os.sep)
                             for root in [output_abs, temp_abs]) or (
                         "Adobe" in file_path and "UXP" in file_path and "PluginsStorage" in file_path)
            if not is_allowed:
                return web.Response(status=403, text="Access denied")
        else:
            if not filename:
                return web.Response(status=400, text="No filename")
            temp_dir = folder_paths.get_temp_directory()
            output_abs = os.path.abspath(output_dir)
            temp_abs = os.path.abspath(temp_dir)

            candidate_path = os.path.abspath(os.path.join(output_dir, subfolder, filename))
            if not (candidate_path == output_abs or candidate_path.startswith(output_abs + os.sep)):
                candidate_path = os.path.abspath(os.path.join(temp_dir, subfolder, filename))

            file_path = candidate_path
            if not ((file_path == output_abs or file_path.startswith(output_abs + os.sep)) or
                    (file_path == temp_abs or file_path.startswith(temp_abs + os.sep))):
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
        filepath = request.match_info.get("filepath")

        if not filepath or ".." in filepath or folder not in ["custom", "default"]:
            return web.Response(status=403)

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        file_path = os.path.join(plugin_root, folder, filepath)

        if os.path.exists(file_path):
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

@PromptServer.instance.routes.get("/comfypanel/prompt_templates")
async def get_prompt_templates(request):
    try:
        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        templates_path = os.path.abspath(os.path.join(plugin_root, "default", "prompt_templates.json"))

        if not os.path.exists(templates_path):

            return web.json_response({})
        with open(templates_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/save_prompt_templates")
async def save_prompt_templates(request):
    try:
        body = await request.json()
        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        templates_path = os.path.abspath(os.path.join(plugin_root, "default", "prompt_templates.json"))

        os.makedirs(os.path.dirname(templates_path), exist_ok=True)
        with open(templates_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
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

@PromptServer.instance.routes.get("/comfypanel/userdata/{filename:.*}")
async def get_userdata_file(request):
    """
    Read a specific JSON file from userdata (e.g., /comfypanel/userdata/workflows/my.json).
    """
    import urllib.parse
    try:
        path = request.match_info.get("filename", "")
        if "%" in path:
            path = urllib.parse.unquote(path)

        if not path:
            return web.json_response({"error": "No filename specified"}, status=400)

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

        user_dir = folder_paths.get_user_directory() if hasattr(folder_paths, 'get_user_directory') else os.path.join(folder_paths.base_path, "user", "default")
        full_path = os.path.abspath(os.path.join(user_dir, path))

        if not os.path.exists(full_path):

            full_path = os.path.abspath(os.path.join(plugin_root, path))

        if not os.path.exists(full_path):
            return web.json_response({"error": f"File not found: {path}"}, status=404)

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
        path = request.match_info.get("filename", "")
        body = await request.json()

        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

        full_path = os.path.abspath(os.path.join(plugin_root, path))

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)

        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get("/comfypanel/builtin_workflows")
async def get_builtin_workflows(request):
    """
    Dedicated endpoint to fetch officially packaged built-in workflows.
    These are sourced explicitly from the ComfyPanel/workflows root directory.
    """
    try:
        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        target_dir = os.path.join(plugin_root, "default", "workflows")

        if not os.path.exists(target_dir):
            return web.json_response({"success": True, "workflows": []})

        workflows = []
        for filename in os.listdir(target_dir):
            if filename.endswith(".json"):
                full_path = os.path.join(target_dir, filename)
                base_name = filename[:-5]
                try:
                    cover_urls = []

                    svg_path = os.path.join(target_dir, f"{base_name}-cover.svg")
                    webp_cover_path = os.path.join(target_dir, f"{base_name}-cover.webp")
                    webp_path = os.path.join(target_dir, f"{base_name}.webp")

                    def to_file_uri(path):
                        clean_path = path.replace("\\", "/")

                        if not clean_path.startswith("/"):
                            clean_path = "/" + clean_path
                        return f"file://{clean_path}"

                    if os.path.exists(svg_path):
                        cover_urls.append(to_file_uri(svg_path))
                    elif os.path.exists(webp_cover_path):
                        cover_urls.append(to_file_uri(webp_cover_path))
                    elif os.path.exists(webp_path):
                        cover_urls.append(to_file_uri(webp_path))

                    workflows.append({
                        "name": filename,
                        "path": "default/workflows/" + filename,
                        "workflow": None,
                        "cover_urls": cover_urls
                    })
                except Exception as e:
                    pass

        return web.json_response({"success": True, "workflows": workflows})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/open_prompt_templates")
async def open_prompt_templates(request):
    try:
        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        templates_path = os.path.abspath(os.path.join(plugin_root, "default", "prompt_templates.json"))

        if not os.path.exists(templates_path):
            return web.json_response({"success": False, "error": f"prompt_templates.json not found at {templates_path}"}, status=404)

        system = platform.system()
        if system == "Darwin":
            subprocess.call(["open", templates_path])
        elif system == "Windows":
            os.startfile(templates_path)
        else:
            subprocess.call(["xdg-open", templates_path])
        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/tunnel/start")
async def start_tunnel(request):
    try:
        body = await request.json()
        server_addr = body.get("server_addr")
        server_port = body.get("server_port", 7000)
        token = body.get("token")
        remote_port = body.get("remote_port")
        subdomain = body.get("subdomain")
        local_port = body.get("local_port", 8188)

        if not all([server_addr, token]) or (not remote_port and not subdomain):
            return web.json_response({"success": False, "error": "Missing parameters"}, status=400)

        result = tunnel_manager.start(server_addr, server_port, token, remote_port, local_port, subdomain)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/tunnel/stop")
async def stop_tunnel(request):
    try:
        success = tunnel_manager.stop()
        return web.json_response({"success": success})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get("/comfypanel/tunnel/status")
async def get_tunnel_status(request):
    info = tunnel_manager.get_status_info()
    return web.json_response({
        "success": True,
        "status": info["status"],
        "running": info["running"],
        "error": info["error"],
        "remote_url": info["remote_url"]
    })

@PromptServer.instance.routes.post("/comfypanel/runninghub/proxy")
async def runninghub_proxy(request):
    try:
        body = await request.json()
        endpoint = body.get("endpoint", "")
        method = body.get("method", "POST").upper()
        payload = body.get("body")
        headers = body.get("headers", {})
        base_url = body.get("baseUrl", "")
        if not base_url:
            return web.json_response({"success": False, "error": "Missing baseUrl"})

        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint

        if endpoint == '/prompt' and method == 'POST' and isinstance(payload, dict):
            prompt = payload.get("prompt", {})
            has_bridge = any(
                isinstance(n, dict) and n.get("class_type") == "RHWorkflowBridge"
                for n in prompt.values()
            )
            if has_bridge:
                try:
                    from ..runninghub_bridge import expand_bridge_nodes

                    api_key = (
                        headers.get("Authorization", "").removeprefix("Bearer ").strip()
                        or headers.get("token", "")
                    )
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

        import aiohttp
        from aiohttp import ClientError
        import asyncio
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
        base_url = body.get("baseUrl", "")
        api_key = body.get("apiKey", "")
        if not base_url:
            return web.json_response({"success": False, "error": "Missing baseUrl"})

        if not filename:
            return web.json_response({"success": False, "error": "No filename provided"}, status=400)

        input_dir = folder_paths.get_input_directory()
        file_path = os.path.abspath(os.path.join(input_dir, filename))
        if not file_path.startswith(os.path.abspath(input_dir)) or not os.path.isfile(file_path):
            return web.json_response({"success": False, "error": f"File not found: {filename}"}, status=404)

        url = f"{base_url}/openapi/v2/media/upload/binary"
        import aiohttp
        from aiohttp import ClientError
        import asyncio
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
            headers["token"] = api_key

        import aiohttp
        from aiohttp import ClientError
        import asyncio
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
            config_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
            config_path = os.path.join(config_dir, ".runninghub_config")
            api_key = ""
            base_url = "https://www.runninghub.cn"
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#") or "=" not in line:
                                continue
                            key, val = line.split("=", 1)
                            if key.strip() == "runninghub_api_key":
                                api_key = val.strip()
                            elif key.strip() == "runninghub_base_url":
                                base_url = val.strip()
                except Exception:
                    pass
            if not api_key:
                return web.json_response({"success": False, "error": "RunningHub API Key is not configured!"}, status=400)

            import requests
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            clean_base_domain = base_url.strip().rstrip("/")
            if not clean_base_domain.startswith("http"):
                clean_base_domain = "https://www.runninghub.cn"

            fetch_url = f"{clean_base_domain}/api/openapi/getJsonApiFormat"
            payload = {
                "apiKey": api_key,
                "workflowId": workflow_file.strip()
            }
            try:
                resp = requests.post(fetch_url, json=payload, headers=headers, timeout=15)
                if resp.status_code != 200:
                    return web.json_response({"success": False, "error": f"RunningHub API returned HTTP {resp.status_code}"}, status=resp.status_code)
                res_json = resp.json()
                if res_json.get("code") != 0:
                    msg = res_json.get("msg") or res_json.get("message") or "Unknown error"
                    return web.json_response({"success": False, "error": msg}, status=400)

                data_val = res_json.get("data")
                if isinstance(data_val, str):
                    try:
                        parsed = json.loads(data_val)
                        if isinstance(parsed, dict) and "prompt" in parsed:
                            prompt_val = parsed.get("prompt")
                            data = json.loads(prompt_val) if isinstance(prompt_val, str) else prompt_val
                        else:
                            data = parsed
                    except Exception:
                        data = data_val
                elif isinstance(data_val, dict):
                    if "prompt" in data_val:
                        prompt_val = data_val.get("prompt")
                        data = json.loads(prompt_val) if isinstance(prompt_val, str) else prompt_val
                    else:
                        data = data_val
                else:
                    data = res_json
            except Exception as e:
                return web.json_response({"success": False, "error": f"Failed to fetch workflow from API: {str(e)}"}, status=500)
        else:

            possible_paths = [
                workflow_file,
                os.path.join(folder_paths.get_input_directory(), "workflows", workflow_file),
                os.path.join(folder_paths.get_input_directory(), workflow_file),
            ]

            resolved_path = None
            for p in possible_paths:
                if os.path.exists(p) and os.path.isfile(p):
                    resolved_path = p
                    break

            if not resolved_path:
                return web.json_response({"success": False, "error": f"Workflow file not found: {workflow_file}"}, status=404)
            with open(resolved_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        WHITELIST_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN", "BOOL", "NUMBER"}

        EXCLUDE_WIDGET_KEYWORDS = {
            "name", "model", "ckpt", "lora", "vae", "unet", "clip", "device",
            "dtype", "scheduler", "sampler", "file", "path", "upscale", "save_prefix"
        }

        widgets = []

        if "nodes" in data and isinstance(data["nodes"], list):
            for node in data["nodes"]:
                node_id = node.get("id")
                node_type = node.get("type")

                node_mode = node.get("mode", 0)
                if node_mode in [2, 4]:
                    continue

                lower_type = node_type.lower()
                node_title = node.get("title", "").strip()

                if "loadimage" in lower_type or "load_image" in lower_type:

                    has_link = False
                    outputs = node.get("outputs", [])
                    for out in outputs:
                        links = out.get("links")
                        if links and any(x is not None for x in links):
                            has_link = True
                            break
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
                    has_link = False
                    outputs = node.get("outputs", [])
                    for out in outputs:
                        links = out.get("links")
                        if links and any(x is not None for x in links):
                            has_link = True
                            break
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
                    has_link = False
                    outputs = node.get("outputs", [])
                    for out in outputs:
                        links = out.get("links")
                        if links and any(x is not None for x in links):
                            has_link = True
                            break
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

                    has_link = False
                    inputs = node.get("inputs", [])
                    for inp in inputs:
                        if inp.get("link") is not None:
                            has_link = True
                            break
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
                elif "savevideo" in lower_type or "save_video" in lower_type:
                    has_link = False
                    inputs = node.get("inputs", [])
                    for inp in inputs:
                        if inp.get("link") is not None:
                            has_link = True
                            break
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
                    has_link = False
                    inputs = node.get("inputs", [])
                    for inp in inputs:
                        if inp.get("link") is not None:
                            has_link = True
                            break
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

                widget_slots_inputs = []
                if "inputs" in node and isinstance(node["inputs"], list):
                    for inp in node["inputs"]:
                        if not isinstance(inp, dict):
                            continue
                        if inp.get("widget") or inp.get("type") == "COMBO":
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

                if "inputs" in node and isinstance(node["inputs"], list):
                    for inp in node["inputs"]:
                        w_info = inp.get("widget")
                        if w_info and isinstance(w_info, dict):
                            widget_name = w_info.get("name")
                            widget_type = str(inp.get("type", "STRING")).upper()

                            if widget_type not in WHITELIST_TYPES:
                                continue

                            lower_name = widget_name.lower()
                            if any(kw in lower_name for kw in EXCLUDE_WIDGET_KEYWORDS):
                                continue

                            is_linked = False
                            if "link" in inp and inp["link"] is not None:
                                if inp["link"]:
                                    is_linked = True

                            if not is_linked:
                                value = None
                                try:
                                    val_idx = widget_slots.index(inp)
                                    if "widgets_values" in node and len(node["widgets_values"]) > val_idx:
                                        value = node["widgets_values"][val_idx]
                                except Exception:
                                    pass

                                widgets.append({
                                    "nodeId": node_id,
                                    "nodeType": node_type,
                                    "name": widget_name,
                                    "type": widget_type,
                                    "value": value
                                })

                if "outputs" in node and isinstance(node["outputs"], list):
                    for out in node["outputs"]:
                        w_info = out.get("widget")
                        if w_info and isinstance(w_info, dict):
                            widget_name = w_info.get("name")
                            widget_type = str(out.get("type", "STRING")).upper()

                            if widget_type not in WHITELIST_TYPES:
                                continue

                            lower_name = widget_name.lower()
                            if any(kw in lower_name for kw in EXCLUDE_WIDGET_KEYWORDS):
                                continue

                            value = None
                            try:
                                val_idx = widget_slots.index(out)
                                if "widgets_values" in node and len(node["widgets_values"]) > val_idx:
                                    value = node["widgets_values"][val_idx]
                            except Exception:
                                pass

                            widgets.append({
                                "nodeId": node_id,
                                "nodeType": node_type,
                                "name": widget_name,
                                "type": widget_type,
                                "value": value
                            })
        else:

            for node_id, node in data.items():
                if not isinstance(node, dict):
                    continue
                class_type = node.get("class_type", "")
                lower_type = class_type.lower()
                inputs = node.get("inputs", {})
                if not isinstance(inputs, dict):
                    continue

                if "loadimage" in lower_type or "load_image" in lower_type:
                    widgets.append({
                        "nodeId": node_id,
                        "nodeType": class_type,
                        "name": "mask" if "mask" in lower_type else "image",
                        "type": "MASK_INPUT_SLOT" if "mask" in lower_type else "IMAGE_INPUT_SLOT",
                        "value": ""
                    })
                    continue
                elif "loadvideo" in lower_type or "load_video" in lower_type:
                    widgets.append({
                        "nodeId": node_id,
                        "nodeType": class_type,
                        "name": "video",
                        "type": "VIDEO_INPUT_SLOT",
                        "value": ""
                    })
                    continue
                elif "loadaudio" in lower_type or "load_audio" in lower_type:
                    widgets.append({
                        "nodeId": node_id,
                        "nodeType": class_type,
                        "name": "audio",
                        "type": "AUDIO_INPUT_SLOT",
                        "value": ""
                    })
                    continue

                if "saveimage" in lower_type or "save_image" in lower_type:
                    widgets.append({
                        "nodeId": node_id,
                        "nodeType": class_type,
                        "name": "image",
                        "type": "IMAGE_OUTPUT_SLOT",
                        "value": ""
                    })
                    continue
                elif "savevideo" in lower_type or "save_video" in lower_type:
                    widgets.append({
                        "nodeId": node_id,
                        "nodeType": class_type,
                        "name": "video",
                        "type": "VIDEO_OUTPUT_SLOT",
                        "value": ""
                    })
                    continue
                elif "saveaudio" in lower_type or "save_audio" in lower_type:
                    widgets.append({
                        "nodeId": node_id,
                        "nodeType": class_type,
                        "name": "audio",
                        "type": "AUDIO_OUTPUT_SLOT",
                        "value": ""
                    })
                    continue

                if any(kw in lower_type for kw in ["loader", "checkpoint", "loraloader", "vaeloader", "model"]):
                    continue

                for param_name, param_val in inputs.items():
                    if isinstance(param_val, list) and len(param_val) == 2 and (isinstance(param_val[0], (str, int)) or str(param_val[0]).isdigit()):
                        continue

                    lower_name = param_name.lower()
                    if any(kw in lower_name for kw in EXCLUDE_WIDGET_KEYWORDS):
                        continue

                    w_type = "STRING"
                    if isinstance(param_val, bool):
                        w_type = "BOOLEAN"
                    elif isinstance(param_val, int):
                        w_type = "INT"
                    elif isinstance(param_val, float):
                        w_type = "FLOAT"

                    widgets.append({
                        "nodeId": node_id,
                        "nodeType": class_type,
                        "name": param_name,
                        "type": w_type,
                        "value": param_val
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

        config_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        config_path = os.path.join(config_dir, ".runninghub_config")

        config = {}
        allowed_keys = {"runninghub_api_key", "runninghub_base_url"}

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        if key in allowed_keys:
                            config[key] = val.strip()
            except Exception:
                pass

        if api_key:
            config["runninghub_api_key"] = api_key
        if base_url:
            config["runninghub_base_url"] = base_url

        if not config:
            return web.json_response({"success": False, "error": "No valid configuration values provided."}, status=400)

        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        with open(config_path, "w", encoding="utf-8") as f:
            for key in sorted(config.keys()):
                f.write(f"{key}={config[key]}\n")

        return web.json_response({"success": True})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.get("/comfypanel/runninghub/get_config")
async def runninghub_get_config(request):
    try:
        config_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        config_path = os.path.join(config_dir, ".runninghub_config")
        api_key = ""
        base_url = "https://www.runninghub.cn"

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        if key.strip() == "runninghub_api_key":
                            api_key = val.strip()
                        elif key.strip() == "runninghub_base_url":
                            base_url = val.strip()
            except Exception:
                pass

        return web.json_response({"success": True, "apiKey": api_key, "baseUrl": base_url})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

@PromptServer.instance.routes.post("/comfypanel/runninghub/upload_workflow")
async def runninghub_upload_workflow(request):
    try:
        post_data = await request.post()
        file_field = post_data.get("file")
        if not file_field:
            return web.json_response({"success": False, "error": "No file uploaded"}, status=400)

        filename = file_field.filename
        if not filename.endswith('.json'):
            return web.json_response({"success": False, "error": "Only JSON files are allowed"}, status=400)

        input_dir = folder_paths.get_input_directory()

        workflows_dir = os.path.join(input_dir, "workflows")
        os.makedirs(workflows_dir, exist_ok=True)
        target_path = os.path.join(workflows_dir, filename)

        file_data = file_field.file.read()
        with open(target_path, 'wb') as f:
            f.write(file_data)

        logging.info(f"[Linker] Uploaded workflow file saved to: {target_path}")
        return web.json_response({"success": True, "filename": filename})
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)