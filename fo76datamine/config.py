"""Default paths and constants for Fallout 76 datamining."""
from pathlib import Path


def derive_ba2_path(esm: Path) -> Path:
    """Derive localization BA2 path from ESM path (sibling in same Data dir)."""
    return esm.parent / "SeventySix - Localization.ba2"


def derive_db_path(profile_name: str) -> Path:
    """Derive database path from profile name. DB lives in project db/ dir."""
    db_dir = Path(__file__).resolve().parent.parent / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / f"{profile_name}.db"


def derive_texture_ba2_paths(esm: Path) -> list[Path]:
    """Return all existing SeventySix - Textures*.ba2 paths in the Data directory."""
    data_dir = esm.parent
    paths = []
    for i in range(1, 11):
        p = data_dir / f"SeventySix - Textures{i:02d}.ba2"
        if p.exists():
            paths.append(p)
    return paths


def derive_sounds_ba2_paths(esm: Path) -> list[Path]:
    """Return all existing SeventySix - Sounds*.ba2 paths in the Data directory."""
    data_dir = esm.parent
    paths = []
    for i in range(1, 11):
        p = data_dir / f"SeventySix - Sounds{i:02d}.ba2"
        if p.exists():
            paths.append(p)
    return paths


def derive_scripts_ba2_paths(esm: Path) -> list[Path]:
    """Return all existing BA2 paths that may contain Papyrus .pex scripts."""
    data_dir = esm.parent
    paths = []
    for name in [
        "SeventySix - MiscClient.ba2",
        "SeventySix - Startup.ba2",
    ]:
        p = data_dir / name
        if p.exists():
            paths.append(p)
    # Update archives may contain newer scripts
    for f in sorted(data_dir.glob("SeventySix - *UpdateMain*.ba2")):
        paths.append(f)
    return paths


def derive_mesh_ba2_paths(esm: Path) -> list[Path]:
    """Return existing mesh BA2 paths (Meshes, MeshesExtra, UpdateMain)."""
    data_dir = esm.parent
    paths = []
    for name in ["SeventySix - Meshes.ba2", "SeventySix - MeshesExtra.ba2"]:
        p = data_dir / name
        if p.exists():
            paths.append(p)
    # Update archives may contain newer meshes
    for f in sorted(data_dir.glob("SeventySix - *UpdateMain*.ba2")):
        paths.append(f)
    return paths


def derive_material_ba2_paths(esm: Path) -> list[Path]:
    """Return existing material BA2 paths."""
    data_dir = esm.parent
    paths = []
    p = data_dir / "SeventySix - Materials.ba2"
    if p.exists():
        paths.append(p)
    # Update archives may contain newer materials
    for f in sorted(data_dir.glob("SeventySix - *UpdateMain*.ba2")):
        paths.append(f)
    return paths


def derive_workshop_icons_ba2_path(esm: Path) -> Path | None:
    """Return the WorkshopIcons BA2 path if it exists."""
    p = esm.parent / "SeventySix - WorkshopIcons.ba2"
    return p if p.exists() else None


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
