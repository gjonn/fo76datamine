"""Export records as JSON."""
from __future__ import annotations

import json
from typing import Optional

from fo76datamine.db.resolve import FormIDResolver
from fo76datamine.db.store import Store


def export_json(store: Store, snapshot_id: int, record_type: Optional[str] = None) -> str:
    """Export records as JSON string."""
    if record_type:
        records = store.get_records_by_type(snapshot_id, record_type)
    else:
        cur = store.conn.execute(
            "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
            "desc_text, desc_id, data_hash, flags, data_size "
            "FROM records WHERE snapshot_id=? ORDER BY record_type, form_id",
            (snapshot_id,),
        )
        from fo76datamine.db.models import DbRecord
        records = [DbRecord(*row) for row in cur.fetchall()]

    resolver = FormIDResolver(store, snapshot_id)

    data = []
    for rec in records:
        entry = {
            "form_id": f"0x{rec.form_id:08X}",
            "record_type": rec.record_type,
            "editor_id": rec.editor_id,
            "full_name": rec.full_name,
            "flags": f"0x{rec.flags:08X}",
            "data_size": rec.data_size,
        }

        # Include decoded fields
        fields = store.get_decoded_fields(snapshot_id, rec.form_id)
        if fields:
            entry["fields"] = {
                f.field_name: resolver.format_field_value(f)
                for f in fields
            }

        data.append(entry)

    return json.dumps(data, indent=2)
