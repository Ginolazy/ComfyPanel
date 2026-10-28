"""
Unified read/write helper for ComfyUI user settings (comfy.settings.json).

Keys managed:
    ComfyPanel.BizyAir.apikey
    ComfyPanel.RunningHubZh.apikey
    ComfyPanel.RunningHubEn.apikey
    ComfyPanel.RunningHub.baseUrl
"""

import json
import logging
import os
import urllib.parse
import folder_paths

def _mask_key(key: str) -> str:
    """Mask sensitive API key to prevent exfiltration."""
    if not key:
        return ""
    if len(key) <= 8:
        return "********"
    return f"{key[:4]}****{key[-4:]}"

def _is_safe_path(target_path: str, base_dir: str) -> bool:
    """Verify target_path is strictly contained inside base_dir using realpath + commonpath."""
    try:
        real_target = os.path.realpath(target_path)
        real_base = os.path.realpath(base_dir)
        return os.path.commonpath([real_target, real_base]) == real_base
    except Exception:
        return False

def is_safe_comfy_path(target_path: str) -> bool:
    """Verify target_path is strictly inside ComfyUI allowed directories (input, output, temp, user)."""
    if not target_path or not isinstance(target_path, str):
        return False
    try:
        allowed_dirs = [
            folder_paths.get_input_directory(),
            folder_paths.get_output_directory(),
            folder_paths.get_temp_directory(),
            folder_paths.get_user_directory(),
        ]
        real_target = os.path.realpath(target_path)
        for d in allowed_dirs:
            if d and _is_safe_path(real_target, d):
                return True
        return False
    except Exception:
        return False

ALLOWED_RUNNINGHUB_HOSTS = {
    "runninghub.cn", "www.runninghub.cn", "api.runninghub.cn",
    "runninghub.ai", "www.runninghub.ai", "api.runninghub.ai"
}

def is_allowed_rh_host(base_url: str) -> bool:
    """Ensure outgoing proxy requests or configured base URLs only target official RunningHub endpoints."""
    try:
        if not base_url or not isinstance(base_url, str):
            return False
        parsed = urllib.parse.urlparse(base_url)
        host = (parsed.hostname or "").lower()
        if not host:

            host = base_url.split("/")[0].split(":")[0].lower()
        if host in ALLOWED_RUNNINGHUB_HOSTS:
            return True
        if host.endswith(".runninghub.cn") or host.endswith(".runninghub.ai"):
            return True
        return False
    except Exception:
        return False

def _get_settings_path() -> str:
    user_dir = folder_paths.get_user_directory()
    return os.path.join(user_dir, "default", "comfy.settings.json")

def read_config() -> dict:
    """Read settings from comfy.settings.json and return as dict."""
    settings_path = _get_settings_path()
    if not os.path.exists(settings_path):
        return {}
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"[ComfyPanel] Failed to read settings from {settings_path}: {e}")
        return {}

def write_config(updates: dict) -> None:
    """Merge `updates` into comfy.settings.json."""
    settings_path = _get_settings_path()
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    config = read_config()
    config.update({k: v for k, v in updates.items() if v is not None})
    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"[ComfyPanel] Failed to write settings to {settings_path}: {e}")

def get_rh_config(provided_base_url: str = None) -> tuple[str, str]:
    """Get RunningHub API key and base URL from comfy.settings.json."""
    cfg = read_config()
    base_url = provided_base_url or cfg.get("ComfyPanel.RunningHub.baseUrl", "https://www.runninghub.cn")
    is_en = "runninghub.ai" in base_url
    api_key_name = "ComfyPanel.RunningHubEn.apikey" if is_en else "ComfyPanel.RunningHubZh.apikey"
    api_key = cfg.get(api_key_name, "")
    return api_key, base_url