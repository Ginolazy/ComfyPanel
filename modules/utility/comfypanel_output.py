"""
Shared helper for downloading remote output files and converting them to
ComfyUI-native types (IMAGE tensor, AUDIO dict, VideoFromFile).
"""

import logging
import os
import numpy as np
import requests
import torch
import torchaudio

from comfy_api.input_impl import VideoFromFile
from PIL import Image

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

    `prefix` is used to build filenames: {prefix}_{idx}{ext}
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    for idx, url in enumerate(urls):
        ext = os.path.splitext(url.split('?')[0])[1].lower() or ".png"
        filename = f"{prefix}_{idx}{ext}"
        filepath = os.path.join(output_dir, filename)
        item = download_and_convert(url, filepath)
        if item is not None:
            results.append(item)
    return results