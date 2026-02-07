"""Record and Subrecord dataclasses for ESM parsing."""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class Subrecord:
    """A single subrecord within an ESM record."""
    type: str          # 4-char type code (EDID, FULL, DATA, etc.)
    size: int          # Data size in bytes
    data: bytes        # Raw subrecord data

    def as_string(self) -> str:
        """Decode as null-terminated string."""
        return self.data.rstrip(b"\x00").decode("utf-8", errors="replace")

    def as_uint32(self) -> int:
        """Decode as unsigned 32-bit integer."""
        return struct.unpack_from("<I", self.data)[0]

    def as_int32(self) -> int:
        return struct.unpack_from("<i", self.data)[0]

    def as_float(self) -> float:
        return struct.unpack_from("<f", self.data)[0]

    def as_uint16(self) -> int:
        return struct.unpack_from("<H", self.data)[0]

    def as_formid_array(self) -> list[int]:
        """Decode as array of FormIDs (uint32)."""
        count = len(self.data) // 4
        return list(struct.unpack_from(f"<{count}I", self.data))


@dataclass(slots=True)
class Record:
    """A parsed ESM record with its subrecords."""
    type: str               # 4-char type code (WEAP, ARMO, etc.)
    data_size: int          # Size of record data
    flags: int              # Record flags
    form_id: int            # Unique form identifier
    revision: int           # Record revision
    version: int            # Record version
    subrecords: list[Subrecord] = field(default_factory=list)

    # Cached extracted fields
    _editor_id: Optional[str] = field(default=None, repr=False)
    _full_name_id: Optional[int] = field(default=None, repr=False)
    _data_hash: Optional[str] = field(default=None, repr=False)

    @property
    def is_compressed(self) -> bool:
        return bool(self.flags & 0x00040000)

    @property
    def form_id_hex(self) -> str:
        return f"0x{self.form_id:08X}"

    @property
    def editor_id(self) -> Optional[str]:
        """Get the EDID subrecord value."""
        if self._editor_id is None:
            for sub in self.subrecords:
                if sub.type == "EDID":
                    self._editor_id = sub.as_string()
                    break
        return self._editor_id

    @property
    def full_name_id(self) -> Optional[int]:
        """Get the FULL subrecord localized string ID."""
        if self._full_name_id is None:
            for sub in self.subrecords:
                if sub.type == "FULL" and sub.size == 4:
                    self._full_name_id = sub.as_uint32()
                    break
        return self._full_name_id

    @property
    def desc_id(self) -> Optional[int]:
        """Get the DESC subrecord localized string ID."""
        for sub in self.subrecords:
            if sub.type == "DESC" and sub.size == 4:
                return sub.as_uint32()
        return None

    def get_subrecord(self, sub_type: str) -> Optional[Subrecord]:
        """Get first subrecord of given type."""
        for sub in self.subrecords:
            if sub.type == sub_type:
                return sub
        return None

    def get_subrecords(self, sub_type: str) -> list[Subrecord]:
        """Get all subrecords of given type."""
        return [sub for sub in self.subrecords if sub.type == sub_type]

    def get_keywords(self) -> list[int]:
        """Get keyword FormIDs from KWDA subrecord."""
        kwda = self.get_subrecord("KWDA")
        if kwda:
            return kwda.as_formid_array()
        return []

    def data_hash(self) -> str:
        """SHA-256 hash of all subrecord data for change detection."""
        if self._data_hash is None:
            h = hashlib.sha256()
            for sub in self.subrecords:
                h.update(sub.type.encode("utf-8", errors="replace"))
                h.update(struct.pack("<H", sub.size))
                h.update(sub.data)
            self._data_hash = h.hexdigest()
        return self._data_hash
