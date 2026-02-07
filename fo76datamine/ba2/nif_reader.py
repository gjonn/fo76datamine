"""Extract material paths (.bgsm/.bgem) from NIF file headers.

Parses the Gamebryo NIF string table without fully parsing block data.
Supports Fallout 76 format (NIF version 20.2.0.7, BS stream version 130+).
"""
from __future__ import annotations

import struct


def extract_material_paths(nif_data: bytes) -> list[str]:
    """Extract .bgsm and .bgem material paths from a NIF file's string table.

    Returns a list of material paths found (lowercase, forward slashes).
    """
    try:
        strings = _parse_string_table(nif_data)
    except (struct.error, IndexError, ValueError):
        return []

    materials = []
    for s in strings:
        lower = s.lower()
        if lower.endswith(".bgsm") or lower.endswith(".bgem"):
            materials.append(s.replace("\\", "/"))
    return materials


def _parse_string_table(data: bytes) -> list[str]:
    """Parse the NIF header and return the string table entries."""
    # Header string ends with newline
    newline = data.index(b"\n")
    pos = newline + 1

    # Version (4) + endian (1) + user_version (4) + num_blocks (4) + bs_stream_version (4)
    version = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    pos += 1  # endian
    pos += 4  # user_version
    num_blocks = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    bs_ver = struct.unpack_from("<I", data, pos)[0]
    pos += 4

    # 3 standard export info ShortStrings (uint8 len + chars)
    for _ in range(3):
        slen = data[pos]; pos += 1
        pos += slen

    # BS stream >= 130: 3 additional ShortStrings + uint16
    if bs_ver >= 130:
        for _ in range(3):
            slen = data[pos]; pos += 1
            pos += slen
        pos += 2  # unknown uint16

    # Block type names: uint16 count, then (uint32 len + chars) per name
    num_block_types = struct.unpack_from("<H", data, pos)[0]
    pos += 2
    for _ in range(num_block_types):
        slen = struct.unpack_from("<I", data, pos)[0]
        pos += 4 + slen

    # Block type indices: uint16 per block
    pos += num_blocks * 2

    # Block sizes: uint32 per block
    pos += num_blocks * 4

    # String table
    num_strings = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    pos += 4  # max_string_length

    strings = []
    for _ in range(num_strings):
        slen = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        s = data[pos:pos + slen].decode("ascii", errors="replace")
        strings.append(s)
        pos += slen

    return strings
