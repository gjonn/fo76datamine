"""Export records as CSV."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fo76datamine.db.store import Store


def export_csv(store: Store, snapshot_id: int, record_type: Optional[str] = None) -> str:
    """Export records as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "form_id", "record_type", "editor_id", "full_name",
        "description", "flags", "data_size", "data_hash",
    ])

    if record_type:
        records = store.get_records_by_type(snapshot_id, record_type)
    else:
        # All records
        cur = store.conn.execute(
            "SELECT form_id, record_type, editor_id, full_name, desc_text, flags, data_size, data_hash "
            "FROM records WHERE snapshot_id=? ORDER BY record_type, form_id",
            (snapshot_id,),
        )
        records = cur.fetchall()
        # Write raw tuples
        for row in records:
            fid = f"0x{row[0]:08X}"
            writer.writerow([fid, *row[1:]])
        return output.getvalue()

    for rec in records:
        writer.writerow([
            rec.form_id_hex,
            rec.record_type,
            rec.editor_id or "",
            rec.full_name or "",
            (rec.desc_text or "")[:200],
            f"0x{rec.flags:08X}",
            rec.data_size,
            rec.data_hash,
        ])

    return output.getvalue()
