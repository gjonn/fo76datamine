"""Snapshot CRUD and batch insert operations with WAL mode."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from fo76datamine.db.models import DbRecord, DecodedField, Snapshot
from fo76datamine.db.schema import init_db


class Store:
    """Database access layer for the datamining database."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        init_db(self.conn)

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # -- Snapshots --

    def create_snapshot(self, label: str, esm_path: Path) -> int:
        """Create a new snapshot and return its ID."""
        esm_size = esm_path.stat().st_size
        # Hash first 1MB for quick identification
        with open(esm_path, "rb") as f:
            esm_hash = hashlib.sha256(f.read(1024 * 1024)).hexdigest()

        cur = self.conn.execute(
            "INSERT INTO snapshots (label, esm_hash, esm_size) VALUES (?, ?, ?)",
            (label, esm_hash, esm_size),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_snapshot_counts(self, snapshot_id: int, record_count: int,
                                string_count: int, has_subrecords: bool = False):
        self.conn.execute(
            "UPDATE snapshots SET record_count=?, string_count=?, has_subrecords=? WHERE id=?",
            (record_count, string_count, int(has_subrecords), snapshot_id),
        )
        self.conn.commit()

    def get_snapshot(self, snapshot_id: int) -> Optional[Snapshot]:
        cur = self.conn.execute(
            "SELECT id, label, created_at, esm_hash, esm_size, record_count, string_count, has_subrecords "
            "FROM snapshots WHERE id=?", (snapshot_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return Snapshot(*row)

    def get_latest_snapshot(self) -> Optional[Snapshot]:
        cur = self.conn.execute(
            "SELECT id, label, created_at, esm_hash, esm_size, record_count, string_count, has_subrecords "
            "FROM snapshots ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row is None:
            return None
        return Snapshot(*row)

    def get_two_latest_snapshots(self) -> tuple[Optional[Snapshot], Optional[Snapshot]]:
        """Return (older, newer) or (None, None) if fewer than 2 exist."""
        cur = self.conn.execute(
            "SELECT id, label, created_at, esm_hash, esm_size, record_count, string_count, has_subrecords "
            "FROM snapshots ORDER BY id DESC LIMIT 2")
        rows = cur.fetchall()
        if len(rows) < 2:
            return None, None
        newer = Snapshot(*rows[0])
        older = Snapshot(*rows[1])
        return older, newer

    def list_snapshots(self) -> list[Snapshot]:
        cur = self.conn.execute(
            "SELECT id, label, created_at, esm_hash, esm_size, record_count, string_count, has_subrecords "
            "FROM snapshots ORDER BY id")
        return [Snapshot(*row) for row in cur.fetchall()]

    def delete_snapshot(self, snapshot_id: int):
        self.conn.execute("DELETE FROM snapshots WHERE id=?", (snapshot_id,))
        self.conn.commit()

    # -- Batch inserts --

    def insert_records(self, snapshot_id: int, records: list[tuple]):
        """Batch insert records. Each tuple: (form_id, type, editor_id, full_name, full_name_id, desc, desc_id, hash, flags, size)."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO records "
            "(snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
            "desc_text, desc_id, data_hash, flags, data_size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(snapshot_id, *r) for r in records],
        )
        self.conn.commit()

    def insert_decoded_fields(self, snapshot_id: int, fields: list[tuple]):
        """Batch insert decoded fields. Each tuple: (form_id, field_name, field_value, field_type)."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO decoded_fields "
            "(snapshot_id, form_id, field_name, field_value, field_type) "
            "VALUES (?, ?, ?, ?, ?)",
            [(snapshot_id, *f) for f in fields],
        )
        self.conn.commit()

    def insert_strings(self, snapshot_id: int, strings: list[tuple]):
        """Batch insert strings. Each tuple: (string_id, text, source)."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO strings (snapshot_id, string_id, text, source) "
            "VALUES (?, ?, ?, ?)",
            [(snapshot_id, *s) for s in strings],
        )
        self.conn.commit()

    def insert_keywords(self, snapshot_id: int, keywords: list[tuple]):
        """Batch insert keywords. Each tuple: (form_id, editor_id)."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO keywords (snapshot_id, form_id, editor_id) VALUES (?, ?, ?)",
            [(snapshot_id, *k) for k in keywords],
        )
        self.conn.commit()

    def insert_subrecords(self, snapshot_id: int, subrecords: list[tuple]):
        """Batch insert raw subrecords. Each tuple: (form_id, sub_type, sub_index, data)."""
        self.conn.executemany(
            "INSERT INTO subrecords (snapshot_id, form_id, sub_type, sub_index, data) "
            "VALUES (?, ?, ?, ?, ?)",
            [(snapshot_id, *s) for s in subrecords],
        )
        self.conn.commit()

    # -- Queries --

    def get_records_by_type(self, snapshot_id: int, record_type: str) -> list[DbRecord]:
        cur = self.conn.execute(
            "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
            "desc_text, desc_id, data_hash, flags, data_size "
            "FROM records WHERE snapshot_id=? AND record_type=? ORDER BY form_id",
            (snapshot_id, record_type),
        )
        return [DbRecord(*row) for row in cur.fetchall()]

    def get_record(self, snapshot_id: int, form_id: int) -> Optional[DbRecord]:
        cur = self.conn.execute(
            "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
            "desc_text, desc_id, data_hash, flags, data_size "
            "FROM records WHERE snapshot_id=? AND form_id=?",
            (snapshot_id, form_id),
        )
        row = cur.fetchone()
        return DbRecord(*row) if row else None

    def search_records(self, snapshot_id: int, query: str,
                       record_type: Optional[str] = None,
                       edid_pattern: Optional[str] = None) -> list[DbRecord]:
        """Search records by name, editor ID, or FormID."""
        conditions = ["snapshot_id = ?"]
        params: list = [snapshot_id]

        if record_type:
            conditions.append("record_type = ?")
            params.append(record_type)

        if edid_pattern:
            # Convert glob to SQL LIKE
            like_pattern = edid_pattern.replace("*", "%").replace("?", "_")
            conditions.append("editor_id LIKE ?")
            params.append(like_pattern)

        if query:
            # Search name, editor_id, or FormID
            try:
                form_id = int(query, 16) if query.startswith("0x") else int(query, 0)
                conditions.append("(full_name LIKE ? OR editor_id LIKE ? OR form_id = ?)")
                params.extend([f"%{query}%", f"%{query}%", form_id])
            except ValueError:
                conditions.append("(full_name LIKE ? OR editor_id LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])

        where = " AND ".join(conditions)
        cur = self.conn.execute(
            f"SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
            f"desc_text, desc_id, data_hash, flags, data_size "
            f"FROM records WHERE {where} ORDER BY record_type, form_id LIMIT 500",
            params,
        )
        return [DbRecord(*row) for row in cur.fetchall()]

    def get_icon_paths(self, snapshot_id: int, form_ids: list[int]) -> dict[int, str]:
        """Batch-fetch icon texture paths for given form_ids."""
        if not form_ids:
            return {}
        result = {}
        # Query in batches to avoid SQLite variable limits
        batch_size = 500
        for i in range(0, len(form_ids), batch_size):
            batch = form_ids[i:i + batch_size]
            placeholders = ",".join("?" * len(batch))
            cur = self.conn.execute(
                f"SELECT form_id, field_value FROM decoded_fields "
                f"WHERE snapshot_id=? AND field_name='icon' AND form_id IN ({placeholders})",
                [snapshot_id, *batch],
            )
            for row in cur:
                result[row[0]] = row[1]
        return result

    def get_model_paths(self, snapshot_id: int, form_ids: list[int]) -> dict[int, str]:
        """Batch-fetch model (.nif) paths for given form_ids."""
        if not form_ids:
            return {}
        result = {}
        batch_size = 500
        for i in range(0, len(form_ids), batch_size):
            batch = form_ids[i:i + batch_size]
            placeholders = ",".join("?" * len(batch))
            cur = self.conn.execute(
                f"SELECT form_id, field_value FROM decoded_fields "
                f"WHERE snapshot_id=? AND field_name='model' AND form_id IN ({placeholders})",
                [snapshot_id, *batch],
            )
            for row in cur:
                result[row[0]] = row[1]
        return result

    def get_decoded_fields(self, snapshot_id: int, form_id: int) -> list[DecodedField]:
        cur = self.conn.execute(
            "SELECT snapshot_id, form_id, field_name, field_value, field_type "
            "FROM decoded_fields WHERE snapshot_id=? AND form_id=?",
            (snapshot_id, form_id),
        )
        return [DecodedField(*row) for row in cur.fetchall()]

    def get_record_hashes(self, snapshot_id: int) -> dict[int, str]:
        """Get all form_id -> data_hash pairs for a snapshot (for diffing)."""
        cur = self.conn.execute(
            "SELECT form_id, data_hash FROM records WHERE snapshot_id=?",
            (snapshot_id,),
        )
        return dict(cur.fetchall())

    def get_record_type_counts(self, snapshot_id: int) -> list[tuple[str, int]]:
        cur = self.conn.execute(
            "SELECT record_type, COUNT(*) FROM records WHERE snapshot_id=? "
            "GROUP BY record_type ORDER BY COUNT(*) DESC",
            (snapshot_id,),
        )
        return cur.fetchall()

    def get_string(self, snapshot_id: int, string_id: int) -> Optional[str]:
        cur = self.conn.execute(
            "SELECT text FROM strings WHERE snapshot_id=? AND string_id=?",
            (snapshot_id, string_id),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def search_strings(self, snapshot_id: int, query: str) -> list[tuple[int, str]]:
        cur = self.conn.execute(
            "SELECT string_id, text FROM strings WHERE snapshot_id=? AND text LIKE ? LIMIT 200",
            (snapshot_id, f"%{query}%"),
        )
        return cur.fetchall()

    def get_db_size(self) -> int:
        """Get database file size in bytes."""
        return self.db_path.stat().st_size if self.db_path.exists() else 0

    # -- Diff storage --

    def save_diff(self, old_id: int, new_id: int,
                  added: list[tuple], removed: list[tuple], modified: list[tuple]) -> int:
        """Save diff results. Returns diff ID."""
        cur = self.conn.execute(
            "INSERT INTO diffs (old_snapshot_id, new_snapshot_id, added_count, removed_count, modified_count) "
            "VALUES (?, ?, ?, ?, ?)",
            (old_id, new_id, len(added), len(removed), len(modified)),
        )
        diff_id = cur.lastrowid

        # Insert entries
        all_entries = []
        for form_id, rec_type, edid, name, new_hash in added:
            all_entries.append((diff_id, form_id, "added", rec_type, edid, name, None, new_hash))
        for form_id, rec_type, edid, name, old_hash in removed:
            all_entries.append((diff_id, form_id, "removed", rec_type, edid, name, old_hash, None))
        for form_id, rec_type, edid, name, old_hash, new_hash in modified:
            all_entries.append((diff_id, form_id, "modified", rec_type, edid, name, old_hash, new_hash))

        self.conn.executemany(
            "INSERT INTO diff_entries "
            "(diff_id, form_id, change_type, record_type, editor_id, full_name, old_hash, new_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            all_entries,
        )
        self.conn.commit()
        return diff_id

    def purge_old_snapshots(self, keep: int):
        """Delete all but the N most recent snapshots."""
        cur = self.conn.execute(
            "SELECT id FROM snapshots ORDER BY id DESC LIMIT -1 OFFSET ?",
            (keep,),
        )
        old_ids = [row[0] for row in cur.fetchall()]
        if old_ids:
            placeholders = ",".join("?" * len(old_ids))
            self.conn.execute(f"DELETE FROM snapshots WHERE id IN ({placeholders})", old_ids)
            self.conn.execute(f"DELETE FROM records WHERE snapshot_id IN ({placeholders})", old_ids)
            self.conn.execute(f"DELETE FROM decoded_fields WHERE snapshot_id IN ({placeholders})", old_ids)
            self.conn.execute(f"DELETE FROM strings WHERE snapshot_id IN ({placeholders})", old_ids)
            self.conn.execute(f"DELETE FROM keywords WHERE snapshot_id IN ({placeholders})", old_ids)
            self.conn.execute(f"DELETE FROM subrecords WHERE snapshot_id IN ({placeholders})", old_ids)
            self.conn.commit()
            self.conn.execute("VACUUM")
        return len(old_ids)

    def clear_all_snapshots(self):
        """Delete every snapshot and all related data."""
        count = self.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        if count:
            self.conn.execute("DELETE FROM diff_entries")
            self.conn.execute("DELETE FROM diffs")
            self.conn.execute("DELETE FROM decoded_fields")
            self.conn.execute("DELETE FROM strings")
            self.conn.execute("DELETE FROM keywords")
            self.conn.execute("DELETE FROM subrecords")
            self.conn.execute("DELETE FROM records")
            self.conn.execute("DELETE FROM snapshots")
            self.conn.commit()
            self.conn.execute("VACUUM")
        return count
