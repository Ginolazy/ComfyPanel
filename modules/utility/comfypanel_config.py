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
import folder_paths

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