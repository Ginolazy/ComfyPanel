import shutil
import os
import io
import hashlib
import logging
import folder_paths
import platform
import subprocess
import json
from aiohttp import web
from server import PromptServer
from PIL import Image, ImageOps
from .comfypanel_tunnel import tunnel_manager


# ─── Origin Middleware Patch ────────────────────────────────────────────────────
# ComfyUI's origin_only_middleware compares Host (127.0.0.1) vs Origin hostname.
# UXP webview <img> tags send "Origin: file://localhost", where "localhost" != "127.0.0.1",
# causing a blanket 403 that prevents /comfypanel/thumbnail from ever executing.
# This patch whitelists /comfypanel/ routes so the thumbnail handler can run.
# ────────────────────────────────────────────────────────────────────────────────
def _patch_origin_middleware():
    app = PromptServer.instance.app
    for i, mw in enumerate(app.middlewares):
        name = getattr(mw, '__name__', '')
        if 'origin' in name.lower():
            original = mw

            @web.middleware
            async def patched(request, handler, _orig=original):
                normalized = request.path.lstrip('/')
                if normalized.startswith('comfypanel/') or normalized == 'comfypanel':
                    if request.method == "OPTIONS":
                        resp = web.Response()
                    else:
                        resp = await handler(request)
                    resp.headers['Access-Control-Allow-Origin'] = '*'
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
    # No fallback: raise error if no UXP directory containing manifest.json is found
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

        if not src_path or not os.path.isfile(src_path):
            return web.json_response({"success": False, "error": f"Source file not found: {src_path}"}, status=400)

        input_dir = folder_paths.get_input_directory()
        
        abs_src = os.path.abspath(src_path)
        abs_input = os.path.abspath(input_dir)
        
        # [v2.12] True Origin-Level Zero Copy: If file is already anywhere inside the input directory, DO NOT copy or rename.
        # Just return its relative path from the input directory.
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
    ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

    output_dir = folder_paths.get_output_directory()
    files = []

    # Scan root output dir AND all subdirectories (audio/, video/, comfypanel_results/, etc.)
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
                        # Return relative to output folder for ComfyUI's /view API compatibility
                        rel_name = os.path.relpath(entry.path, output_dir).replace("\\", "/")
                        files.append({
                            "name": rel_name,
                            "nativePath": entry.path,
                            "mtime": entry.stat().st_mtime,
                        })
        
        # Sort all aggregated files by modified time descending
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
            # Absolute path mode — whitelist check
            file_path = os.path.abspath(path_param)
            allowed_roots = [
                os.path.abspath(output_dir),
                os.path.abspath(folder_paths.get_temp_directory()),
            ]
            is_allowed = any(file_path.startswith(r) for r in allowed_roots) or \
                         ("Adobe" in file_path and "UXP" in file_path and "PluginsStorage" in file_path)
            if not is_allowed:
                return web.Response(status=403, text="Access denied")
        else:
            if not filename:
                return web.Response(status=400, text="No filename")
            file_path = os.path.abspath(os.path.join(output_dir, subfolder, filename))
            if not file_path.startswith(os.path.abspath(output_dir)):
                return web.Response(status=403, text="Access denied")

        if not os.path.isfile(file_path):
            return web.Response(status=404, text="File not found")

        # [CACHE] Check thumbnail cache in ComfyUI temp
        mtime = os.path.getmtime(file_path)
        # Use a more searchable cache key: {path_hash}_{params_hash}.webp
        path_hash = hashlib.md5(file_path.encode()).hexdigest()
        params_hash = hashlib.md5(f"{mtime}_{size}".encode()).hexdigest()
        
        temp_dir = folder_paths.get_temp_directory()
        cache_dir = os.path.join(temp_dir, "comfypanel_thumbs")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        
        cache_path = os.path.join(cache_dir, f"{path_hash}_{params_hash}.webp")

        if os.path.exists(cache_path):
            return web.FileResponse(cache_path)

        # [GENERATE] Use Pillow to resize
        try:
            img = Image.open(file_path)
        except Exception:
            # Fallback for non-image files or corrupted images
            return web.Response(status=415, text="Unsupported file type")

        img = ImageOps.exif_transpose(img)
        img.thumbnail((size, size))
        
        output = io.BytesIO()
        img.save(output, format="WEBP", quality=85)
        img.close()
        
        webp_data = output.getvalue()
        
        # Save to cache
        try:
            with open(cache_path, "wb") as f:
                f.write(webp_data)
        except Exception:
            pass # Ignore cache write errors

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

        # Security: Ensure the file is within the output directory
        if not file_path.startswith(os.path.abspath(output_dir)):
            return web.json_response({"success": False, "error": "Access denied"}, status=403)

        if os.path.isfile(file_path):
            # [CLEANUP] Remove associated thumbnails first
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
            
            # Clean up the parent directory if it's empty and it's our comfypanel_results dir
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
        
        # Only allow serving from specific safe directories
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
        # Get plugin root path accurately
        plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
        config_path = os.path.abspath(os.path.join(plugin_root, "custom", "user_config.js"))
        
        if not os.path.exists(config_path):
            return web.json_response({"success": False, "error": f"custom/user_config.js not found at {config_path}"}, status=404)
        
        system = platform.system()
        if system == "Darwin":
            subprocess.call(["open", config_path])
        elif system == "Windows":
            os.startfile(config_path)
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
            # Return empty scaffold if file does not yet exist
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
        
        # [ARCH] Support reading user workflows (if any custom directory mapping is needed)
        # Natively ComfyUI has /userdata, but if the webview explicitly calls /comfypanel/userdata, we serve it from a safe user directory.
        target_dir = folder_paths.get_user_directory() if hasattr(folder_paths, 'get_user_directory') else os.path.join(folder_paths.base_path, "user", "default")
        target_dir = os.path.join(target_dir, directory)

        if not os.path.exists(target_dir):
            # Fallback to ComfyPanel local folder if user dir doesn't exist just in case
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
        
        # Try user directory first
        user_dir = folder_paths.get_user_directory() if hasattr(folder_paths, 'get_user_directory') else os.path.join(folder_paths.base_path, "user", "default")
        full_path = os.path.abspath(os.path.join(user_dir, path))
        
        if not os.path.exists(full_path):
            # Fallback to plugin root
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
        # Saving always goes to the root plugin directory for persistence across updates
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
                base_name = filename[:-5]  # Strip .json
                try:
                    cover_urls = []
                    # Prioritize SVG -> -cover.webp -> raw .webp
                    svg_path = os.path.join(target_dir, f"{base_name}-cover.svg")
                    webp_cover_path = os.path.join(target_dir, f"{base_name}-cover.webp")
                    webp_path = os.path.join(target_dir, f"{base_name}.webp")
                    
                    # Convert backslashes to forward slashes to prevent CSS escape issues on Windows (e.g. \t, \U)
                    def to_file_uri(path):
                        clean_path = path.replace("\\", "/")
                        # Ensure proper file:/// format for Windows (C:/...) and Mac (/Users/...)
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
                        "workflow": None, # [ARCH] Switched to lazy loading, will fetch via API when clicked
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
