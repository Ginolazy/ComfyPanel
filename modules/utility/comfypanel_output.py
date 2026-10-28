"""
Shared helper for downloading remote output files and converting them to
ComfyUI-native types (IMAGE tensor, AUDIO dict, VideoFromFile).
"""

import logging
import os
import re
import numpy as np
import requests
import torch
import torchaudio
import folder_paths

from comfy_api.input_impl import VideoFromFile
from PIL import Image
from .comfypanel_config import _is_safe_path

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a'}

def download_and_convert(file_url: str, filepath: str) -> object:
    """
    Download `file_url` to `filepath`, then return the appropriate ComfyUI type:
    - IMAGE exts  → torch.Tensor  [1, H, W, C] float32 in [0,1]
    - AUDIO exts  → {"waveform": Tensor, "sample_rate": int}
    - anything else → VideoFromFile(filepath)

    Returns None on failure.
    """
    try:
        with requests.get(file_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
    except Exception as e:
        logging.error(f"[ComfyPanel] Download failed for {file_url}: {e}")
        return None

    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext in IMAGE_EXTS:
            img = Image.open(filepath)
            img = img.convert("RGBA") if img.mode == "RGBA" else img.convert("RGB")
            arr = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(arr).unsqueeze(0)
        elif ext in AUDIO_EXTS:
            waveform, sample_rate = torchaudio.load(filepath)
            return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}
        else:
            return VideoFromFile(filepath)
    except Exception as e:
        logging.error(f"[ComfyPanel] Conversion failed for {filepath}: {e}")
        return None

def download_outputs(urls: list, output_dir: str, prefix: str) -> list:
    """
    Download a list of output URLs into `output_dir`, convert each, and return
    a list of ComfyUI-native values (skipping None results).

    `prefix` is sanitized and used to build filenames: {safe_prefix}_{idx}{ext}.
    Output paths are strictly confined within ComfyUI output directory.
    """
    safe_output_root = os.path.realpath(folder_paths.get_output_directory())
    real_output_dir = os.path.realpath(output_dir)
    if not _is_safe_path(real_output_dir, safe_output_root):
        real_output_dir = os.path.realpath(os.path.join(safe_output_root, "runninghub_webapp"))

    os.makedirs(real_output_dir, exist_ok=True)
    results = []

    safe_prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", prefix or "output")

    for idx, url in enumerate(urls):
        ext = os.path.splitext(url.split('?')[0])[1].lower() or ".png"
        clean_ext = re.sub(r"[^a-zA-Z0-9.]", "", ext)
        if not clean_ext.startswith('.'):
            clean_ext = f".{clean_ext}"
        filename = f"{safe_prefix}_{idx}{clean_ext}"
        filepath = os.path.realpath(os.path.join(real_output_dir, filename))
        if not _is_safe_path(filepath, real_output_dir):
            continue
        item = download_and_convert(url, filepath)
        if item is not None:
            results.append(item)
    return results