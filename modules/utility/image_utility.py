## ComfyUI/custom_nodes/ComfyPanel/py/utility/image_utility.py
import re
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageColor, ImageEnhance, ImageFilter
from typing import Tuple, List, NamedTuple, Any
from .type_utility import handle_error

class CropData(NamedTuple):
    crop_x1: int
    crop_y1: int
    crop_x2: int
    crop_y2: int
    pad_x: int
    pad_y: int
    content_w: int
    content_h: int
    scale_x: float
    scale_y: float
    target_w: int
    target_h: int
    @staticmethod
    def from_values(x1, y1, x2, y2, pad_x=0, pad_y=0, content_w=0, content_h=0,
                    scale_x=1.0, scale_y=1.0, target_w=0, target_h=0):
        return CropData(x1, y1, x2, y2, pad_x, pad_y, content_w, content_h,
                        scale_x, scale_y, target_w, target_h)

def apply_image_filters(
    img: Image.Image,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 1.0,
    blur: float = 0.0,
    gaussian_blur: float = 0.0,
    edge_enhance: bool = False
) -> Image.Image:
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(saturation)
    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
    if blur > 0:
        img = img.filter(ImageFilter.BoxBlur(blur))
    if gaussian_blur > 0:
        img = img.filter(ImageFilter.GaussianBlur(gaussian_blur))
    if edge_enhance:
        img = img.filter(ImageFilter.EDGE_ENHANCE)
    return img

def parse_color(color_str: str) -> Tuple[int, int, int, int]:
    try:
        s = str(color_str).strip().lower()
        if s.startswith("#"): # Hex colors
            hex_str = s[1:]
            if len(hex_str) in (3, 4):
                hex_str = "".join(c*2 for c in hex_str)
            comps = [int(hex_str[i:i+2], 16) for i in range(0, len(hex_str), 2)]
            return tuple(comps + [255]) if len(comps) == 3 else tuple(comps)
        match = re.findall(r"[\d.]+%?", s)
        if match:
            comps = []
            for p in match:
                if "%" in p:
                    comps.append(int(float(p.strip("%")) * 2.55))
                else:
                    comps.append(int(float(p) * (255 if "." in p else 1)))
            return tuple(comps + [255]) if len(comps) == 3 else tuple(comps)
        rgb = ImageColor.getrgb(s)
        return (*rgb, 255)
    except Exception as e:
        raise ValueError(f"[parse_color] Invalid color '{color_str}': {e}")

def pil2tensor(img: Image.Image, add_batch_dim: bool = True) -> torch.Tensor:
    tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0)
    if add_batch_dim:
        tensor = tensor.unsqueeze(0)
    return tensor

def tensor2pil(tensor: torch.Tensor, clamp: bool = True) -> List[Image.Image]:
    arr = tensor.cpu().numpy()
    if clamp:
        arr = np.clip(arr, 0, 1)
    return [Image.fromarray((img * 255).astype(np.uint8)) for img in arr]
    
def validate_mask_dimensions(mask_np: np.ndarray) -> np.ndarray:
    if mask_np.ndim > 2:
        return mask_np[0] if mask_np.ndim == 3 else mask_np[0, 0]
    return mask_np

def calculate_scale_with_mode(
    width: int, height: int, target_size: int,
    scale_mode: str = 'scale up',
    reference_side: str = 'long side',
    return_extra: bool = True
):
    long_side, short_side = max(width, height), min(width, height)
    ref_dim = long_side if reference_side == "long side" else short_side
    should_scale = ((scale_mode == "scale up" and ref_dim < target_size) or
                    (scale_mode == "scale down" and ref_dim > target_size) or
                    scale_mode == "rescale")
    if not should_scale:
        base = (width, height, False)
        return (*base, 1.0, "No scaling") if return_extra else base
    scale_factor = target_size / ref_dim
    new_w = int(round(width * scale_factor))
    new_h = int(round(height * scale_factor))
    info = f"Scale {scale_mode} ({reference_side}): {width}x{height} → {new_w}x{new_h} (×{scale_factor:.6g})"
    base = (new_w, new_h, True)
    return (*base, scale_factor, info) if return_extra else base

def scale_to_match(target: torch.Tensor, source: torch.Tensor, is_mask: bool = False) -> torch.Tensor:
    if source.shape[-2:] == target.shape[-2:]:
        return source
    mode = "nearest" if is_mask else "bicubic"
    align_corners = None if is_mask else False
    if source.dim() == 3:
        source = source.unsqueeze(0)
    elif source.dim() == 4 and source.shape[0] != 1:
        raise ValueError("Source batch size must be 1")
    if target.dim() == 3:
        target = target.unsqueeze(0)
    elif target.dim() != 4 or target.shape[0] != 1:
        raise ValueError("Target must be [1, C, H, W] or [C, H, W]")
    out = F.interpolate(
        source,
        size=(target.shape[2], target.shape[3]),
        mode=mode,
        align_corners=align_corners
    )
    return out.squeeze(0)

def hwc_to_bchw(tensor: torch.Tensor) -> torch.Tensor: # [H,W,C] -> [1,C,H,W]
    return tensor.permute(2, 0, 1).unsqueeze(0)

def bchw_to_hwc(tensor: torch.Tensor) -> torch.Tensor: # [1,C,H,W] -> [H,W,C]
    return tensor.squeeze(0).permute(1, 2, 0)

def hw_to_b1hw(tensor: torch.Tensor) -> torch.Tensor: # [H,W] -> [1,1,H,W]
    return tensor.unsqueeze(0).unsqueeze(0)

def b1hw_to_hw(tensor: torch.Tensor) -> torch.Tensor: # [1,1,H,W] -> [H,W]
    return tensor.squeeze(0).squeeze(0)

def generate_preview_images(input_values: List[Any]) -> List[torch.Tensor]:
    preview_images_list = []
    i = 0
    while i < len(input_values):
        val = input_values[i]
        is_img = isinstance(val, torch.Tensor) and val.ndim == 4 
        is_mask = isinstance(val, torch.Tensor) and val.ndim in (2, 3) 
        if is_img:
            next_val = input_values[i+1] if i + 1 < len(input_values) else None
            next_is_mask = isinstance(next_val, torch.Tensor) and next_val.ndim in (2, 3)
            if next_is_mask and is_empty_mask(next_val):
                next_is_mask = False
            if next_is_mask:
                try:
                    img_tensor = val
                    mask_tensor = next_val
                    if mask_tensor.ndim == 2:
                        mask_tensor = mask_tensor.unsqueeze(0).unsqueeze(-1)
                    elif mask_tensor.ndim == 3:
                        mask_tensor = mask_tensor.unsqueeze(-1)
                    if mask_tensor.shape[-3:-1] != img_tensor.shape[-3:-1]:
                        mask_for_resize = mask_tensor.permute(0, 3, 1, 2)
                        mask_resized = F.interpolate(
                            mask_for_resize, 
                            size=(img_tensor.shape[1], img_tensor.shape[2]), 
                            mode="nearest"
                        )
                        mask_tensor = mask_resized.permute(0, 2, 3, 1)
                    mask_opacity = 0.5
                    red_overlay = torch.zeros_like(img_tensor)
                    red_overlay[:, :, :, 0] = 1.0 # R channel = 1
                    alpha = mask_tensor * mask_opacity
                    if alpha.shape[0] != img_tensor.shape[0]:
                        alpha = alpha.repeat(img_tensor.shape[0], 1, 1, 1)
                    composite = img_tensor * (1 - alpha) + red_overlay * alpha
                    preview_images_list.append(composite)
                except Exception as e:
                    handle_error(e, "Overlay utility error")
                    preview_images_list.append(val)
            else:
                preview_images_list.append(val)
        elif is_mask:
            prev_val = input_values[i-1] if i > 0 else None
            prev_is_img = isinstance(prev_val, torch.Tensor) and prev_val.ndim == 4
            
            if not prev_is_img:
                mask_preview = val
                if mask_preview.ndim == 2:
                    mask_preview = mask_preview.unsqueeze(0) # [B, H, W]
                mask_preview = mask_preview.reshape((-1, 1, mask_preview.shape[-2], mask_preview.shape[-1]))
                mask_preview = mask_preview.movedim(1, -1).expand(-1, -1, -1, 3)
                preview_images_list.append(mask_preview)
        i += 1
    return preview_images_list

def flatten_input_values(input_values: List[Any]) -> List[Any]:
    flat_values = []
    def _flatten(items):
        for item in items:
            if isinstance(item, (list, tuple)):
                _flatten(item)
            else:
                flat_values.append(item)
    _flatten(input_values)
    return flat_values

def generate_text_previews(input_values: List[Any], max_length: int = 500) -> List[str]:
    text_previews = []
    for port_vals in input_values:
        if not isinstance(port_vals, list):
            port_vals = [port_vals]
        for val in port_vals:
            if isinstance(val, str):
                text_preview = val[:max_length] if len(val) > max_length else val
                if len(val) > max_length:
                    text_preview += "..."
                text_previews.append(text_preview)
            elif isinstance(val, bool):
                text_previews.append(f"Boolean: {val}")
            elif isinstance(val, (int, float)):
                text_previews.append(f"Number: {val}")
            elif isinstance(val, list):
                text_previews.append(f"List: {len(val)} items")
    return text_previews

def is_empty_mask(mask_tensor: torch.Tensor) -> bool:
    unique_vals = mask_tensor.unique()
    if len(unique_vals) == 1:
        return unique_vals[0].item() in (0.0, 1.0)
    return False

def normalize_mask_tensor(mask_tensor: torch.Tensor) -> torch.Tensor: # mask [B, H, W, 1]
    if mask_tensor.ndim == 2:
        mask_tensor = mask_tensor.unsqueeze(0).unsqueeze(-1) # [H, W] -> [1, H, W, 1]
    elif mask_tensor.ndim == 3:
        mask_tensor = mask_tensor.unsqueeze(-1) # [B, H, W] -> [B, H, W, 1]
    return mask_tensor

def resize_mask_to_image(mask_tensor: torch.Tensor, img_tensor: torch.Tensor) -> torch.Tensor:
    if mask_tensor.shape[-3:-1] != img_tensor.shape[-3:-1]:
        mask_for_resize = mask_tensor.permute(0, 3, 1, 2)  # [B, 1, H, W]
        mask_resized = F.interpolate(
            mask_for_resize,
            size=(img_tensor.shape[1], img_tensor.shape[2]),
            mode="nearest"
        )
        mask_tensor = mask_resized.permute(0, 2, 3, 1)  # [B, H, W, 1]
    if mask_tensor.shape[0] != img_tensor.shape[0]:
        mask_tensor = mask_tensor.repeat(img_tensor.shape[0], 1, 1, 1)
    return mask_tensor

def create_rgba_from_image_mask(img_tensor: torch.Tensor, mask_tensor: torch.Tensor) -> torch.Tensor:
    mask_tensor = normalize_mask_tensor(mask_tensor)
    mask_tensor = resize_mask_to_image(mask_tensor, img_tensor)
    alpha = 1.0 - mask_tensor # alpha = 1.0 - mask
    if img_tensor.shape[-1] == 1:
        img_tensor = img_tensor.repeat(1, 1, 1, 3)
    elif img_tensor.shape[-1] > 3:
        img_tensor = img_tensor[..., :3]
    img_rgba = torch.cat((img_tensor, alpha), dim=-1)
    return img_rgba

def generate_editable_images(input_values: List[Any]) -> List[torch.Tensor]: # RGBA list
    editable_images_list = []
    i = 0
    while i < len(input_values):
        val = input_values[i]
        is_img = isinstance(val, torch.Tensor) and val.ndim == 4
        is_mask = isinstance(val, torch.Tensor) and val.ndim in (2, 3)
        if is_img:
            next_val = input_values[i+1] if i + 1 < len(input_values) else None
            next_is_mask = isinstance(next_val, torch.Tensor) and next_val.ndim in (2, 3)
            if next_is_mask and is_empty_mask(next_val):
                next_is_mask = False
            if next_is_mask:
                img_rgba = create_rgba_from_image_mask(val, next_val)
                editable_images_list.append(img_rgba)
                i += 1
            else:
                editable_images_list.append(val)
        elif is_mask:
            prev_val = input_values[i-1] if i > 0 else None
            prev_is_img = isinstance(prev_val, torch.Tensor) and prev_val.ndim == 4
            if not prev_is_img:
                mask_preview = val
                if mask_preview.ndim == 2:
                    mask_preview = mask_preview.unsqueeze(0)  # [B, H, W]
                mask_preview = mask_preview.reshape((-1, 1, mask_preview.shape[-2], mask_preview.shape[-1]))
                mask_preview = mask_preview.movedim(1, -1).expand(-1, -1, -1, 3)
                editable_images_list.append(mask_preview)
        i += 1
    return editable_images_list

def save_images_for_preview(save_image_instance, images_list: List[torch.Tensor], 
                            filename_prefix: str = "ComfyPanel_preview",
                            collect_filenames: bool = False) -> Tuple[List[dict], List[Tuple[str, str]]]:
    all_saved_images = []
    saved_filenames = []
    
    for img_tensor in images_list:
        res = save_image_instance.save_images(img_tensor, filename_prefix=filename_prefix)
        if 'ui' in res and 'images' in res['ui']:
            for img_data in res['ui']['images']:
                img_data['url'] = f"{img_data.get('subfolder', '')}/{img_data['filename']}"
                img_data['thumbnail'] = f"/api/view?type={img_data['type']}&filename={img_data['filename']}&subfolder={img_data.get('subfolder', '')}"
                all_saved_images.append(img_data)
                if collect_filenames:
                    saved_filenames.append((img_data.get('subfolder', ''), img_data['filename']))
    return all_saved_images, saved_filenames

def send_preview_event(unique_id_str: str, frontend_data: dict, node_type: str = "preview", 
                       action: str = None, extra_data: dict = None):
    import server
    event_data = {
        "node_id": unique_id_str,
        "node_type": node_type,
        "data": frontend_data
    }
    if action is not None:
        event_data["action"] = action
    if extra_data is not None:
        event_data.update(extra_data)
    server.PromptServer.instance.send_sync("ComfyPanel.node_event", event_data)

def composite_image_with_color(image: torch.Tensor, mask: torch.Tensor, 
                                color: Tuple[int, int, int], opacity: float = 1.0) -> torch.Tensor:
    color_normalized = (color[0] / 255.0, color[1] / 255.0, color[2] / 255.0)
    mask_tensor = normalize_mask_tensor(mask)
    mask_tensor = resize_mask_to_image(mask_tensor, image)
    color_overlay = torch.zeros_like(image)
    color_overlay[:, :, :, 0] = color_normalized[0]  # R
    color_overlay[:, :, :, 1] = color_normalized[1]  # G
    color_overlay[:, :, :, 2] = color_normalized[2]  # B
    alpha = mask_tensor * opacity
    composite = image * (1 - alpha) + color_overlay * alpha
    if composite.shape[-1] > 3:
        composite = composite[..., :3]
    return composite