"""BA2 (BTDX v1 GNRL) archive reader for Fallout 76."""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_HEADER = struct.Struct("<4sI4sIQ")   # magic(4) + version(4) + type(4) + filecount(4) + nametable_offset(8)
_GNRL_ENTRY = struct.Struct("<I4sIIQII4s")  # namehash(4) + ext(4) + dirhash(4) + unk(4) + offset(8) + packed(4) + unpacked(4) + sentinel(4)


@dataclass(slots=True)
class BA2FileEntry:
    """A file entry in a BA2 archive."""
    name: str
    offset: int
    packed_size: int
    unpacked_size: int


class BA2Reader:
    """Reader for Bethesda Archive 2 (BA2) GNRL format."""

    def __init__(self, path: Path):
        self.path = path
        self.entries: list[BA2FileEntry] = []
        self._parse_header()

    def _parse_header(self):
        with open(self.path, "rb") as f:
            header_data = f.read(_HEADER.size)
            magic, version, archive_type, file_count, nametable_offset = _HEADER.unpack(header_data)

            if magic != b"BTDX":
                raise ValueError(f"Not a BA2 file: bad magic {magic!r}")
            if archive_type != b"GNRL":
                raise ValueError(f"Unsupported BA2 type: {archive_type!r} (only GNRL supported)")

            # Read file entries
            raw_entries = []
            for _ in range(file_count):
                entry_data = f.read(_GNRL_ENTRY.size)
                namehash, ext, dirhash, unk, offset, packed, unpacked, sentinel = \
                    _GNRL_ENTRY.unpack(entry_data)
                raw_entries.append((offset, packed, unpacked))

            # Read name table
            f.seek(nametable_offset)
            for offset, packed, unpacked in raw_entries:
                name_len = struct.unpack("<H", f.read(2))[0]
                name = f.read(name_len).decode("utf-8", errors="replace")
                self.entries.append(BA2FileEntry(
                    name=name.replace("\\", "/"),
                    offset=offset,
                    packed_size=packed,
                    unpacked_size=unpacked,
                ))

    def extract_file(self, entry: BA2FileEntry) -> bytes:
        """Extract a single file from the archive."""
        with open(self.path, "rb") as f:
            f.seek(entry.offset)
            if entry.packed_size > 0:
                compressed = f.read(entry.packed_size)
                return zlib.decompress(compressed)
            else:
                return f.read(entry.unpacked_size)

    def find(self, name_fragment: str) -> Optional[BA2FileEntry]:
        """Find first entry whose name contains the fragment (case-insensitive)."""
        fragment_lower = name_fragment.lower()
        for entry in self.entries:
            if fragment_lower in entry.name.lower():
                return entry
        return None

    def find_all(self, name_fragment: str) -> list[BA2FileEntry]:
        """Find all entries matching a name fragment."""
        fragment_lower = name_fragment.lower()
        return [e for e in self.entries if fragment_lower in e.name.lower()]

    def list_files(self) -> list[str]:
        """List all file names in the archive."""
        return [e.name for e in self.entries]


def main():
    """Test: list files in a BA2 archive."""
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m fo76datamine.ba2.reader <path/to/file.ba2>")
        sys.exit(1)

    path = Path(sys.argv[1])
    print(f"Reading {path.name}...")
    reader = BA2Reader(path)
    print(f"Found {len(reader.entries)} files:\n")
    for entry in reader.entries:
        size_kb = entry.unpacked_size / 1024
        print(f"  {entry.name} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
