"""Dataclasses for database records, snapshots, and diffs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Snapshot:
    id: int
    label: str
    created_at: str
    esm_hash: str
    esm_size: int
    record_count: int
    string_count: int
    has_subrecords: bool = False

    @property
    def created_datetime(self) -> datetime:
        return datetime.fromisoformat(self.created_at)


@dataclass
class DbRecord:
    """A record stored in the database."""
    snapshot_id: int
    form_id: int
    record_type: str
    editor_id: Optional[str]
    full_name: Optional[str]
    full_name_id: Optional[int]
    desc_text: Optional[str]
    desc_id: Optional[int]
    data_hash: str
    flags: int
    data_size: int

    @property
    def form_id_hex(self) -> str:
        return f"0x{self.form_id:08X}"


@dataclass
class DecodedField:
    """A decoded named field value."""
    snapshot_id: int
    form_id: int
    field_name: str
    field_value: str
    field_type: str  # 'float', 'int', 'str', 'formid', 'flags'


@dataclass
class DbString:
    """A localized string stored in the database."""
    snapshot_id: int
    string_id: int
    text: str
    source: str  # 'strings', 'dlstrings', 'ilstrings'


@dataclass
class DiffResult:
    """Result of comparing two snapshots."""
    old_snapshot_id: int
    new_snapshot_id: int
    added: list[DbRecord] = field(default_factory=list)
    removed: list[DbRecord] = field(default_factory=list)
    modified: list[tuple[DbRecord, DbRecord]] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)


@dataclass
class FieldChange:
    """A single field-level change between two record versions."""
    form_id: int
    field_name: str
    old_value: Optional[str]
    new_value: Optional[str]
