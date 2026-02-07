"""BA2 (BTDX v1 DX10) texture archive reader for Fallout 76."""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_HEADER = struct.Struct("<4sI4sIQ")  # magic(4) + version(4) + type(4) + filecount(4) + nametable_offset(8)


@dataclass(slots=True)
class DX10Chunk:
    """A single mip-level chunk within a DX10 texture entry."""
    offset: int
    packed_size: int
    unpacked_size: int
    start_mip: int
    end_mip: int


@dataclass(slots=True)
class DX10FileEntry:
    """A texture file entry in a DX10 BA2 archive."""
    name: str
    height: int
    width: int
    num_mips: int
    dxgi_format: int
    tile_mode: int
    chunks: list[DX10Chunk] = field(default_factory=list)


class DX10Reader:
    """Reader for Bethesda Archive 2 (BA2) DX10 texture format."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: list[DX10FileEntry] = []
        self._name_index: Optional[dict[str, DX10FileEntry]] = None
        self._parse()

    def _parse(self):
        with open(self.path, "rb") as f:
            header_data = f.read(_HEADER.size)
            magic, version, archive_type, file_count, nametable_offset = _HEADER.unpack(header_data)

            if magic != b"BTDX":
                raise ValueError(f"Not a BA2 file: bad magic {magic!r}")
            if archive_type != b"DX10":
                raise ValueError(f"Not a DX10 BA2: type is {archive_type!r}")

            # Read file entries (variable length due to chunks)
            raw_entries = []
            for _ in range(file_count):
                # Fixed 24-byte header per entry
                name_hash = struct.unpack("<I", f.read(4))[0]
                ext = f.read(4)
                dir_hash = struct.unpack("<I", f.read(4))[0]
                unknown = struct.unpack("<B", f.read(1))[0]
                num_chunks = struct.unpack("<B", f.read(1))[0]
                chunk_header_size = struct.unpack("<H", f.read(2))[0]
                height = struct.unpack("<H", f.read(2))[0]
                width = struct.unpack("<H", f.read(2))[0]
                num_mips = struct.unpack("<B", f.read(1))[0]
                dxgi_format = struct.unpack("<B", f.read(1))[0]
                tile_mode = struct.unpack("<H", f.read(2))[0]

                # Read chunk descriptors (24 bytes each)
                chunks = []
                for _ in range(num_chunks):
                    chunk_data = f.read(24)
                    c_offset = struct.unpack_from("<Q", chunk_data, 0)[0]
                    c_packed = struct.unpack_from("<I", chunk_data, 8)[0]
                    c_unpacked = struct.unpack_from("<I", chunk_data, 12)[0]
                    c_start_mip = struct.unpack_from("<H", chunk_data, 16)[0]
                    c_end_mip = struct.unpack_from("<H", chunk_data, 18)[0]
                    # bytes 20-23 are padding/sentinel
                    chunks.append(DX10Chunk(
                        offset=c_offset,
                        packed_size=c_packed,
                        unpacked_size=c_unpacked,
                        start_mip=c_start_mip,
                        end_mip=c_end_mip,
                    ))

                raw_entries.append((height, width, num_mips, dxgi_format, tile_mode, chunks))

            # Read name table
            f.seek(nametable_offset)
            for height, width, num_mips, dxgi_format, tile_mode, chunks in raw_entries:
                name_len = struct.unpack("<H", f.read(2))[0]
                name = f.read(name_len).decode("utf-8", errors="replace")
                self.entries.append(DX10FileEntry(
                    name=name.replace("\\", "/").lower(),
                    height=height,
                    width=width,
                    num_mips=num_mips,
                    dxgi_format=dxgi_format,
                    tile_mode=tile_mode,
                    chunks=chunks,
                ))

    def _build_name_index(self):
        if self._name_index is None:
            self._name_index = {e.name: e for e in self.entries}

    def find_by_path(self, path: str) -> Optional[DX10FileEntry]:
        """Find entry by exact path (case-insensitive, forward slashes)."""
        self._build_name_index()
        return self._name_index.get(path.lower().replace("\\", "/"))

    def find(self, name_fragment: str) -> Optional[DX10FileEntry]:
        """Find first entry whose name contains the fragment (case-insensitive)."""
        fragment_lower = name_fragment.lower()
        for entry in self.entries:
            if fragment_lower in entry.name:
                return entry
        return None

    def extract_chunk(self, chunk: DX10Chunk) -> bytes:
        """Extract and decompress a single chunk."""
        with open(self.path, "rb") as f:
            f.seek(chunk.offset)
            if chunk.packed_size > 0:
                compressed = f.read(chunk.packed_size)
                return zlib.decompress(compressed)
            else:
                return f.read(chunk.unpacked_size)

    def extract_all_chunks(self, entry: DX10FileEntry) -> list[bytes]:
        """Extract all chunks for a texture entry."""
        return [self.extract_chunk(c) for c in entry.chunks]

    def list_files(self) -> list[str]:
        """List all file names in the archive."""
        return [e.name for e in self.entries]
