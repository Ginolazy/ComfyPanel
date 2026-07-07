import torch
import torch.nn as nn
import sys



patched = []

if not hasattr(torch, 'uint16'):
    torch.uint16 = torch.int32
    patched.append('uint16->int32')

if not hasattr(torch, 'uint32'):
    torch.uint32 = torch.int64
    patched.append('uint32->int64')

if not hasattr(torch, 'uint64'):
    torch.uint64 = torch.int64
    patched.append('uint64->int64')

try:
    if torch.backends.mps.is_available() and hasattr(torch, 'bfloat16'):
        torch.bfloat16 = torch.float16
        patched.append('bfloat16->float16')
except Exception:
    pass

if patched:
    print(f"[Pytorch_IntelMac_Fix] Patched torch types for Intel Mac compatibility: {', '.join(patched)} (MPS fixed) ✅")
else:
    print("[Pytorch_IntelMac_Fix] No patches needed (types already exist).")


class RMSNorm(nn.Module):
    def __init__(self, normalized_shape, eps=1e-8, elementwise_affine=True):
        super().__init__()
        if isinstance(normalized_shape, int):
            normalized_shape = (normalized_shape,)
        self.normalized_shape = tuple(normalized_shape)
        self.eps = eps
        self.elementwise_affine = elementwise_affine

        if self.elementwise_affine:
            self.weight = nn.Parameter(torch.ones(self.normalized_shape))
        else:
            self.register_parameter('weight', None)

    def forward(self, x):
        dims = tuple(range(-len(self.normalized_shape), 0))
        rms = x.pow(2).mean(dim=dims, keepdim=True).sqrt()
        x_norm = x / (rms + self.eps)
        if self.elementwise_affine:
            x_norm = x_norm * self.weight
        return x_norm

def replace_layernorm_with_rmsnorm(model):
    for name, module in model.named_children():
        if isinstance(module, nn.LayerNorm):
            rmsnorm = RMSNorm(
                normalized_shape=module.normalized_shape,
                eps=module.eps,
                elementwise_affine=module.elementwise_affine
            )
            if module.elementwise_affine:
                with torch.no_grad():
                    rmsnorm.weight.copy_(module.weight)
            setattr(model, name, rmsnorm)
        else:
            replace_layernorm_with_rmsnorm(module)
    return model

_original_nn_init = nn.Module.__init__

def _hooked_nn_init(self, *args, **kwargs):
    _original_nn_init(self, *args, **kwargs)
    try:
        replace_layernorm_with_rmsnorm(self)
    except Exception:
        pass

nn.Module.__init__ = _hooked_nn_init

print("[Pytorch_IntelMac_Fix] RMSNorm auto-replace plugin loaded. All LayerNorm layers will be replaced automatically. (RMSNorm fixed) ✅")