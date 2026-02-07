"""Parse .strings / .dlstrings / .ilstrings files from Localization BA2.

String table format (Bethesda):
  .strings:   Header: count(uint32) + datasize(uint32), then count entries of (id:uint32, offset:uint32).
              Data section: null-terminated strings at given offsets from data start.
  .dlstrings: Same header, but data section strings are length-prefixed (uint32 len + bytes, NOT null-terminated).
  .ilstrings: Same as .dlstrings.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional

from fo76datamine.ba2.reader import BA2Reader


def _parse_strings(data: bytes) -> dict[int, str]:
    """Parse a .strings file (null-terminated strings in data section)."""
    if len(data) < 8:
        return {}

    count, data_size = struct.unpack_from("<II", data, 0)
    entries = {}
    header_size = 8 + count * 8  # 8-byte file header + count * (id + offset) entries
    data_len = len(data)

    # Batch-unpack all directory entries at once
    dir_fmt = struct.Struct(f"<{count * 2}I")
    dir_values = dir_fmt.unpack_from(data, 8)

    for i in range(count):
        string_id = dir_values[i * 2]
        string_offset = dir_values[i * 2 + 1]

        str_start = header_size + string_offset
        if str_start >= data_len:
            continue

        # Find null terminator
        end = data.find(b"\x00", str_start)
        if end == -1:
            end = data_len
        entries[string_id] = data[str_start:end].decode("utf-8", errors="replace")

    return entries


def _parse_dlstrings(data: bytes) -> dict[int, str]:
    """Parse a .dlstrings or .ilstrings file (length-prefixed strings)."""
    if len(data) < 8:
        return {}

    count, data_size = struct.unpack_from("<II", data, 0)
    entries = {}
    header_size = 8 + count * 8
    data_len = len(data)

    # Batch-unpack all directory entries at once
    dir_fmt = struct.Struct(f"<{count * 2}I")
    dir_values = dir_fmt.unpack_from(data, 8)

    for i in range(count):
        string_id = dir_values[i * 2]
        string_offset = dir_values[i * 2 + 1]

        str_start = header_size + string_offset
        if str_start + 4 > data_len:
            continue

        str_len = struct.unpack_from("<I", data, str_start)[0]
        str_data = data[str_start + 4:str_start + 4 + str_len]
        text = str_data.rstrip(b"\x00").decode("utf-8", errors="replace")
        entries[string_id] = text

    return entries


class StringTable:
    """Merged lookup table for all localized strings."""

    def __init__(self):
        self.strings: dict[int, str] = {}
        self._source_counts: dict[str, int] = {}

    def load_from_ba2(self, ba2_path: Path, language: str = "en") -> None:
        """Load all string files for a language from the Localization BA2."""
        reader = BA2Reader(ba2_path)

        # Find string files for the given language
        prefix = f"strings/seventysix_{language}"
        for suffix, parser in [
            (".strings", _parse_strings),
            (".dlstrings", _parse_dlstrings),
            (".ilstrings", _parse_dlstrings),
        ]:
            entry = reader.find(prefix + suffix)
            if entry is None:
                continue

            raw = reader.extract_file(entry)
            parsed = parser(raw)
            self._source_counts[entry.name] = len(parsed)
            self.strings.update(parsed)

        # Also load NW strings if available
        nw_prefix = f"strings/nw_{language}"
        for suffix, parser in [
            (".strings", _parse_strings),
            (".dlstrings", _parse_dlstrings),
            (".ilstrings", _parse_dlstrings),
        ]:
            entry = reader.find(nw_prefix + suffix)
            if entry is None:
                continue

            raw = reader.extract_file(entry)
            parsed = parser(raw)
            self._source_counts[entry.name] = len(parsed)
            self.strings.update(parsed)

    def lookup(self, string_id: int) -> Optional[str]:
        """Look up a string by its ID."""
        return self.strings.get(string_id)

    def search(self, query: str) -> list[tuple[int, str]]:
        """Search strings by substring (case-insensitive)."""
        query_lower = query.lower()
        return [
            (sid, text) for sid, text in self.strings.items()
            if query_lower in text.lower()
        ]

    @property
    def count(self) -> int:
        return len(self.strings)


def main():
    """Test: load strings and look up known items."""
    import sys
    import time
    if len(sys.argv) < 2:
        print("Usage: python -m fo76datamine.strings.loader <path/to/Localization.ba2>")
        sys.exit(1)

    path = Path(sys.argv[1])
    table = StringTable()

    start = time.perf_counter()
    table.load_from_ba2(path)
    elapsed = time.perf_counter() - start

    print(f"Loaded {table.count:,} strings in {elapsed:.2f}s\n")
    for name, count in table._source_counts.items():
        print(f"  {name}: {count:,} strings")

    # Search for known items
    print("\nSearching for known items:")
    for query in ["10mm Pistol", "Stimpak", "Nuka-Cola", "Power Armor"]:
        results = table.search(query)
        print(f"\n  '{query}': {len(results)} matches")
        for sid, text in results[:5]:
            print(f"    0x{sid:08X}: {text[:80]}")


if __name__ == "__main__":
    main()
