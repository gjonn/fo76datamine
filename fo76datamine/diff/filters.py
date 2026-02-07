"""Unreleased content detection heuristics."""
from __future__ import annotations

from fo76datamine.db.models import DbRecord
from fo76datamine.db.store import Store
from fo76datamine.esm.constants import UNRELEASED_PREFIXES


def find_unreleased(store: Store, snapshot_id: int) -> dict[str, list[DbRecord]]:
    """Scan a snapshot for unreleased content using multiple heuristics."""
    results: dict[str, list[DbRecord]] = {
        "Atomic Shop (ATX_)": [],
        "Cut/Test Content": [],
        "High FormIDs (likely new)": [],
        "Disabled Quests": [],
    }

    # ATX_ prefix items (Atomic Shop, often added before going live)
    cur = store.conn.execute(
        "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
        "desc_text, desc_id, data_hash, flags, data_size "
        "FROM records WHERE snapshot_id=? AND editor_id LIKE 'ATX_%' "
        "ORDER BY form_id DESC",
        (snapshot_id,),
    )
    results["Atomic Shop (ATX_)"] = [DbRecord(*row) for row in cur.fetchall()]

    # Cut/test content
    patterns = ["zzz_%", "CUT_%", "TEST_%", "test_%", "DEBUG_%", "DVLP_%"]
    for pattern in patterns:
        cur = store.conn.execute(
            "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
            "desc_text, desc_id, data_hash, flags, data_size "
            "FROM records WHERE snapshot_id=? AND editor_id LIKE ? "
            "ORDER BY form_id",
            (snapshot_id, pattern),
        )
        results["Cut/Test Content"].extend(DbRecord(*row) for row in cur.fetchall())

    # High FormIDs (top 0.1% - often newly added content)
    cur = store.conn.execute(
        "SELECT MAX(form_id) FROM records WHERE snapshot_id=?",
        (snapshot_id,),
    )
    max_fid = cur.fetchone()[0]
    if max_fid:
        threshold = int(max_fid * 0.995)  # Top 0.5%
        cur = store.conn.execute(
            "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
            "desc_text, desc_id, data_hash, flags, data_size "
            "FROM records WHERE snapshot_id=? AND form_id > ? "
            "AND record_type IN ('WEAP', 'ARMO', 'ALCH', 'MISC', 'NPC_', 'QUST', 'BOOK', 'COBJ', 'OMOD') "
            "ORDER BY form_id DESC",
            (snapshot_id, threshold),
        )
        results["High FormIDs (likely new)"] = [DbRecord(*row) for row in cur.fetchall()]

    # Quests with start-disabled flag (flag 0x0800 = initially disabled)
    cur = store.conn.execute(
        "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
        "desc_text, desc_id, data_hash, flags, data_size "
        "FROM records WHERE snapshot_id=? AND record_type='QUST' "
        "AND editor_id LIKE 'ATX_%' "
        "ORDER BY form_id DESC",
        (snapshot_id,),
    )
    results["Disabled Quests"] = [DbRecord(*row) for row in cur.fetchall()]

    return results
