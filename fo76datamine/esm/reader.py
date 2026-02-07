"""Low-level ESM binary parser for Fallout 76 SeventySix.esm (format v208)."""
from __future__ import annotations

import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional

from fo76datamine.esm.constants import SKIP_TYPES, FLAG_COMPRESSED
from fo76datamine.esm.records import Record, Subrecord


# Struct formats (little-endian)
_HEADER_FMT = struct.Struct("<4sIIIIHH")   # type(4) + size(4) + flags(4) + formid(4) + rev(4) + ver(2) + pad(2)
_GRUP_FMT = struct.Struct("<4sI4sIII")     # 'GRUP'(4) + size(4) + label(4) + grouptype(4) + ts(4) + pad(4)
_SUB_HEADER = struct.Struct("<4sH")         # type(4) + size(2)
_UINT32 = struct.Struct("<I")


class ESMReader:
    """Parser for Fallout 76 ESM files (format version 208).

    Iterates all records except placement refs (REFR/NAVM/ACHR),
    yielding Record objects with parsed subrecords.
    """

    def __init__(self, path: Path, skip_types: Optional[set[bytes]] = None):
        self.path = path
        self.skip_types = skip_types if skip_types is not None else SKIP_TYPES
        self._file_size = path.stat().st_size

    def parse_all(self) -> list[Record]:
        """Parse all records into a list. ~7-8s for full ESM."""
        return list(self.iter_records())

    def iter_records(self) -> Iterator[Record]:
        """Iterate over all datamineable records in the ESM file."""
        with open(self.path, "rb") as f:
            data = f.read()

        file_size = len(data)
        pos = 0

        # Parse TES4 header record (skip it, just advance past)
        if data[pos:pos+4] != b"TES4":
            raise ValueError(f"Not a valid ESM file: expected TES4 at offset 0")
        tes4_size = _HEADER_FMT.unpack_from(data, pos)[1]
        pos += 24 + tes4_size  # Skip TES4 header + data

        # Now iterate top-level GRUPs
        while pos < file_size:
            if pos + 24 > file_size:
                break

            tag = data[pos:pos+4]
            if tag != b"GRUP":
                break

            _, group_size, label, group_type, _, _ = _GRUP_FMT.unpack_from(data, pos)
            group_end = pos + group_size

            if group_type == 0 and label in self.skip_types:
                # Skip entire top-level group for unwanted types
                pos = group_end
                continue

            # Parse records within this group
            pos += 24  # Skip GRUP header
            yield from self._parse_group_contents(data, pos, group_end)
            pos = group_end

    def _parse_group_contents(self, data: bytes, pos: int, end: int) -> Iterator[Record]:
        """Parse records within a group, recursing into sub-groups."""
        while pos < end:
            if pos + 4 > end:
                break

            tag = data[pos:pos+4]

            if tag == b"GRUP":
                # Sub-group
                if pos + 24 > end:
                    break
                _, group_size, label, group_type, _, _ = _GRUP_FMT.unpack_from(data, pos)
                sub_end = pos + group_size

                # Skip sub-groups that only contain placement refs
                if group_type in (8, 9):  # CELL persistent/temporary children
                    # These contain REFR/ACHR - peek to see if we should skip
                    pos = sub_end
                    continue

                pos += 24
                yield from self._parse_group_contents(data, pos, sub_end)
                pos = sub_end
                continue

            # It's a record
            if pos + 24 > end:
                break

            rec_type_bytes, data_size, flags, form_id, revision, version, _ = \
                _HEADER_FMT.unpack_from(data, pos)
            pos += 24

            rec_type = rec_type_bytes.rstrip(b"\x00")

            # Skip unwanted record types
            if rec_type in self.skip_types:
                pos += data_size
                continue

            rec_type_str = rec_type.decode("ascii", errors="replace")

            # Read record data
            if pos + data_size > end:
                break

            raw_data = data[pos:pos + data_size]
            pos += data_size

            # Decompress if needed
            if flags & FLAG_COMPRESSED:
                if len(raw_data) < 4:
                    continue
                decomp_size = _UINT32.unpack_from(raw_data)[0]
                try:
                    raw_data = zlib.decompress(raw_data[4:])
                except zlib.error:
                    continue

            # Parse subrecords
            subrecords = self._parse_subrecords(raw_data)

            yield Record(
                type=rec_type_str,
                data_size=data_size,
                flags=flags,
                form_id=form_id,
                revision=revision,
                version=version,
                subrecords=subrecords,
            )

    def _parse_subrecords(self, data: bytes) -> list[Subrecord]:
        """Parse all subrecords from record data."""
        subrecords = []
        offset = 0
        data_len = len(data)

        while offset + 6 <= data_len:
            sub_type_bytes, sub_size = _SUB_HEADER.unpack_from(data, offset)
            offset += 6

            if offset + sub_size > data_len:
                break

            sub_data = data[offset:offset + sub_size]
            offset += sub_size

            sub_type = sub_type_bytes.decode("ascii", errors="replace")
            subrecords.append(Subrecord(type=sub_type, size=sub_size, data=sub_data))

        return subrecords


def main():
    """Quick test: parse ESM and print record type counts."""
    import sys
    import time
    if len(sys.argv) < 2:
        print("Usage: python -m fo76datamine.esm.reader <path/to/SeventySix.esm>")
        sys.exit(1)

    path = Path(sys.argv[1])
    print(f"Parsing {path} ({path.stat().st_size / 1024 / 1024:.0f} MB)...")

    reader = ESMReader(path)
    start = time.perf_counter()
    records = reader.parse_all()
    elapsed = time.perf_counter() - start

    print(f"\nParsed {len(records):,} records in {elapsed:.1f}s\n")

    # Count by type
    type_counts = Counter(r.type for r in records)
    print(f"{'Type':<8} {'Count':>8}")
    print("-" * 18)
    for rtype, count in type_counts.most_common(30):
        print(f"{rtype:<8} {count:>8,}")

    # Count subrecords
    total_subs = sum(len(r.subrecords) for r in records)
    print(f"\nTotal subrecords: {total_subs:,}")

    # Show some example records
    print("\nSample EDID values:")
    shown = 0
    for r in records:
        if r.editor_id and shown < 10:
            print(f"  {r.type} {r.form_id_hex}: {r.editor_id}")
            shown += 1


if __name__ == "__main__":
    main()
