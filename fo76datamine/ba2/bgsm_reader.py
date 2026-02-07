"""Extract diffuse texture path from BGSM/BGEM material files.

BGSM (Bethesda Game Studio Material) format:
  - 4 bytes magic ('BGSM' or 'BGEM')
  - uint32 version
  - Fixed header fields (flags, UV params, etc.)
  - Length-prefixed texture path strings (uint32 len + chars)
  - First texture string = diffuse texture (_d.dds)
"""
from __future__ import annotations

import struct

# Offset where texture strings begin, by material type and version.
# These are determined empirically from Fallout 76 data files.
# BGSM: magic(4) + version(4) + tile_flags(4) + bools/floats/ints(48) = offset 60
_BGSM_TEXTURE_OFFSET = 60


def extract_diffuse_path(material_data: bytes) -> str | None:
    """Extract the diffuse texture path from BGSM or BGEM material data.

    Returns the texture path string, or None if parsing fails.
    """
    if len(material_data) < _BGSM_TEXTURE_OFFSET + 5:
        return None

    magic = material_data[:4]
    if magic not in (b"BGSM", b"BGEM"):
        return None

    try:
        return _read_first_texture(material_data)
    except (struct.error, IndexError, UnicodeDecodeError):
        return None


def _read_first_texture(data: bytes) -> str | None:
    """Read the first length-prefixed texture string from the material.

    Scans for the first valid DDS path after the header fields.
    """
    # Try the known offset first (works for standard BGSM v22)
    result = _try_read_string_at(data, _BGSM_TEXTURE_OFFSET)
    if result and result.lower().endswith(".dds"):
        return result

    # Fallback: scan for the first length-prefixed string that ends in .dds
    for offset in range(40, min(120, len(data) - 8)):
        result = _try_read_string_at(data, offset)
        if result and result.lower().endswith(".dds"):
            return result

    return None


def _try_read_string_at(data: bytes, offset: int) -> str | None:
    """Try to read a uint32 length-prefixed string at the given offset."""
    if offset + 4 > len(data):
        return None
    slen = struct.unpack_from("<I", data, offset)[0]
    if slen < 5 or slen > 260 or offset + 4 + slen > len(data):
        return None
    try:
        s = data[offset + 4:offset + 4 + slen].decode("ascii")
        # Validate it looks like a path
        if "/" in s or "\\" in s:
            return s.rstrip("\x00 ")
    except UnicodeDecodeError:
        pass
    return None
