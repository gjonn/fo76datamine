"""DDS to PNG conversion via Pillow."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path


def dds_to_png(dds_data: bytes, output_path: Path, max_size: int = 128) -> bool:
    """Convert DDS data to a PNG file, resizing if needed.

    Returns True on success, False if the format is unsupported or data is corrupt.
    """
    try:
        from PIL import Image

        img = Image.open(BytesIO(dds_data))

        # Resize if larger than max_size (0 = no resize)
        if max_size > 0 and (img.width > max_size or img.height > max_size):
            ratio = min(max_size / img.width, max_size / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Ensure RGBA for transparency support
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "PNG")
        return True
    except Exception:
        return False
