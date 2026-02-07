"""DDS file reconstruction from DX10 BA2 texture entries."""
from __future__ import annotations

import struct

from fo76datamine.ba2.dx10_reader import DX10FileEntry

# DXGI format constants
DXGI_FORMAT_BC1_UNORM = 71
DXGI_FORMAT_BC3_UNORM = 77
DXGI_FORMAT_BC5_UNORM = 83
DXGI_FORMAT_BC7_UNORM = 98
DXGI_FORMAT_R8G8B8A8_UNORM = 28
DXGI_FORMAT_B8G8R8A8_UNORM = 87

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


def _compute_pitch(width: int, height: int, dxgi_format: int) -> int:
    """Compute the linear size for a given format and dimensions."""
    if dxgi_format in (DXGI_FORMAT_BC1_UNORM,):
        block_size = 8
    elif dxgi_format in (DXGI_FORMAT_BC3_UNORM, DXGI_FORMAT_BC5_UNORM, DXGI_FORMAT_BC7_UNORM):
        block_size = 16
    elif dxgi_format in (DXGI_FORMAT_R8G8B8A8_UNORM, DXGI_FORMAT_B8G8R8A8_UNORM):
        return width * height * 4
    else:
        block_size = 16  # default to 16-byte blocks
    blocks_wide = max(1, (width + 3) // 4)
    blocks_high = max(1, (height + 3) // 4)
    return blocks_wide * blocks_high * block_size


def _build_header(entry: DX10FileEntry, num_mips: int) -> bytes:
    """Build a 148-byte DDS header (124 DDS_HEADER + 20 DDS_HEADER_DXT10 + 4 magic)."""
    # DDS_HEADER (124 bytes)
    header = bytearray(DDS_HEADER_SIZE)
    flags = DDSD_REQUIRED | DDSD_LINEARSIZE
    if num_mips > 1:
        flags |= DDSD_MIPMAPCOUNT

    pitch = _compute_pitch(entry.width, entry.height, entry.dxgi_format)

    struct.pack_into("<I", header, 0, DDS_HEADER_SIZE)       # dwSize
    struct.pack_into("<I", header, 4, flags)                  # dwFlags
    struct.pack_into("<I", header, 8, entry.height)           # dwHeight
    struct.pack_into("<I", header, 12, entry.width)           # dwWidth
    struct.pack_into("<I", header, 16, pitch)                 # dwPitchOrLinearSize
    struct.pack_into("<I", header, 24, 1)                     # dwDepth
    struct.pack_into("<I", header, 28, num_mips)              # dwMipMapCount

    # DDS_PIXELFORMAT at offset 76 (size 32)
    struct.pack_into("<I", header, 76, DDS_PIXELFORMAT_SIZE)  # dwSize
    struct.pack_into("<I", header, 80, DDPF_FOURCC)           # dwFlags
    header[84:88] = b"DX10"                                   # dwFourCC

    # dwCaps
    caps = DDSCAPS_TEXTURE
    if num_mips > 1:
        caps |= DDSCAPS_MIPMAP | DDSCAPS_COMPLEX
    struct.pack_into("<I", header, 108, caps)

    # DDS_HEADER_DXT10 (20 bytes)
    dxt10 = bytearray(20)
    struct.pack_into("<I", dxt10, 0, entry.dxgi_format)       # dxgiFormat
    struct.pack_into("<I", dxt10, 4, 3)                       # resourceDimension = D3D10_RESOURCE_DIMENSION_TEXTURE2D
    struct.pack_into("<I", dxt10, 8, 0)                       # miscFlag
    struct.pack_into("<I", dxt10, 12, 1)                      # arraySize
    struct.pack_into("<I", dxt10, 16, 0)                      # miscFlags2

    return DDS_MAGIC + bytes(header) + bytes(dxt10)


def build_dds(entry: DX10FileEntry, chunk_data_list: list[bytes]) -> bytes:
    """Build a complete DDS file from a DX10 entry and all chunk data."""
    header = _build_header(entry, entry.num_mips)
    return header + b"".join(chunk_data_list)


def build_dds_first_mip(entry: DX10FileEntry, first_chunk_data: bytes) -> bytes:
    """Build a DDS file with only the first mip level (fast path for icons)."""
    header = _build_header(entry, 1)
    return header + first_chunk_data
