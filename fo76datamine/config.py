"""Default paths and constants for Fallout 76 datamining."""
from pathlib import Path


def derive_ba2_path(esm: Path) -> Path:
    """Derive localization BA2 path from ESM path (sibling in same Data dir)."""
    return esm.parent / "SeventySix - Localization.ba2"


def derive_db_path(esm: Path) -> Path:
    """Derive database path from ESM path. DB lives next to ESM's parent dir."""
    db_dir = esm.parent.parent / "fo76datamine" / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "fo76datamine.db"


# ESM format constants
ESM_HEADER_SIZE = 24        # Record and GRUP headers are both 24 bytes
SUBRECORD_HEADER_SIZE = 6   # 4-byte type + 2-byte size
COMPRESSION_FLAG = 0x00040000
MASTER_FLAG = 0x00000001
LOCALIZED_FLAG = 0x00000080

# Record types to skip (placement data, not useful for datamining)
SKIP_RECORD_TYPES = frozenset({b"REFR", b"NAVM", b"ACHR", b"PGRE", b"PMIS", b"PHZD", b"PARW"})

# Record types with nested groups (CELL, WRLD contain child groups)
NESTED_GROUP_TYPES = frozenset({b"CELL", b"WRLD"})
