## ComfyUI/custom_nodes/ComfyPanel/py/image.py
import torch
import torch.nn.functional as F
import cv2
import numpy as np
import comfy.utils
import os
import folder_paths
import kornia
from kornia.feature import LoFTR
from kornia.geometry.transform import warp_perspective   
from PIL import Image
from typing import Tuple
from .utility.type_utility import (any_type, handle_error)
from .utility.image_utility import (parse_color, pil2tensor, tensor2pil, validate_mask_dimensions, apply_image_filters,
    calculate_scale_with_mode, scale_to_match, CropData, hwc_to_bchw, bchw_to_hwc, hw_to_b1hw, b1hw_to_hw)
 

## ---------------------- ComfyPanel / Image or Mask ---------------------- ##
# BlendByMask
class BlendByMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "background_image": ("IMAGE",),
                "background_mask": ("MASK",),
                "blend_image": ("IMAGE",),
                "blend_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "mask_blur": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 50.0, "step": 0.5}),
                "maximize_fill": ("BOOLEAN", {"default": True}),
                "clip_by_mask": ("BOOLEAN", {"default": True}),
                "crop_by_mask": ("BOOLEAN", {"default": False}),
                "scale_by_mask": ("BOOLEAN", {"default": True}),
                "align_by_mask": ("BOOLEAN", {"default": False}),
            },
            "optional": {"blend_mask": ("MASK",),},
        }
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "blend"
    CATEGORY = "ComfyPanel/Image & Mask"
    def blend(self, background_image, background_mask, blend_image, blend_strength, **kw):
        bg_img = (background_image[0].cpu().numpy() * 255).astype(np.uint8)
        bg_mask = (background_mask[0].cpu().numpy() * 255).astype(np.uint8)
        blend_img_data = (blend_image[0].cpu().numpy() * 255).astype(np.uint8)
        
        # Check if blend_image has alpha channel (RGBA)
        if blend_img_data.shape[2] == 4:
            src_blend = blend_img_data[:, :, :3]  # Extract RGB channels
            blend_msk = blend_img_data[:, :, 3].astype(np.float32) / 255.0  # Extract alpha channel as mask
        else:
            src_blend = blend_img_data
            blend_msk = np.ones((src_blend.shape[0], src_blend.shape[1]), np.float32)
        
        if kw["mask_blur"] > 0:
            k = int(kw["mask_blur"] * 2 + 1)
            bg_mask = cv2.GaussianBlur(bg_mask, (k, k), kw["mask_blur"])
        bg_mask_binary = cv2.threshold(bg_mask, 127, 255, cv2.THRESH_BINARY)[1]
        contours, _ = cv2.findContours(bg_mask_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return (background_image, background_mask)
        if kw["align_by_mask"]:
            bx, by, bw, bh = cv2.boundingRect(np.concatenate(contours))
            center = (bx + bw // 2, by + bh // 2)
        else:
            center = (bg_img.shape[1] // 2, bg_img.shape[0] // 2)
            bx, by = 0, 0
            bw, bh = bg_img.shape[1], bg_img.shape[0]
        
        # Override blend_msk if an explicit blend_mask is provided
        if kw.get("blend_mask") is not None:
            blend_msk = kw["blend_mask"][0].cpu().numpy()
            blend_msk = np.clip(blend_msk, 0.0, 1.0)
        blend_img = src_blend
        if kw["crop_by_mask"] and kw.get("blend_mask") is not None:
            b_mask_bin = (blend_msk * 255).astype(np.uint8)
            b_contours, _ = cv2.findContours(b_mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if b_contours:
                bx2, by2, bw2, bh2 = cv2.boundingRect(np.concatenate(b_contours))
                blend_img = blend_img[by2:by2+bh2, bx2:bx2+bw2]
                blend_msk = blend_msk[by2:by2+bh2, bx2:bx2+bw2]
        blend_h, blend_w = blend_img.shape[:2]
        if kw["scale_by_mask"]:
            scale = max(bw / blend_w, bh / blend_h) if kw["maximize_fill"] else min(bw / blend_w, bh / blend_h)
        else:
            scale = 1.0
        new_w = max(1, int(round(blend_w * scale)))
        new_h = max(1, int(round(blend_h * scale)))
        resized_blend = cv2.resize(blend_img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
        resized_mask = cv2.resize(blend_msk, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        resized_mask = np.clip(resized_mask, 0.0, 1.0)
        offset_x = int(center[0] - new_w // 2)
        offset_y = int(center[1] - new_h // 2)
        src_x = max(0, -offset_x)
        src_y = max(0, -offset_y)
        dst_x = max(0, offset_x)
        dst_y = max(0, offset_y)
        avail_w = min(new_w - src_x, bg_img.shape[1] - dst_x)
        avail_h = min(new_h - src_y, bg_img.shape[0] - dst_y)
        if avail_w <= 0 or avail_h <= 0:
            return (background_image, background_mask)
        src_slice = (slice(src_y, src_y + avail_h), slice(src_x, src_x + avail_w))
        dst_slice = (slice(dst_y, dst_y + avail_h), slice(dst_x, dst_x + avail_w))
        blend_source = resized_blend[src_slice[0], src_slice[1]]
        blend_mask_region = resized_mask[src_slice[0], src_slice[1]]
        bg_mask_region = bg_mask[dst_slice[0], dst_slice[1]].astype(np.float32) / 255.0
        blend_alpha = blend_mask_region * blend_strength
        effective_alpha = blend_alpha * bg_mask_region if kw["clip_by_mask"] else blend_alpha
        dst_region = bg_img[dst_slice[0], dst_slice[1]].astype(np.float32)
        blended_region = dst_region * (1.0 - effective_alpha[..., None]) + blend_source.astype(np.float32) * effective_alpha[..., None]
        blended_region = np.clip(blended_region, 0, 255).astype(np.uint8)
        final_img = bg_img.copy()
        final_img[dst_slice[0], dst_slice[1]] = blended_region
        mask_applied = (effective_alpha > 1e-3).astype(np.uint8) * 255
        final_mask = np.zeros_like(bg_mask)
        final_mask[dst_slice[0], dst_slice[1]] = mask_applied
        return (
            torch.from_numpy(final_img.astype(np.float32) / 255.0).unsqueeze(0),
            torch.from_numpy(final_mask.astype(np.float32) / 255.0).unsqueeze(0)
        )
        
# Image Batch To Image List
class ImageBatchToImageList:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"image": ("IMAGE",), }}
    RETURN_TYPES = ("IMAGE",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "doit"
    CATEGORY = "ComfyPanel/Image or Mask"
    def doit(self, image):
        images = [image[i:i + 1, ...] for i in range(image.shape[0])]
        return (images, )

# = ImageBlank
class ImageBlank:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "color": ("STRING", {"default": "white"}),
                "width": ("INT", {"default": 512, "min": 1, "max": 8192}),
                "height": ("INT", {"default": 512, "min": 1, "max": 8192}),
            },
            "optional": {"image": ("IMAGE",)},
        }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "create"
    CATEGORY = "ComfyPanel/Image or Mask"
    @classmethod
    def IS_CHANGED(cls, **kwargs): return float("NaN")
    def create(self, color, width, height, image=None):
        if image is not None:
            height, width = image.shape[1:3]
        try:
            r, g, b, _ = parse_color(color)
            return (pil2tensor(Image.new("RGB", (width, height), (r, g, b))),)
        except Exception as e:
            handle_error(e, "Blank image creation failed")

# Image List To Image Batch
class ImageListToImageBatch:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"images": ("IMAGE", ),}}
    INPUT_IS_LIST = True
    RETURN_TYPES = ("IMAGE", )
    FUNCTION = "doit"
    CATEGORY = "ComfyPanel/Image or Mask"
    def doit(self, images):
        if len(images) <= 1:
            return (images[0],)
        else:
            image1 = images[0]
            for image2 in images[1:]:
                if image1.shape[1:] != image2.shape[1:]:
                    image2 = comfy.utils.common_upscale(image2.movedim(-1, 1), image1.shape[2], image1.shape[1], "lanczos", "center").movedim(1, -1)
                image1 = torch.cat((image1, image2), dim=0)
            return (image1,)

# = ImageFilterAdjustments
class ImageFilterAdjustments:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "brightness": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "sharpness": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "blur": ("INT", {"default": 0, "min": 0, "max": 10}),
                "gaussian_blur": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10.0, "step": 0.01}),
                "edge_enhance": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "detail_enhance": ("BOOLEAN", {"default": False}),
            }
        }
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "apply"
    CATEGORY = "ComfyPanel/Image or Mask"
    def apply(self, image, **kwargs):
        try:
            out = []
            for t in image:
                pil = tensor2pil(t)[0]
                pil = apply_image_filters(pil, **kwargs)
                if kwargs.get("detail_enhance"):
                    pil = pil.filter(ImageFilter.DETAIL)
                out.append(pil2tensor(pil))
            return (torch.cat(out),)
        except Exception as e:
            handle_error(e, "Filter adjustment failed")

# = ImageRemoveAlpha
class ImageRemoveAlpha:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "fill_background": ("BOOLEAN", {"default": True}),
                "background_color": ("STRING", {"default": "#FFFFFF"}),
            },
            "optional": {"mask": ("MASK",)},
        }
    RETURN_TYPES = ("IMAGE", "MASK")
    FUNCTION = "remove"
    CATEGORY = "ComfyPanel/Image or Mask"
    def remove(self, image, fill_background=True, background_color="#FFFFFF", mask=None):
        try:
            img = image.cpu().numpy()
            rgb = img[..., :3]
            if mask is not None:
                alpha = validate_mask_dimensions(mask.cpu().numpy())
                alpha = np.expand_dims(alpha, -1)
            elif img.shape[-1] == 4:
                alpha = img[..., 3:4]
            else:
                alpha = np.ones((*rgb.shape[:-1], 1), np.float32)

            if not fill_background:
                out = rgb
            else:
                bg = np.array(parse_color(background_color)[:3]) / 255.0
                out = rgb * alpha + bg * (1 - alpha)
            out_tensor = torch.from_numpy(out).clamp(0, 1).to(image.device)
            mask_tensor = torch.from_numpy(alpha.squeeze(-1)).clamp(0, 1).to(image.device)
            return (out_tensor, mask_tensor)
        except Exception as e:
            handle_error(e, "Alpha removal failed")

# Image Swap
class ImageSwap:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_a": ("IMAGE",),
                "image_b": ("IMAGE",),
                "swap": ("BOOLEAN", {"default": False}),
            },
        }
    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("output_image_a", "output_image_b")
    FUNCTION = "swap"
    CATEGORY = "ComfyPanel/Image or Mask"
    def swap(self, image_a, image_b, swap):
        if swap:
            return image_b, image_a
        else:
            return image_a, image_b

# MakeBatch (image or mask)
class MakeBatch:
    @classmethod
    def INPUT_TYPES(cls):
        return {}
    RETURN_TYPES = (any_type,)
    FUNCTION = "doit"
    CATEGORY = "ComfyPanel/Image or Mask"
    def doit(self, **kwargs):
        first_key = next(iter(kwargs))
        first_item = kwargs[first_key]
        dtype = first_item.dtype  # torch.float32 / torch.uint8
        is_mask = (dtype == torch.uint8 or first_item.max() <= 1.0)
        base = first_item
        for k, v in list(kwargs.items())[1:]:
            if v.shape[1:] != base.shape[1:]:
                v = comfy.utils.common_upscale(
                    v.movedim(-1, 1) if v.ndim == 4 else v.unsqueeze(1),
                    base.shape[2], base.shape[1], "lanczos", "center"
                )
                if v.ndim == 4:
                    v = v.movedim(1, -1)
                elif v.ndim == 3:
                    v = v.squeeze(1)
            base = torch.cat((base, v), dim=0)
        return (base,)

# ScaleAny (image or mask)
class ScaleAny:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input": (any_type,),
                "target_size": ("INT", {"default": 512, "min": 1, "max": 4096, "step": 1}),
                "scale_mode": (["scale up", "scale down", "rescale"], {"default": "scale up"}),
                "reference_side": (["long side", "short side"], {"default": "long side"}),
            }
        }
    RETURN_TYPES = (any_type,)
    RETURN_NAMES = ("*",)
    FUNCTION = "scale_any"
    CATEGORY = "ComfyPanel/Image or Mask"
    def scale_any(self, input, target_size, scale_mode, reference_side):
        is_image = (input.ndim == 4)  # [B,H,W,C]
        is_mask = (input.ndim == 3)   # [B,H,W]

        if not (is_image or is_mask):
            raise ValueError(f"Unsupported input shape: {input.shape}")

        if is_image:
            batch, height, width, channels = input.shape
        else:
            batch, height, width = input.shape

        new_width, new_height, should_scale, _, _ = calculate_scale_with_mode(
            width, height, target_size, scale_mode, reference_side
        )

        if not should_scale or (new_width == width and new_height == height):
            return (input,)

        if is_mask:
            scaled = F.interpolate(
                input.unsqueeze(1), size=(new_height, new_width), mode="nearest"
            ).squeeze(1)
        else:
            method = "lanczos" if (new_width > width or new_height > height) else "area"
            input_nchw = input.permute(0, 3, 1, 2)
            scaled = comfy.utils.common_upscale(
                input_nchw, new_width, new_height, method, "disabled"
            ).permute(0, 2, 3, 1)

        return (scaled,)

# SwitchMaskAuto
class SwitchMaskAuto:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "optional": {
                "mask_a": ("MASK",),
                "mask_b": ("MASK",),
            },
        }

    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    FUNCTION = "switch_mask"
    CATEGORY = "ComfyPanel/Image or Mask"
    
    def is_mask_edited(self, mask: torch.Tensor) -> bool:
        if mask is None:
            return False
        if mask.ndim == 3:
            mask = mask[0]
        unique_values = torch.unique(mask)
        return len(unique_values) > 1

    def switch_mask(self, mask_a=None, mask_b=None):
        if mask_a is None:
            return (mask_b,)
        if mask_b is None:
            return (mask_a,)
        if self.is_mask_edited(mask_b) and not self.is_mask_edited(mask_a):
            return (mask_b,)
        return (mask_a,)

## ---------------------- ComfyPanel / Image and Mask ---------------------- ##
# ImageMask_Constrain
class ImageMask_Constrain:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "max_width": ("INT", {"default": 1024, "min": 1, "max": 4096, "step": 1}),
                "max_height": ("INT", {"default": 1024, "min": 1, "max": 4096, "step": 1}),
                "min_width": ("INT", {"default": 256, "min": 1, "max": 4096, "step": 1}),
                "min_height": ("INT", {"default": 256, "min": 1, "max": 4096, "step": 1}),
                "crop": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
            }
        }
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("constrained_image", "constrained_mask")
    FUNCTION = "constrain_image"
    CATEGORY = "ComfyPanel/Image & Mask"
    def constrain_image(self, image, max_width, max_height, min_width, min_height, crop, mask=None):
        image_np = image[0].numpy()  # Take the first image in the batch
        image_np = (image_np * 255).astype(np.uint8)  # Convert to 0-255 range
        pil_image = Image.fromarray(image_np)
        original_width, original_height = pil_image.size
        target_width = original_width
        target_height = original_height
        if original_width > max_width or original_height > max_height:
            scale = min(max_width / original_width, max_height / original_height)
            target_width = int(original_width * scale)
            target_height = int(original_height * scale)
        if target_width < min_width or target_height < min_height:
            scale = max(min_width / target_width, min_height / target_height)
            target_width = int(target_width * scale)
            target_height = int(target_height * scale)
        pil_image = pil_image.resize((target_width, target_height), Image.BICUBIC)
        if crop:
            left = (target_width - min_width) // 2
            top = (target_height - min_height) // 2
            right = left + min_width
            bottom = top + min_height
            pil_image = pil_image.crop((left, top, right, bottom))
        image_np = np.array(pil_image).astype(np.float32) / 255.0
        image_tensor = torch.from_numpy(image_np)[None,]
        if mask is not None:
            mask_np = mask[0].numpy()
            pil_mask = Image.fromarray(mask_np)
            pil_mask = pil_mask.resize((target_width, target_height), Image.NEAREST)
            if crop:
                pil_mask = pil_mask.crop((left, top, right, bottom))
            mask_np = np.array(pil_mask).astype(np.float32)
            mask_tensor = torch.from_numpy(mask_np)[None,]
        else:
            mask_tensor = torch.zeros((1, target_height, target_width), dtype=torch.float32)
        return (image_tensor, mask_tensor)

# Image & Mask Boolean Swap
class ImageMask_Swap:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image_a": ("IMAGE",),
                 "mask_a": ("MASK",),
                "image_b": ("IMAGE",),
                 "mask_b": ("MASK",),
                "swap": ("BOOLEAN", {"default": False}),
            },
        }
    RETURN_TYPES = ("IMAGE", "MASK", "IMAGE", "MASK")
    RETURN_NAMES = ("output_image_a", "output_mask_a", "output_image_b", "output_mask_b")
    FUNCTION = "swap"
    CATEGORY = "ComfyPanel/Image & Mask"
    def swap(self, image_a, mask_a, image_b, mask_b, swap):
        if swap:
            return image_b, mask_b, image_a, mask_a
        else:
            return image_a, mask_a, image_b, mask_b

# Image & Mask Boolean Switch
class ImageMask_Switch:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "switch": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "image_true": ("IMAGE", {"lazy": True}),
                "mask_true": ("MASK", {"lazy": True}),
                "image_false": ("IMAGE", {"lazy": True}),
                "mask_false": ("MASK", {"lazy": True}),
            }
        }
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "switch"
    CATEGORY = "ComfyPanel/Image & Mask"
    def check_lazy_status(self, switch, image_true=None, mask_true=None, image_false=None, mask_false=None):
        needed = []
        if switch:
            if image_true is None:
                needed.append("image_true")
            if mask_true is None:
                needed.append("mask_true")
        else:
            if image_false is None:
                needed.append("image_false")
            if mask_false is None:
                needed.append("mask_false")
        return needed
    def switch(self, switch, image_true=None, mask_true=None, image_false=None, mask_false=None):
        if switch:
            output_image = image_true
            output_mask = mask_true
        else:
            output_image = image_false
            output_mask = mask_false
        return (output_image, output_mask)

# Image & Mask Auto Switch
class ImageMask_SwitchAuto:
    @classmethod
    def INPUT_TYPES(cls):
        return {# image_*,mask_* Input groups are added dynamically by JS
        }
    RETURN_TYPES = ("IMAGE", "MASK",)
    FUNCTION = "switch"
    CATEGORY = "ComfyPanel/Image & Mask"

    def switch(self, **kwargs):
        images = {}
        masks = {}
        for key, value in kwargs.items():
            if key.startswith("image_") and value is not None:
                index = int(key.split("_")[1])
                images[index] = value
            elif key.startswith("mask_") and value is not None:
                index = int(key.split("_")[1])
                masks[index] = value
        if not images:
            return (None, None)
        for i in range(1, max(images.keys()) + 1):
            if i in images:
                selected_image = images.get(i)
                selected_mask = masks.get(i)
                return (selected_image, selected_mask)
        min_index = min(images.keys())
        return (images[min_index], masks.get(min_index))

#Image and Mask Transform
class ImageMask_Transform:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE", {"lazy": True}),
                "mask": ("MASK", {"lazy": True}),
                "flip_h": ("BOOLEAN", {"default": False}),
                "flip_v": ("BOOLEAN", {"default": False}),
                "rotate": ("INT", {"default": 0, "min": 0, "max": 3}),
            }
        }
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "transform"
    CATEGORY = "ComfyPanel/Image & Mask"
    def check_lazy_status(self, image=None, mask=None, flip_h=False, flip_v=False, rotate=0):
        needed = []
        if image is None:
            needed.append("image")
        if mask is None:
            needed.append("mask")
        return needed
    def transform(self, image, mask, flip_h, flip_v, rotate):
        if flip_h:
            image = torch.flip(image, [3])
            mask = torch.flip(mask, [2])
        if flip_v:
            image = torch.flip(image, [2])
            mask = torch.flip(mask, [1])
        if rotate > 0:
            image = torch.rot90(image, k=rotate, dims=[2, 3])
            mask = torch.rot90(mask, k=rotate, dims=[1, 2])
        return (image, mask)

## ---------------------- ComfyPanel / Process & Restore ---------------------- ##
#CropByMask
class CropByMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "apply_mask": ("BOOLEAN", {"default": False}),
                "target_ratio": ("BOOLEAN", {"default": False}),
                "allow_overflow": ("BOOLEAN", {"default": False}),
                "fill_color": ("STRING", {"default": "#000000"}),
                "target_width": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 8}),
                "target_height": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 8}),
                "padding": ("INT", {"default": 20, "min": 0, "max": 512, "step": 1}),
                "mask_grow": ("INT", {"default": 0, "min": -100, "max": 100, "step": 1}),
                "mask_blur": ("INT", {"default": 4, "min": 0, "max": 64, "step": 1}),
            }
        }
    RETURN_TYPES = ("IMAGE", "MASK", "CROP_DATA")
    RETURN_NAMES = ("cropped_image", "cropped_mask", "crop_data")
    FUNCTION = "crop"
    CATEGORY = "ComfyPanel/Process & Restore"
    @staticmethod
    def _apply_mask_effects(mask: torch.Tensor, grow: int, blur: int, device: torch.device) -> torch.Tensor:
        if grow == 0 and blur == 0:
            return mask
        if grow != 0:
            k = abs(grow)
            if grow > 0:
                mask = F.max_pool2d(mask.unsqueeze(1), kernel_size=k*2+1, stride=1, padding=k)
            else:
                mask = -F.max_pool2d(-mask.unsqueeze(1), kernel_size=k*2+1, stride=1, padding=k)
            mask = mask.squeeze(1)
        if blur > 0:
            weight = torch.tensor([[[[1, 2, 1], [2, 4, 2], [1, 2, 1]]]], dtype=torch.float32, device=device) / 16.0
            for _ in range(blur):
                mask = F.conv2d(mask.unsqueeze(1), weight, padding=1).squeeze(1)
        return mask.clamp(0, 1)
    def crop(self, image, mask, target_ratio, allow_overflow,
             target_width, target_height, padding, mask_grow, mask_blur, fill_color, apply_mask):
        try:
            device = image.device
            batch_size = image.shape[0]
            empty_input_mask = False
            if mask is None or mask.shape[0] == 0:
                empty_input_mask = True
                mask = torch.ones(batch_size, image.shape[1], image.shape[2], dtype=torch.float32, device=device)
            else:
                mask = mask.to(device)
                if mask.max() < 1e-5:
                    empty_input_mask = True
                    mask = torch.ones(batch_size, image.shape[1], image.shape[2], dtype=torch.float32, device=device)
                else:
                    mask = (mask > 0.5).float()
            mask = self._apply_mask_effects(mask, mask_grow, mask_blur, device)
            fill_rgba = parse_color(fill_color)
            fill_rgb = [c / 255.0 for c in fill_rgba[:3]]
            cropped_images, cropped_masks, crop_infos = [], [], []
            for i in range(batch_size):
                img = image[i]
                if img.shape[2] >= 4:
                    img = img[:, :, :3]
                msk = mask[i].squeeze()
                y_idx, x_idx = torch.where(msk > 0.5)
                if len(y_idx) == 0:
                    canvas = torch.tensor(fill_rgb, device=device, dtype=img.dtype).view(1, 1, 3).expand(target_height, target_width, 3).clone()
                    final_mask = torch.ones(target_height, target_width, device=device)
                    cropped_images.append(canvas)
                    cropped_masks.append(final_mask)
                    crop_infos.append(CropData(0, 0, img.shape[1], img.shape[0], 0, 0, img.shape[1], img.shape[0], 1.0, 1.0, img.shape[1], img.shape[0]))
                    continue
                x_min, x_max = int(x_idx.min()), int(x_idx.max())
                y_min, y_max = int(y_idx.min()), int(y_idx.max())
                crop_x1 = max(0, x_min - padding)
                crop_y1 = max(0, y_min - padding)
                crop_x2 = min(img.shape[1], x_max + padding + 1)
                crop_y2 = min(img.shape[0], y_max + padding + 1)
                crop_w = crop_x2 - crop_x1
                crop_h = crop_y2 - crop_y1
                if not target_ratio:
                    cropped = img[crop_y1:crop_y2, crop_x1:crop_x2, :]
                    cropped_m = msk[crop_y1:crop_y2, crop_x1:crop_x2]
                    if apply_mask:
                        cropped = torch.cat([cropped, cropped_m.unsqueeze(-1)], dim=-1)
                    cropped_images.append(cropped)
                    cropped_masks.append(cropped_m)
                    crop_infos.append(CropData(crop_x1, crop_y1, crop_x2, crop_y2, 0, 0, crop_w, crop_h, 1.0, 1.0, crop_w, crop_h))
                    continue
                target_ratio_val = target_width / target_height
                mask_ratio = crop_w / crop_h if crop_h > 0 else 1.0
                if allow_overflow:
                    if mask_ratio > target_ratio_val:
                        ideal_crop_w = crop_w
                        ideal_crop_h = int(crop_w / target_ratio_val)
                    else:
                        ideal_crop_h = crop_h
                        ideal_crop_w = int(crop_h * target_ratio_val)
                    mask_center_x = (crop_x1 + crop_x2) / 2
                    mask_center_y = (crop_y1 + crop_y2) / 2
                    ideal_x1 = mask_center_x - ideal_crop_w / 2
                    ideal_y1 = mask_center_y - ideal_crop_h / 2
                    ideal_x2 = ideal_x1 + ideal_crop_w
                    ideal_y2 = ideal_y1 + ideal_crop_h
                    actual_x1 = max(0, int(ideal_x1))
                    actual_y1 = max(0, int(ideal_y1))
                    actual_x2 = min(img.shape[1], int(ideal_x2))
                    actual_y2 = min(img.shape[0], int(ideal_y2))
                    scale_to_target_x = target_width / ideal_crop_w
                    scale_to_target_y = target_height / ideal_crop_h
                    canvas_x1 = int((actual_x1 - ideal_x1) * scale_to_target_x)
                    canvas_y1 = int((actual_y1 - ideal_y1) * scale_to_target_y)
                    canvas_x2 = int((actual_x2 - ideal_x1) * scale_to_target_x)
                    canvas_y2 = int((actual_y2 - ideal_y1) * scale_to_target_y)
                    canvas = torch.tensor(fill_rgb, device=device, dtype=img.dtype).view(1, 1, 3).expand(target_height, target_width, 3).clone()
                    final_mask = torch.zeros(target_height, target_width, dtype=msk.dtype, device=device)
                    if actual_x2 > actual_x1 and actual_y2 > actual_y1:
                        crop_region = img[actual_y1:actual_y2, actual_x1:actual_x2, :]
                        target_h = canvas_y2 - canvas_y1
                        target_w = canvas_x2 - canvas_x1
                        if target_h > 0 and target_w > 0:
                            target_img = torch.zeros(1, 3, target_h, target_w, device=device)
                            source_img = hwc_to_bchw(crop_region)
                            scaled_region = bchw_to_hwc(scale_to_match(target_img, source_img, is_mask=False))
                            canvas[canvas_y1:canvas_y2, canvas_x1:canvas_x2, :] = scaled_region
                    if actual_x2 > actual_x1 and actual_y2 > actual_y1:
                        mask_region = msk[actual_y1:actual_y2, actual_x1:actual_x2]
                        target_h = canvas_y2 - canvas_y1
                        target_w = canvas_x2 - canvas_x1
                        if target_h > 0 and target_w > 0:
                            target_msk = torch.zeros(1, 1, target_h, target_w, device=device)
                            source_msk = hw_to_b1hw(mask_region)
                            scaled_mask_region = b1hw_to_hw(scale_to_match(target_msk, source_msk, is_mask=True))
                            final_mask[canvas_y1:canvas_y2, canvas_x1:canvas_x2] = scaled_mask_region
                    
                    crop_data = CropData(
                        int(ideal_x1), int(ideal_y1), int(ideal_x2), int(ideal_y2),
                        canvas_x1, canvas_y1, canvas_x2 - canvas_x1, canvas_y2 - canvas_y1,
                        scale_to_target_x, scale_to_target_y,
                        target_width, target_height
                    )
                else:
                    current_w = crop_x2 - crop_x1
                    current_h = crop_y2 - crop_y1
                    current_ratio = current_w / current_h if current_h > 0 else 1.0
                    if current_ratio > target_ratio_val:
                        needed_h = int(current_w / target_ratio_val)
                        expand_h = needed_h - current_h
                        expand_top = min(crop_y1, expand_h // 2)
                        expand_bottom = min(img.shape[0] - crop_y2, expand_h - expand_top)
                        crop_y1 -= expand_top
                        crop_y2 += expand_bottom
                    else:
                        needed_w = int(current_h * target_ratio_val)
                        expand_w = needed_w - current_w
                        expand_left = min(crop_x1, expand_w // 2)
                        expand_right = min(img.shape[1] - crop_x2, expand_w - expand_left)
                        crop_x1 -= expand_left
                        crop_x2 += expand_right
                    crop_w = crop_x2 - crop_x1
                    crop_h = crop_y2 - crop_y1
                    mask_ratio = crop_w / crop_h if crop_h > 0 else 1.0
                    if mask_ratio > target_ratio_val:
                        new_w, new_h = target_width, max(1, int(target_width / mask_ratio))
                    else:
                        new_h, new_w = target_height, max(1, int(target_height * mask_ratio))
                    pad_x = (target_width - new_w) // 2
                    pad_y = (target_height - new_h) // 2
                    end_x = pad_x + new_w
                    end_y = pad_y + new_h
                    canvas = torch.tensor(fill_rgb, device=device, dtype=img.dtype).view(1, 1, 3).expand(target_height, target_width, 3).clone()
                    final_mask = torch.zeros(target_height, target_width, dtype=msk.dtype, device=device)
                    crop_img = hwc_to_bchw(img[crop_y1:crop_y2, crop_x1:crop_x2, :])
                    crop_msk = hw_to_b1hw(msk[crop_y1:crop_y2, crop_x1:crop_x2])
                    target_img = torch.zeros(1, 3, new_h, new_w, device=device)
                    scaled_img = bchw_to_hwc(scale_to_match(target_img, crop_img, is_mask=False))
                    canvas[pad_y:end_y, pad_x:end_x, :] = scaled_img
                    target_msk = torch.zeros(1, 1, new_h, new_w, device=device)
                    scaled_mask = b1hw_to_hw(scale_to_match(target_msk, crop_msk, is_mask=True))
                    final_mask[pad_y:end_y, pad_x:end_x] = scaled_mask
                    crop_data = CropData(
                        crop_x1, crop_y1, crop_x2, crop_y2,
                        pad_x, pad_y, new_w, new_h,
                        new_w / crop_w, new_h / crop_h,
                        target_width, target_height
                    )
                if apply_mask:
                    canvas = torch.cat([canvas, final_mask.unsqueeze(-1)], dim=-1)
                cropped_images.append(canvas)
                cropped_masks.append(final_mask)
                crop_infos.append(crop_data)
            return torch.stack(cropped_images), torch.stack(cropped_masks), crop_infos
        except Exception as e:
            handle_error(e, "CropByMask failed")

# CropByMaskRestore
class CropByMaskRestore:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "cropped_image": ("IMAGE",),
                "cropped_mask": ("MASK",),
                "crop_data": ("CROP_DATA",),
                "original_image": ("IMAGE",),
                "blend_hardness": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("restored_image",)
    FUNCTION = "restore_crop"
    CATEGORY = "ComfyPanel/Process & Restore"
    def _blend_region(self, orig, proc, mask, hardness):
        alpha = mask.astype(np.float32) / 255.0
        alpha = 1.0 - alpha
        alpha3 = np.expand_dims(alpha, -1)
        blended = orig.astype(np.float32) * alpha3 + proc.astype(np.float32) * (1.0 - alpha3)
        blended = np.clip(blended, 0, 255).astype(np.uint8)
        if hardness < 0.95:
            edge = ((alpha > 0.05) & (alpha < 0.95)).astype(np.uint8)
            if np.any(edge):
                smooth = cv2.GaussianBlur(blended, (3, 3), 0.5)
                for c in range(blended.shape[2]):
                    blended[edge > 0, c] = smooth[edge > 0, c]
        return blended
    def restore_crop(self, cropped_image, cropped_mask, crop_data, original_image, blend_hardness):
        results = []
        bs = min(original_image.shape[0], len(crop_data))
        for i in range(bs):
            try:
                d = [int(v) if isinstance(v, torch.Tensor) else int(v) for v in crop_data[i]]
                (crop_x1, crop_y1, crop_x2, crop_y2,
                 dst_x1, dst_y1, mask_w, mask_h,
                 scale_x, scale_y, canvas_w, canvas_h) = d
                orig_w = original_image.shape[2]
                orig_h = original_image.shape[1]
                proc_data = (cropped_image[i].cpu().numpy() * 255).astype(np.uint8)
                if (crop_x1 == 0 and crop_y1 == 0 and crop_x2 == orig_w and crop_y2 == orig_h
                    and mask_w == canvas_w and mask_h == canvas_h):
                    proc_rgb = proc_data[:, :, :3] if proc_data.shape[2] == 4 else proc_data
                    restored = cv2.resize(proc_rgb, (orig_w, orig_h), interpolation=cv2.INTER_CUBIC)
                    results.append(torch.from_numpy(restored.astype(np.float32) / 255.0))
                    continue
                if crop_x1 == 0 and crop_y1 == 0 and crop_x2 == original_image.shape[2] and crop_y2 == original_image.shape[1]:
                    proc_np = proc_data
                    if proc_np.shape[0] == original_image.shape[1] and proc_np.shape[1] == original_image.shape[2]:
                        proc_rgb = proc_np[:, :, :3] if proc_np.shape[2] == 4 else proc_np
                        results.append(torch.from_numpy(proc_rgb.astype(np.float32) / 255.0))
                        continue
                orig = (original_image[i].cpu().numpy() * 255).astype(np.uint8)
                proc = proc_data[:, :, :3] if proc_data.shape[2] == 4 else proc_data
                msk = (cropped_mask[i].cpu().numpy().squeeze() * 255).astype(np.uint8)
                if proc.shape[:2] != msk.shape[:2]:
                    msk = cv2.resize(msk, (proc.shape[1], proc.shape[0]), cv2.INTER_LINEAR)
                crop_w = crop_x2 - crop_x1
                crop_h = crop_y2 - crop_y1
                if crop_w <= 0 or crop_h <= 0:
                    results.append(original_image[i])
                    continue
                if canvas_w > 0 and canvas_h > 0 and mask_w > 0 and mask_h > 0:
                    sx1 = max(0, dst_x1)
                    sy1 = max(0, dst_y1)
                    sx2 = min(proc.shape[1], dst_x1 + mask_h)
                    sy2 = min(proc.shape[0], dst_y1 + mask_h)
                    proc_region = proc[dst_y1:dst_y1 + mask_h, dst_x1:dst_x1 + mask_w]
                    msk_region = msk[dst_y1:dst_y1 + mask_h, dst_x1:dst_x1 + mask_w]
                else:
                    proc_region = proc
                    msk_region = msk
                proc_resized = cv2.resize(proc_region, (crop_w, crop_h), interpolation=cv2.INTER_CUBIC)
                msk_resized = cv2.resize(msk_region, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)
                blended = self._blend_region(
                    orig[crop_y1:crop_y2, crop_x1:crop_x2],
                    proc_resized,
                    msk_resized,
                    blend_hardness
                )
                orig[crop_y1:crop_y2, crop_x1:crop_x2] = blended
                results.append(torch.from_numpy(orig.astype(np.float32) / 255.0))
            except Exception as e:
                print(f"[CropByMaskRestore] error at {i}: {e}")
                results.append(original_image[i])
        return (torch.stack(results),)

# Image & Mask Concat
class ImageConcat:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "bg_color_L": ("STRING", {"default": "#FFFFFF"}),
            },
            "optional": {
                "image_L": ("IMAGE", {"default": None}),
                "mask_L": ("MASK", {"default": None}),
                "image_R": ("IMAGE", {"default": None}), 
                "mask_R": ("MASK", {"default": None}),
            },
        }
    RETURN_TYPES = ("IMAGE", "MASK", "DICT")
    RETURN_NAMES = ("contact_image", "contact_mask", "contact_data")
    FUNCTION = "concat_images"
    CATEGORY = "ComfyPanel/Process & Restore"
    def process_image_L(self, image, mask, bg_color):
        img_pil = tensor2pil(image)[0].convert("RGB")
        if mask is not None:
            w, h = img_pil.size
            mask_np = validate_mask_dimensions(mask.cpu().numpy())
            mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8)).convert("L")
            bg = Image.new("RGBA", (w, h), bg_color)
            rgba = Image.new("RGBA", (w, h))
            rgba.paste(img_pil, mask=mask_pil)
            return Image.alpha_composite(bg, rgba)
        else:
            return img_pil
    def concat_images(self, image_L, image_R, mask_R, bg_color_L, mask_L=None):
        try:
            bg_color = parse_color(bg_color_L)
            comp_L = self.process_image_L(image_L, mask_L, bg_color)
            comp_R = tensor2pil(image_R)[0].convert("RGB")
            w_L, h_L = comp_L.size
            w_R, h_R = comp_R.size
            total_width = w_L + w_R
            max_height = max(h_L, h_R)
            composite = Image.new("RGB", (total_width, max_height), (255, 255, 255))
            composite.paste(comp_L, (0, (max_height - h_L) // 2))
            composite.paste(comp_R, (w_L, (max_height - h_R) // 2))
            composite_mask = torch.zeros((mask_R.shape[0], max_height, total_width), dtype=torch.float32)
            for i in range(mask_R.shape[0]):
                mask = mask_R[i].squeeze() if mask_R[i].ndim == 3 else mask_R[i]
                upscaled = torch.nn.functional.interpolate(
                    mask.unsqueeze(0).unsqueeze(0),
                    size=(h_R, w_R),
                    mode="bicubic",
                    align_corners=False
                ).squeeze()
                y_start = (max_height - h_R) // 2
                x_start = w_L
                composite_mask[i, y_start:y_start+h_R, x_start:x_start+w_R] = upscaled
            meta_data = {
                "left_width": w_L,
                "right_start": w_L,
                "total_width": total_width,
                "max_height": max_height,
                "right_original_size": (w_R, h_R)
            }
            return (pil2tensor(composite), composite_mask, meta_data)
        except Exception as e:
            raise RuntimeError(f"Image concatenation failed: {str(e)}")

# Image Concat Restore
class ImageConcatRestore:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "contact_image": ("IMAGE",),
                "contact_data": ("DICT",),
            },
        }
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("restored_image",)
    FUNCTION = "restore_image"
    CATEGORY = "ComfyPanel/Process & Restore"
    def _restore_right_image(self, img_pil, meta_data):
        w_L = meta_data["left_width"]
        orig_w, orig_h = meta_data["right_original_size"]
        max_h = meta_data["max_height"]
        y_start = (max_h - orig_h) // 2
        crop_box = (w_L, y_start, w_L + orig_w, y_start + orig_h)
        cropped = img_pil.crop(crop_box)
        if cropped.size != (orig_w, orig_h):
            cropped = cropped.resize((orig_w, orig_h), Image.BICUBIC)
        return cropped
    def restore_image(self, contact_image, contact_data):
        if not isinstance(contact_data, dict):
            raise ValueError("Invalid metadata format")
        batch_images = tensor2pil(contact_image)
        restored = [self._restore_right_image(img, contact_data) for img in batch_images]
        result = torch.cat([pil2tensor(img) for img in restored], dim=0)
        return result,

# ImageMask_Scale  (image or mask, Call scale_any())
class ImageMask_Scale:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "target_size": ("INT", {"default": 512, "min": 1, "max": 4096}),
                "scale_mode": (["scale up", "scale down", "rescale"],),
                "reference_side": (["long side", "short side"],),
            },
            "optional": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
            },
        }
    RETURN_TYPES = ("IMAGE", "MASK", "SCALE_DATA")
    RETURN_NAMES = ("scaled_image", "scaled_mask", "scale_data")
    FUNCTION = "scale"
    CATEGORY = "ComfyPanel/Process & Restore"
    def scale(self, target_size, scale_mode, reference_side, image=None, mask=None):
        scale_node = ScaleAny()
        def _resize(t):
            if t is None:
                return None
            return scale_node.scale_any(
                t, target_size=target_size, scale_mode=scale_mode, reference_side=reference_side
            )[0]
        scaled_image = _resize(image)
        scaled_mask = _resize(mask)
        h = image.shape[1] if image is not None else mask.shape[1]
        w = image.shape[2] if image is not None else mask.shape[2]
        new_width, new_height, _, _, _ = calculate_scale_with_mode(
            w, h, target_size, scale_mode, reference_side
        )
        scale_data = {
            "original_width": w,
            "original_height": h,
            "scaled_width": new_width,
            "scaled_height": new_height
        }
        return scaled_image, scaled_mask, scale_data

# Image & Mask Scale Restore
class ImageMask_ScaleRestore:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "restore_mode": (["original", "masked"], {"default": "original"}),
            },
            "optional": {
                "scaled_image": ("IMAGE",),
                "scaled_mask": ("MASK",),
                "scale_data": ("SCALE_DATA",),
            }
        }
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("restored_image", "restored_mask")
    FUNCTION = "restore_scale"
    CATEGORY = "ComfyPanel/Process & Restore"
    def restore_scale(self, scale_data, restore_mode, scaled_image=None, scaled_mask=None):
        if scale_data is None:
            raise ValueError("Missing scale_data input")
        if scaled_image is None and scaled_mask is None:
            raise ValueError("Provide at least image or mask")
        orig_w = int(scale_data["original_width"])
        orig_h = int(scale_data["original_height"])
        scaled_w = int(scale_data["scaled_width"])
        scaled_h = int(scale_data["scaled_height"])
        def restore_tensor(tensor, orig_h, orig_w):
            if tensor is None:
                return None
            h, w = tensor.shape[1:3]
            if h == orig_h and w == orig_w:
                return tensor
            if tensor.ndim == 4 and tensor.shape[-1] == 3:  # image
                tensor = F.interpolate(
                    tensor.permute(0, 3, 1, 2),
                    size=(orig_h, orig_w),
                    mode="bicubic",
                    align_corners=False
                ).permute(0, 2, 3, 1)
            else:  # mask
                tensor = F.interpolate(
                    tensor.unsqueeze(1),
                    size=(orig_h, orig_w),
                    mode="nearest"
                ).squeeze(1)
            return tensor
        restored_image = restore_tensor(scaled_image, orig_h, orig_w)
        restored_mask = restore_tensor(scaled_mask, orig_h, orig_w)
        if restored_mask is not None:
            restored_mask = torch.clamp(restored_mask, 0.0, 1.0)
        if restore_mode == "original":
            return (restored_image, restored_mask)
        if restored_image is None or restored_mask is None:
            raise ValueError("Both image and mask are required for masked mode")
        mask_exp = restored_mask.unsqueeze(-1)
        rgb_part = restored_image * mask_exp
        rgba_image = torch.cat([rgb_part, mask_exp], dim=-1)
        return (rgba_image, restored_mask)

class FluxKontextImageCompensate:
    """
    Flux Kontext Stretch Compensation Node.
    Expands canvas height to counteract 5.2% vertical stretch during sampling.
    """
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "comp_mode": (["Mirror", "Replicate", "Solid Color"], {"default": "Solid Color"}),
                "solid_color": ("STRING", {"default": "#FFFFFF"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "COMPENSATION_DATA", "INT", "INT")
    RETURN_NAMES = ("comp_image", "comp_data", "width", "height")
    FUNCTION = "compensate"
    CATEGORY = "ComfyPanel/Process & Restore"

    def compensate(self, image, comp_mode, solid_color="#FFFFFF"):
        k_factor = 1.0521
        img = image.permute(0, 3, 1, 2)
        mode_map = {"Mirror": "reflect", "Replicate": "replicate", "Solid Color": "constant"}
        pt_pad_mode = mode_map.get(comp_mode, "reflect")
        
        old_h, old_w = img.shape[2], img.shape[3]
        
        new_h = int(round(old_h * k_factor / 16)) * 16
        pad_total_y = new_h - old_h
        pad_top = pad_total_y // 2
        pad_bottom = pad_total_y - pad_top
        
        new_w = int(round(old_w * k_factor / 16)) * 16
        pad_total_x = new_w - old_w
        pad_left = pad_total_x // 2
        pad_right = pad_total_x - pad_left
        
        try:
            if comp_mode == "Solid Color":
                r, g, b, a = parse_color(solid_color)
                b_sz, c, _, _ = img.shape
                canvas = torch.zeros((b_sz, c, new_h, new_w), dtype=img.dtype, device=img.device)
                c_data = [r/255.0, g/255.0, b/255.0, a/255.0]
                for i in range(min(c, 4)):
                    canvas[:, i, :, :] = c_data[i]
                canvas[:, :, pad_top:pad_top+old_h, pad_left:pad_left+old_w] = img
                img_out = canvas
            else:
                img_out = F.pad(img, (pad_left, pad_right, pad_top, pad_bottom), mode=pt_pad_mode)
        except: 
            img_out = F.pad(img, (pad_left, pad_right, pad_top, pad_bottom), mode='constant', value=1.0)
        
        data = {
            "orig_h": old_h, 
            "orig_w": old_w, 
            "new_h": new_h,
            "new_w": new_w,
            "pad_top": pad_top,
            "pad_bottom": pad_bottom,
            "pad_left": pad_left,
            "pad_right": pad_right,
        }
        
        output_image = img_out.permute(0, 2, 3, 1)
        return (output_image, data, new_w, new_h)

class FluxKontextImageRestore:
    """
    Flux Kontext Stretch Restore Node.
    Restores image aspect ratio/composition using Kornia LoFTR or Template Matching alignment.
    """
    
    # LoFTR matcher singleton (lazy loaded)
    _loftr_matcher = None
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "comp_image": ("IMAGE",),
                "comp_data": ("COMPENSATION_DATA",),
                "original_image": ("IMAGE",), 
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("restored_image",)
    FUNCTION = "restore"
    CATEGORY = "ComfyPanel/Process & Restore"

    @classmethod
    def get_loftr_matcher(cls, device):
        """
        Lazy load LoFTR matcher from ComfyUI models directory.
        Model will be stored in: ComfyUI/models/loftr/loftr_outdoor.ckpt
        """
        if cls._loftr_matcher is None:
            # Set up model path in ComfyUI models directory
            loftr_model_dir = os.path.join(folder_paths.models_dir, "loftr")
            os.makedirs(loftr_model_dir, exist_ok=True)
            
            model_path = os.path.join(loftr_model_dir, "loftr_outdoor.ckpt")
            
            if os.path.exists(model_path):
                # Load from local path
                cls._loftr_matcher = LoFTR(pretrained=model_path)
            else:
                # Download and save to local path
                import urllib.request
                url = "http://cmp.felk.cvut.cz/~mishkdmy/models/loftr_outdoor.ckpt"
                print(f"[ComfyPanel] Downloading LoFTR model to {model_path}...")
                urllib.request.urlretrieve(url, model_path)
                print(f"[ComfyPanel] LoFTR model downloaded successfully.")
                cls._loftr_matcher = LoFTR(pretrained=model_path)
        
        return cls._loftr_matcher.to(device).eval()

    def align_image_kornia(self, generated_img: torch.Tensor, reference_img: torch.Tensor, orig_h: int, orig_w: int):
        """Kornia LoFTR alignment."""
        device = generated_img.device
        ref_bchw = reference_img.permute(0, 3, 1, 2).to(device)
        
        gen_h, gen_w = generated_img.shape[2], generated_img.shape[3]
        ref_resized = F.interpolate(ref_bchw, size=(gen_h, gen_w), mode='bilinear', align_corners=False)
        
        gen_gray = kornia.color.rgb_to_grayscale(generated_img)
        ref_gray = kornia.color.rgb_to_grayscale(ref_resized)
        
        matcher = self.get_loftr_matcher(device)
        with torch.no_grad():
            correspondences = matcher({"image0": gen_gray, "image1": ref_gray})
        
        kpts0 = correspondences['keypoints0']
        kpts1 = correspondences['keypoints1']
        confidence = correspondences['confidence']
        
        mask = confidence > 0.5
        kpts0_filtered = kpts0[mask]
        kpts1_filtered = kpts1[mask]
        
        if len(kpts0_filtered) < 4:
            return None
        
        kpts0_np = kpts0_filtered.cpu().numpy()
        kpts1_np = kpts1_filtered.cpu().numpy()
        
        H, inliers = cv2.findHomography(kpts0_np, kpts1_np, cv2.RANSAC, 5.0)
        
        if H is None or np.sum(inliers) < 4:
            return None
        
        H_tensor = torch.from_numpy(H).float().to(device).unsqueeze(0)
        aligned = warp_perspective(generated_img, H_tensor, (gen_h, gen_w), mode='bilinear', padding_mode='border')
        
        aligned_final = F.interpolate(aligned, size=(orig_h, orig_w), mode='bicubic', align_corners=False)
        return aligned_final

    def align_image_template(self, main_img_np, ref_img_np):
        """Legacy template matching alignment."""
        main_gray = cv2.cvtColor(main_img_np, cv2.COLOR_RGB2GRAY)
        ref_gray = cv2.cvtColor(ref_img_np, cv2.COLOR_RGB2GRAY)
        
        ref_h, ref_w = ref_gray.shape[:2]
        main_h, main_w = main_gray.shape[:2]
        
        best_score = -1
        best_scale = 1.0
        best_y = 0
        best_x = 0
        
        base_ratio = ref_h / main_h
        search_scales = np.linspace(base_ratio * 0.9, 1.1, 40)
        
        crop_h = int(ref_h * 0.5)
        crop_w = int(ref_w * 0.5)
        crop_y = (ref_h - crop_h) // 2
        crop_x = (ref_w - crop_w) // 2
        
        ref_template = ref_gray[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
        
        for s in search_scales:
            target_h = int(main_h * s)
            if target_h < crop_h: continue
            
            resized_main = cv2.resize(main_gray, (main_w, target_h), interpolation=cv2.INTER_LINEAR)
            
            res = cv2.matchTemplate(resized_main, ref_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val > best_score:
                best_score = max_val
                best_scale = s
                found_x, found_y = max_loc
                best_y = found_y - crop_y
                best_x = found_x - crop_x
                
        return best_scale, best_y, best_x

    def restore(self, comp_image, comp_data, original_image):
        img = comp_image.permute(0, 3, 1, 2)
        orig_h, orig_w = comp_data["orig_h"], comp_data["orig_w"]
        
        try:
            aligned = self.align_image_kornia(img, original_image, orig_h, orig_w)
            if aligned is not None:
                return (aligned.permute(0, 2, 3, 1),)
        except Exception:
            pass
        
        final_scale_y = orig_h / img.shape[2] 
        final_scale_x = orig_w / img.shape[3]
        final_offset_y = 0
        final_offset_x = 0
        
        try:
            ref_np = (original_image[0].cpu().numpy() * 255).astype(np.uint8)
            main_np = (img[0].permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
            
            scale_found, off_y, off_x = self.align_image_template(main_np, ref_np)
            
            final_scale_y = scale_found
            final_scale_x = 1.0
            final_offset_y = off_y
            final_offset_x = off_x
        except Exception:
            pass

        target_h = int(img.shape[2] * final_scale_y)
        target_w = int(img.shape[3] * final_scale_x)
        if target_h < 1: target_h = 1
        if target_w < 1: target_w = 1
        
        img_scaled = F.interpolate(img, size=(target_h, target_w), mode='bicubic', align_corners=False)
        
        y_start = int(final_offset_y)
        x_start = int(final_offset_x)
        y_end = y_start + orig_h
        x_end = x_start + orig_w
        
        pad_l, pad_r, pad_t, pad_b = 0, 0, 0, 0
        if y_start < 0:
            pad_t = -y_start
            y_start = 0
            y_end += pad_t
        if y_end > img_scaled.shape[2]:
            pad_b = y_end - img_scaled.shape[2]
        if x_start < 0:
            pad_l = -x_start
            x_start = 0
            x_end += pad_l
        if x_end > img_scaled.shape[3]:
            pad_r = x_end - img_scaled.shape[3]
            
        if any([pad_l, pad_r, pad_t, pad_b]):
            img_scaled = F.pad(img_scaled, (pad_l, pad_r, pad_t, pad_b), mode='replicate')
            
        img_out = img_scaled[:, :, y_start:y_end, x_start:x_end]
        
        if img_out.shape[2] != orig_h or img_out.shape[3] != orig_w:
            img_out = F.interpolate(img_out, size=(orig_h, orig_w), mode='bicubic')
        
        return (img_out.permute(0, 2, 3, 1),)


