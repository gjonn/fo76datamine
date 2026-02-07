"""Compare snapshots via data_hash, with field-level diffing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fo76datamine.db.models import DbRecord, FieldChange
from fo76datamine.db.store import Store


@dataclass
class DiffResult:
    old_snapshot_id: int
    new_snapshot_id: int
    added: list[DbRecord] = field(default_factory=list)
    removed: list[DbRecord] = field(default_factory=list)
    modified: list[tuple[DbRecord, DbRecord]] = field(default_factory=list)
    field_changes: dict[int, list[FieldChange]] = field(default_factory=dict)

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)


class DiffEngine:
    """Compare two snapshots to find added, removed, and modified records."""

    def __init__(self, store: Store, new_store: Optional[Store] = None):
        self.store = store
        self.new_store = new_store or store

    def compare(self, old_id: int, new_id: int,
                record_type: Optional[str] = None) -> DiffResult:
        """Compare two snapshots by data_hash."""
        result = DiffResult(old_snapshot_id=old_id, new_snapshot_id=new_id)

        # Get all hashes for both snapshots
        old_hashes = self.store.get_record_hashes(old_id)
        new_hashes = self.new_store.get_record_hashes(new_id)

        old_ids = set(old_hashes.keys())
        new_ids = set(new_hashes.keys())

        # Added records
        for fid in sorted(new_ids - old_ids):
            rec = self.new_store.get_record(new_id, fid)
            if rec and (record_type is None or rec.record_type == record_type):
                result.added.append(rec)

        # Removed records
        for fid in sorted(old_ids - new_ids):
            rec = self.store.get_record(old_id, fid)
            if rec and (record_type is None or rec.record_type == record_type):
                result.removed.append(rec)

        # Modified records (same form_id, different hash)
        for fid in sorted(old_ids & new_ids):
            if old_hashes[fid] != new_hashes[fid]:
                old_rec = self.store.get_record(old_id, fid)
                new_rec = self.new_store.get_record(new_id, fid)
                if old_rec and new_rec and (record_type is None or old_rec.record_type == record_type):
                    result.modified.append((old_rec, new_rec))

                    # Field-level diff
                    changes = self._diff_fields(old_id, new_id, fid)
                    if changes:
                        result.field_changes[fid] = changes

        return result

    def _diff_fields(self, old_id: int, new_id: int, form_id: int) -> list[FieldChange]:
        """Compare decoded fields between two versions of a record."""
        old_fields = {f.field_name: (f.field_value, f.field_type)
                      for f in self.store.get_decoded_fields(old_id, form_id)}
        new_fields = {f.field_name: (f.field_value, f.field_type)
                      for f in self.new_store.get_decoded_fields(new_id, form_id)}

        changes = []
        all_names = sorted(set(old_fields.keys()) | set(new_fields.keys()))
        for name in all_names:
            old_val, old_type = old_fields.get(name, (None, "str"))
            new_val, new_type = new_fields.get(name, (None, "str"))
            if old_val != new_val:
                # Prefer the new field_type; fall back to old
                ft = new_type if new_val is not None else old_type
                changes.append(FieldChange(
                    form_id=form_id,
                    field_name=name,
                    old_value=old_val,
                    new_value=new_val,
                    field_type=ft,
                ))

        return changes
