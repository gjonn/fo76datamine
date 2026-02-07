"""Format diff results as text, JSON, or markdown."""
from __future__ import annotations

import json
from typing import Optional

from fo76datamine.db.store import Store
from fo76datamine.diff.engine import DiffResult


def format_diff(result: DiffResult, store: Store,
                old_id: int, new_id: int, fmt: str = "text",
                new_store: Optional[Store] = None) -> str:
    """Format a diff result in the specified format."""
    ns = new_store or store
    if fmt == "json":
        return _format_json(result)
    elif fmt == "markdown":
        return _format_markdown(result, store, old_id, new_id, new_store=ns)
    else:
        return _format_text(result, store, old_id, new_id, new_store=ns)


def _format_text(result: DiffResult, store: Store, old_id: int, new_id: int,
                 new_store: Optional[Store] = None) -> str:
    ns = new_store or store
    lines = []
    old_snap = store.get_snapshot(old_id)
    new_snap = ns.get_snapshot(new_id)

    lines.append(f"Diff: #{old_id} ({old_snap.label}) -> #{new_id} ({new_snap.label})")
    lines.append(f"Added: {len(result.added)}  Removed: {len(result.removed)}  Modified: {len(result.modified)}")
    lines.append("")

    if result.added:
        lines.append(f"=== ADDED ({len(result.added)}) ===")
        for rec in result.added[:100]:
            name = rec.full_name or ""
            edid = rec.editor_id or ""
            lines.append(f"  + {rec.form_id_hex}  {rec.record_type:<6}  {edid:<40}  {name}")
        if len(result.added) > 100:
            lines.append(f"  ... and {len(result.added) - 100} more")
        lines.append("")

    if result.removed:
        lines.append(f"=== REMOVED ({len(result.removed)}) ===")
        for rec in result.removed[:100]:
            name = rec.full_name or ""
            edid = rec.editor_id or ""
            lines.append(f"  - {rec.form_id_hex}  {rec.record_type:<6}  {edid:<40}  {name}")
        if len(result.removed) > 100:
            lines.append(f"  ... and {len(result.removed) - 100} more")
        lines.append("")

    if result.modified:
        lines.append(f"=== MODIFIED ({len(result.modified)}) ===")
        for old_rec, new_rec in result.modified[:100]:
            name = new_rec.full_name or new_rec.editor_id or ""
            lines.append(f"  ~ {new_rec.form_id_hex}  {new_rec.record_type:<6}  {name}")

            # Show field-level changes
            changes = result.field_changes.get(new_rec.form_id, [])
            for change in changes:
                old_v = change.old_value or "(none)"
                new_v = change.new_value or "(none)"
                lines.append(f"      {change.field_name}: {old_v} -> {new_v}")

        if len(result.modified) > 100:
            lines.append(f"  ... and {len(result.modified) - 100} more")

    return "\n".join(lines)


def _format_json(result: DiffResult) -> str:
    data = {
        "added": [
            {"form_id": f"0x{r.form_id:08X}", "type": r.record_type,
             "editor_id": r.editor_id, "name": r.full_name}
            for r in result.added
        ],
        "removed": [
            {"form_id": f"0x{r.form_id:08X}", "type": r.record_type,
             "editor_id": r.editor_id, "name": r.full_name}
            for r in result.removed
        ],
        "modified": [
            {
                "form_id": f"0x{new.form_id:08X}", "type": new.record_type,
                "editor_id": new.editor_id, "name": new.full_name,
                "changes": [
                    {"field": c.field_name, "old": c.old_value, "new": c.new_value}
                    for c in result.field_changes.get(new.form_id, [])
                ]
            }
            for old, new in result.modified
        ],
        "summary": {
            "added": len(result.added),
            "removed": len(result.removed),
            "modified": len(result.modified),
        },
    }
    return json.dumps(data, indent=2)


def _format_markdown(result: DiffResult, store: Store, old_id: int, new_id: int,
                     new_store: Optional[Store] = None) -> str:
    ns = new_store or store
    lines = []
    old_snap = store.get_snapshot(old_id)
    new_snap = ns.get_snapshot(new_id)

    lines.append(f"# Diff: {old_snap.label} -> {new_snap.label}")
    lines.append(f"")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Added | {len(result.added)} |")
    lines.append(f"| Removed | {len(result.removed)} |")
    lines.append(f"| Modified | {len(result.modified)} |")
    lines.append("")

    if result.added:
        lines.append(f"## Added ({len(result.added)})")
        lines.append(f"| FormID | Type | Editor ID | Name |")
        lines.append(f"|--------|------|-----------|------|")
        for rec in result.added[:100]:
            lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        lines.append("")

    if result.removed:
        lines.append(f"## Removed ({len(result.removed)})")
        lines.append(f"| FormID | Type | Editor ID | Name |")
        lines.append(f"|--------|------|-----------|------|")
        for rec in result.removed[:100]:
            lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        lines.append("")

    if result.modified:
        lines.append(f"## Modified ({len(result.modified)})")
        for old_rec, new_rec in result.modified[:100]:
            name = new_rec.full_name or new_rec.editor_id or new_rec.form_id_hex
            lines.append(f"### {name} ({new_rec.form_id_hex})")
            changes = result.field_changes.get(new_rec.form_id, [])
            if changes:
                lines.append(f"| Field | Old | New |")
                lines.append(f"|-------|-----|-----|")
                for c in changes:
                    lines.append(f"| {c.field_name} | {c.old_value or ''} | {c.new_value or ''} |")
            lines.append("")

    return "\n".join(lines)
