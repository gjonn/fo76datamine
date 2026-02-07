"""Display-time FormID name resolution.

Resolves opaque hex FormID strings (e.g. ``0x003AB2C1``) to human-readable
names by looking up the record's full_name or editor_id in the database.

Important: resolution happens at *display* time, not storage time, so that
the diff engine can still compare raw field_value strings across snapshots.
"""
from __future__ import annotations

from typing import Optional

from fo76datamine.db.models import DecodedField


class FormIDResolver:
    """Lazy-loading FormID → display name resolver."""

    def __init__(self, store, snapshot_id: int):
        self._store = store
        self._snapshot_id = snapshot_id
        self._cache: Optional[dict[int, str]] = None

    def _load(self):
        """Bulk-load all form_id → name mappings (single SQL query)."""
        cur = self._store.conn.execute(
            "SELECT form_id, full_name, editor_id FROM records WHERE snapshot_id=?",
            (self._snapshot_id,),
        )
        self._cache = {}
        for form_id, full_name, editor_id in cur:
            name = full_name or editor_id
            if name:
                self._cache[form_id] = name

    def resolve_name(self, hex_str: str) -> Optional[str]:
        """Parse a '0x003AB2C1' string and return the record name, or None."""
        if self._cache is None:
            self._load()
        try:
            form_id = int(hex_str, 16)
        except (ValueError, TypeError):
            return None
        return self._cache.get(form_id)

    def format_field_value(self, field: DecodedField) -> str:
        """Return display string: appends ' (Name)' for formid-typed fields."""
        if field.field_type == "formid":
            name = self.resolve_name(field.field_value)
            if name:
                return f"{field.field_value} ({name})"
        return field.field_value

    def format_value(self, value: str, field_type: str) -> str:
        """Format a raw value string given its field_type."""
        if field_type == "formid":
            name = self.resolve_name(value)
            if name:
                return f"{value} ({name})"
        return value
