"""DDS file reconstruction from DX10 BA2 texture entries."""
from __future__ import annotations

import struct

from fo76datamine.ba2.dx10_reader import DX10FileEntry

# DXGI format constants
DXGI_FORMAT_R8G8B8A8_UNORM = 28
DXGI_FORMAT_R8G8B8A8_UNORM_SRGB = 29
DXGI_FORMAT_B8G8R8A8_UNORM = 87
DXGI_FORMAT_B8G8R8A8_UNORM_SRGB = 91

# Block-compressed formats: (dxgi_format) -> (block_bytes, legacy_fourcc or None)
# Legacy FourCC is used when Pillow doesn't support the format via DXT10 header.
_BC_FORMATS: dict[int, tuple[int, bytes | None]] = {
    # BC1 (8 bytes/block) — use legacy DXT1
    71: (8, b"DXT1"),   # BC1_UNORM
    72: (8, b"DXT1"),   # BC1_UNORM_SRGB
    # BC2 (16 bytes/block) — use legacy DXT3
    74: (16, b"DXT3"),  # BC2_UNORM
    75: (16, b"DXT3"),  # BC2_UNORM_SRGB
    # BC3 (16 bytes/block) — use legacy DXT5
    77: (16, b"DXT5"),  # BC3_UNORM
    78: (16, b"DXT5"),  # BC3_UNORM_SRGB
    # BC4 (8 bytes/block) — use legacy ATI1
    79: (8, b"ATI1"),   # BC4_UNORM
    80: (8, b"ATI1"),   # BC4_SNORM
    # BC5 (16 bytes/block) — Pillow supports via DXT10
    83: (16, None),     # BC5_UNORM
    84: (16, None),     # BC5_SNORM
    # BC7 (16 bytes/block) — Pillow supports via DXT10
    98: (16, None),     # BC7_UNORM
    99: (16, None),     # BC7_UNORM_SRGB
}

# Uncompressed formats: bytes per pixel
_UNCOMPRESSED = {
    DXGI_FORMAT_R8G8B8A8_UNORM: 4,
    DXGI_FORMAT_R8G8B8A8_UNORM_SRGB: 4,
    DXGI_FORMAT_B8G8R8A8_UNORM: 4,
    DXGI_FORMAT_B8G8R8A8_UNORM_SRGB: 4,
}

# DDS constants
DDS_MAGIC = b"DDS "
DDSD_CAPS = 0x1
DDSD_HEIGHT = 0x2
DDSD_WIDTH = 0x4
DDSD_PIXELFORMAT = 0x1000
DDSD_MIPMAPCOUNT = 0x20000
DDSD_LINEARSIZE = 0x80000
DDSD_REQUIRED = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT

DDPF_FOURCC = 0x4

DDSCAPS_TEXTURE = 0x1000
DDSCAPS_MIPMAP = 0x400000
DDSCAPS_COMPLEX = 0x8

DDS_HEADER_SIZE = 124
DDS_PIXELFORMAT_SIZE = 32


def _mip0_size(width: int, height: int, dxgi_format: int) -> int:
    """Compute the byte size of mip level 0."""
    if dxgi_format in _UNCOMPRESSED:
        return width * height * _UNCOMPRESSED[dxgi_format]
    bc = _BC_FORMATS.get(dxgi_format)
    if bc is not None:
        block_bytes = bc[0]
    else:
        block_bytes = 16  # fallback
    blocks_wide = max(1, (width + 3) // 4)
    blocks_high = max(1, (height + 3) // 4)
    return blocks_wide * blocks_high * block_bytes


def _build_header(entry: DX10FileEntry, num_mips: int) -> bytes:
    """Build a DDS header. Uses legacy FourCC for BC1/BC3 compatibility with Pillow."""
    header = bytearray(DDS_HEADER_SIZE)
    flags = DDSD_REQUIRED | DDSD_LINEARSIZE
    if num_mips > 1:
        flags |= DDSD_MIPMAPCOUNT

    pitch = _mip0_size(entry.width, entry.height, entry.dxgi_format)

    struct.pack_into("<I", header, 0, DDS_HEADER_SIZE)       # dwSize
    struct.pack_into("<I", header, 4, flags)                  # dwFlags
    struct.pack_into("<I", header, 8, entry.height)           # dwHeight
    struct.pack_into("<I", header, 12, entry.width)           # dwWidth
    struct.pack_into("<I", header, 16, pitch)                 # dwPitchOrLinearSize
    struct.pack_into("<I", header, 24, 1)                     # dwDepth
    struct.pack_into("<I", header, 28, num_mips)              # dwMipMapCount

    # DDS_PIXELFORMAT at offset 72 (after 11 reserved uint32s starting at 28)
    struct.pack_into("<I", header, 72, DDS_PIXELFORMAT_SIZE)  # dwSize
    struct.pack_into("<I", header, 76, DDPF_FOURCC)           # dwFlags

    # dwCaps at offset 104
    caps = DDSCAPS_TEXTURE
    if num_mips > 1:
        caps |= DDSCAPS_MIPMAP | DDSCAPS_COMPLEX
    struct.pack_into("<I", header, 104, caps)

    # Check if this format has a legacy FourCC (better Pillow compatibility)
    bc = _BC_FORMATS.get(entry.dxgi_format)
    if bc is not None and bc[1] is not None:
        # Legacy header (no DXT10 extension needed)
        header[80:84] = bc[1]
        return DDS_MAGIC + bytes(header)

    # DXT10 extended header for BC5, BC7, uncompressed, etc.
    header[80:84] = b"DX10"
    dxt10 = bytearray(20)
    struct.pack_into("<I", dxt10, 0, entry.dxgi_format)       # dxgiFormat
    struct.pack_into("<I", dxt10, 4, 3)                       # D3D10_RESOURCE_DIMENSION_TEXTURE2D
    struct.pack_into("<I", dxt10, 8, 0)                       # miscFlag
    struct.pack_into("<I", dxt10, 12, 1)                      # arraySize
    struct.pack_into("<I", dxt10, 16, 0)                      # miscFlags2
    return DDS_MAGIC + bytes(header) + bytes(dxt10)


def build_dds(entry: DX10FileEntry, chunk_data_list: list[bytes]) -> bytes:
    """Build a complete DDS file from a DX10 entry and all chunk data."""
    header = _build_header(entry, entry.num_mips)
    return header + b"".join(chunk_data_list)


def build_dds_first_mip(entry: DX10FileEntry, first_chunk_data: bytes) -> bytes:
    """Build a DDS file with only mip level 0 (fast path for icons).

    The chunk may contain multiple mip levels — we truncate to mip 0 only.
    """
    header = _build_header(entry, 1)
    mip0_bytes = _mip0_size(entry.width, entry.height, entry.dxgi_format)
    # Truncate to mip 0 if chunk contains more data
    data = first_chunk_data[:mip0_bytes] if len(first_chunk_data) > mip0_bytes else first_chunk_data
    return header + data
