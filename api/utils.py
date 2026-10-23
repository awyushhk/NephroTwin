"""
api/utils.py — Helper utilities for serialization, image encoding, and validation.
"""

import base64
import io
import math
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def is_valid_image_extension(filename: Optional[str]) -> bool:
    """Check if the filename has an accepted image extension."""
    if not filename:
        return False
    suffix = Path(filename).suffix.lower()
    return suffix in ALLOWED_IMAGE_EXTENSIONS


def numpy_to_base64_png(arr: np.ndarray) -> str:
    """Convert a numpy array (uint8 RGB/grayscale) to a base64 data URI PNG string."""
    if arr.dtype != np.uint8:
        # Normalize if floating point between 0 and 1 or 0 and 255
        if arr.max() <= 1.0:
            arr = (arr * 255).astype(np.uint8)
        else:
            arr = np.clip(arr, 0, 255).astype(np.uint8)

    img = Image.fromarray(arr)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def clean_for_json(val: Any) -> Any:
    """
    Recursively transform NumPy types, NaNs, infinities, and arrays into JSON-safe Python types.
    """
    if isinstance(val, dict):
        return {k: clean_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [clean_for_json(v) for v in val]
    if isinstance(val, np.ndarray):
        # If it's a 3D image array (overlay), encode as base64 PNG data URI
        if val.ndim == 3 and val.shape[2] in (3, 4):
            return numpy_to_base64_png(val)
        return val.tolist()
    if isinstance(val, np.generic):
        item = val.item()
        if isinstance(item, float) and (math.isnan(item) or math.isinf(item)):
            return None
        return item
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val
