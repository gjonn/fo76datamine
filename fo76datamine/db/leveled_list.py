"""Recursive leveled list tree expansion and text formatter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LeveledEntry:
    """A single entry in a leveled list."""
    level: int
    count: int
    form_id: int
    record_type: str
    editor_id: Optional[str]
    full_name: Optional[str]
    children: list[LeveledEntry] = field(default_factory=list)

    @property
    def form_id_hex(self) -> str:
        return f"0x{self.form_id:08X}"


@dataclass
class LeveledTree:
    """Root of an expanded leveled list tree."""
    form_id: int
    record_type: str
    editor_id: Optional[str]
    full_name: Optional[str]
    chance_none: int
    use_all: bool
    entries: list[LeveledEntry] = field(default_factory=list)

    @property
    def form_id_hex(self) -> str:
        return f"0x{self.form_id:08X}"


def expand_leveled_list(store, snapshot_id: int, form_id: int,
                        max_depth: int = 10) -> Optional[LeveledTree]:
    """Recursively expand a leveled list into a tree.

    Returns None if the record isn't LVLI or LVLN.
    Uses a visited set to prevent circular references.
    """
    rec = store.get_record(snapshot_id, form_id)
    if rec is None or rec.record_type not in ("LVLI", "LVLN"):
        return None

    fields = store.get_decoded_fields(snapshot_id, form_id)
    field_map = {f.field_name: f.field_value for f in fields}

    chance_none = int(field_map.get("chance_none", "0"))
    use_all = field_map.get("use_all", "False") == "True"

    tree = LeveledTree(
        form_id=form_id,
        record_type=rec.record_type,
        editor_id=rec.editor_id,
        full_name=rec.full_name,
        chance_none=chance_none,
        use_all=use_all,
    )

    visited: set[int] = {form_id}
    tree.entries = _expand_entries(store, snapshot_id, field_map, max_depth, visited)
    return tree


def _expand_entries(store, snapshot_id: int, field_map: dict[str, str],
                    depth: int, visited: set[int]) -> list[LeveledEntry]:
    """Parse entry_N_ref / entry_N_level / entry_N_count fields and recurse."""
    entries = []
    i = 0
    while True:
        ref_key = f"entry_{i}_ref"
        if ref_key not in field_map:
            break

        ref_hex = field_map[ref_key]
        level = int(field_map.get(f"entry_{i}_level", "0"))
        count = int(field_map.get(f"entry_{i}_count", "1"))
        try:
            ref_fid = int(ref_hex, 16)
        except (ValueError, TypeError):
            i += 1
            continue

        ref_rec = store.get_record(snapshot_id, ref_fid)
        record_type = ref_rec.record_type if ref_rec else ""
        editor_id = ref_rec.editor_id if ref_rec else None
        full_name = ref_rec.full_name if ref_rec else None

        entry = LeveledEntry(
            level=level,
            count=count,
            form_id=ref_fid,
            record_type=record_type,
            editor_id=editor_id,
            full_name=full_name,
        )

        # Recurse into nested leveled lists if not visited and depth allows
        if depth > 0 and record_type in ("LVLI", "LVLN") and ref_fid not in visited:
            visited.add(ref_fid)
            child_fields = store.get_decoded_fields(snapshot_id, ref_fid)
            child_map = {f.field_name: f.field_value for f in child_fields}
            entry.children = _expand_entries(store, snapshot_id, child_map, depth - 1, visited)

        entries.append(entry)
        i += 1

    return entries


def format_tree_text(tree: LeveledTree) -> str:
    """Format a leveled list tree as indented text."""
    lines = []
    name = tree.full_name or tree.editor_id or tree.form_id_hex
    lines.append(f"{name} ({tree.form_id_hex}) [{tree.record_type}]")
    lines.append(f"  Chance None: {tree.chance_none}%  Use All: {tree.use_all}")

    for entry in tree.entries:
        _format_entry(entry, lines, indent=1)

    return "\n".join(lines)


def _format_entry(entry: LeveledEntry, lines: list[str], indent: int):
    """Recursively format a single entry and its children."""
    prefix = "  " * indent
    name = entry.full_name or entry.editor_id or entry.form_id_hex
    type_tag = f"[{entry.record_type}]" if entry.record_type else ""
    qty = f" x{entry.count}" if entry.count > 1 else ""
    lvl = f" (lvl {entry.level})" if entry.level > 0 else ""
    lines.append(f"{prefix}- {name}{qty}{lvl} {type_tag} {entry.form_id_hex}")

    for child in entry.children:
        _format_entry(child, lines, indent + 1)
