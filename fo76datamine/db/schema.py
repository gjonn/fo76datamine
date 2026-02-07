"""SQLite schema creation for the datamining database."""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    label       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    esm_hash    TEXT NOT NULL,
    esm_size    INTEGER NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    string_count INTEGER NOT NULL DEFAULT 0,
    has_subrecords INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS records (
    snapshot_id  INTEGER NOT NULL,
    form_id      INTEGER NOT NULL,
    record_type  TEXT NOT NULL,
    editor_id    TEXT,
    full_name    TEXT,
    full_name_id INTEGER,
    desc_text    TEXT,
    desc_id      INTEGER,
    data_hash    TEXT NOT NULL,
    flags        INTEGER NOT NULL DEFAULT 0,
    data_size    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (snapshot_id, form_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_records_type ON records(snapshot_id, record_type);
CREATE INDEX IF NOT EXISTS idx_records_editor_id ON records(snapshot_id, editor_id);
CREATE INDEX IF NOT EXISTS idx_records_full_name ON records(snapshot_id, full_name);
CREATE INDEX IF NOT EXISTS idx_records_hash ON records(snapshot_id, data_hash);

CREATE TABLE IF NOT EXISTS decoded_fields (
    snapshot_id  INTEGER NOT NULL,
    form_id      INTEGER NOT NULL,
    field_name   TEXT NOT NULL,
    field_value  TEXT NOT NULL,
    field_type   TEXT NOT NULL DEFAULT 'str',
    PRIMARY KEY (snapshot_id, form_id, field_name),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_decoded_formid ON decoded_fields(snapshot_id, form_id);

CREATE TABLE IF NOT EXISTS strings (
    snapshot_id  INTEGER NOT NULL,
    string_id    INTEGER NOT NULL,
    text         TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (snapshot_id, string_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_strings_text ON strings(text);

CREATE TABLE IF NOT EXISTS keywords (
    snapshot_id  INTEGER NOT NULL,
    form_id      INTEGER NOT NULL,
    editor_id    TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, form_id),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS subrecords (
    snapshot_id  INTEGER NOT NULL,
    form_id      INTEGER NOT NULL,
    sub_type     TEXT NOT NULL,
    sub_index    INTEGER NOT NULL,
    data         BLOB NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subrecords_formid ON subrecords(snapshot_id, form_id);

CREATE TABLE IF NOT EXISTS diffs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    old_snapshot_id INTEGER NOT NULL,
    new_snapshot_id INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    added_count     INTEGER NOT NULL DEFAULT 0,
    removed_count   INTEGER NOT NULL DEFAULT 0,
    modified_count  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (old_snapshot_id) REFERENCES snapshots(id),
    FOREIGN KEY (new_snapshot_id) REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS diff_entries (
    diff_id      INTEGER NOT NULL,
    form_id      INTEGER NOT NULL,
    change_type  TEXT NOT NULL,  -- 'added', 'removed', 'modified'
    record_type  TEXT,
    editor_id    TEXT,
    full_name    TEXT,
    old_hash     TEXT,
    new_hash     TEXT,
    FOREIGN KEY (diff_id) REFERENCES diffs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_diff_entries_diff ON diff_entries(diff_id);
CREATE INDEX IF NOT EXISTS idx_diff_entries_type ON diff_entries(diff_id, change_type);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database schema."""
    conn.executescript(SCHEMA_SQL)

    # Check/set schema version
    cur = conn.execute("SELECT COUNT(*) FROM schema_version")
    if cur.fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
    conn.commit()
