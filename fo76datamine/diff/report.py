"""Format diff results as text, JSON, or markdown."""
from __future__ import annotations

import json
from typing import Optional

from fo76datamine.db.resolve import FormIDResolver
from fo76datamine.db.store import Store
from fo76datamine.diff.engine import DiffResult


def _build_xrefs(store: Store, snapshot_id: int, diff_form_ids: set[int],
                  resolver: FormIDResolver):
    """Build cross-refs filtered to records present in the diff.

    Returns (forward_refs, reverse_refs) where:
      forward_refs[fid] = [(field_name, target_fid, target_display_name), ...]
      reverse_refs[fid] = [(source_fid, source_display_name, field_name), ...]
    Only includes links where both source and target are in diff_form_ids.
    """
    all_refs = store.get_formid_refs(snapshot_id)
    forward: dict[int, list[tuple[str, int, str]]] = {}
    reverse: dict[int, list[tuple[int, str, str]]] = {}

    for src_fid, refs in all_refs.items():
        if src_fid not in diff_form_ids:
            continue
        for field_name, tgt_fid in refs:
            if tgt_fid not in diff_form_ids:
                continue
            tgt_name = resolver.resolve_name(f"0x{tgt_fid:08X}") or f"0x{tgt_fid:08X}"
            src_name = resolver.resolve_name(f"0x{src_fid:08X}") or f"0x{src_fid:08X}"
            forward.setdefault(src_fid, []).append((field_name, tgt_fid, tgt_name))
            reverse.setdefault(tgt_fid, []).append((src_fid, src_name, field_name))

    return forward, reverse


def format_diff(result: DiffResult, store: Store,
                old_id: int, new_id: int, fmt: str = "text",
                new_store: Optional[Store] = None,
                icon_map: Optional[dict[int, Optional[str]]] = None) -> str:
    """Format a diff result in the specified format."""
    ns = new_store or store
    old_resolver = FormIDResolver(store, old_id)
    new_resolver = FormIDResolver(ns, new_id)

    # Collect all form_ids in the diff for cross-referencing
    diff_fids: set[int] = set()
    diff_fids.update(r.form_id for r in result.added)
    diff_fids.update(r.form_id for r in result.removed)
    diff_fids.update(new.form_id for _, new in result.modified)

    # Build xrefs: old store for removed, new store for added+modified
    old_fwd, old_rev = _build_xrefs(store, old_id, diff_fids, old_resolver)
    new_fwd, new_rev = _build_xrefs(ns, new_id, diff_fids, new_resolver)

    if fmt == "json":
        return _format_json(result, store, old_id, new_id, new_store=ns,
                            old_resolver=old_resolver, new_resolver=new_resolver,
                            old_xrefs=(old_fwd, old_rev), new_xrefs=(new_fwd, new_rev))
    elif fmt == "markdown":
        return _format_markdown(result, store, old_id, new_id, new_store=ns,
                                icon_map=icon_map,
                                old_resolver=old_resolver, new_resolver=new_resolver,
                                old_xrefs=(old_fwd, old_rev), new_xrefs=(new_fwd, new_rev))
    elif fmt == "html":
        return _format_html(result, store, old_id, new_id, new_store=ns,
                            icon_map=icon_map,
                            old_resolver=old_resolver, new_resolver=new_resolver,
                            old_xrefs=(old_fwd, old_rev), new_xrefs=(new_fwd, new_rev))
    else:
        return _format_text(result, store, old_id, new_id, new_store=ns,
                            old_resolver=old_resolver, new_resolver=new_resolver,
                            old_xrefs=(old_fwd, old_rev), new_xrefs=(new_fwd, new_rev))


_XrefPair = tuple[dict[int, list], dict[int, list]]
_EMPTY_XREFS: _XrefPair = ({}, {})


def _text_xref_lines(form_id: int, fwd: dict, rev: dict) -> list[str]:
    """Return indented text lines for forward/reverse cross-refs."""
    lines = []
    for field_name, tgt_fid, tgt_name in fwd.get(form_id, []):
        lines.append(f"      \u2192 references: {tgt_name} (0x{tgt_fid:08X}) via {field_name}")
    for src_fid, src_name, field_name in rev.get(form_id, []):
        lines.append(f"      \u2190 referenced by: {src_name} (0x{src_fid:08X}) via {field_name}")
    return lines


def _format_text(result: DiffResult, store: Store, old_id: int, new_id: int,
                 new_store: Optional[Store] = None,
                 old_resolver: Optional[FormIDResolver] = None,
                 new_resolver: Optional[FormIDResolver] = None,
                 old_xrefs: _XrefPair = _EMPTY_XREFS,
                 new_xrefs: _XrefPair = _EMPTY_XREFS) -> str:
    ns = new_store or store
    lines = []
    old_snap = store.get_snapshot(old_id)
    new_snap = ns.get_snapshot(new_id)

    lines.append(f"Diff: #{old_id} ({old_snap.label}) -> #{new_id} ({new_snap.label})")
    lines.append(f"Added: {len(result.added)}  Removed: {len(result.removed)}  Modified: {len(result.modified)}")
    lines.append("")

    if result.added:
        lines.append(f"=== ADDED ({len(result.added)}) ===")
        for rec in result.added:
            name = rec.full_name or ""
            edid = rec.editor_id or ""
            lines.append(f"  + {rec.form_id_hex}  {rec.record_type:<6}  {edid:<40}  {name}")
            fields = ns.get_decoded_fields(new_id, rec.form_id)
            if fields:
                for f in fields:
                    val = new_resolver.format_field_value(f) if new_resolver else f.field_value
                    lines.append(f"      {f.field_name}: {val}")
            lines.extend(_text_xref_lines(rec.form_id, new_xrefs[0], new_xrefs[1]))
        lines.append("")

    if result.removed:
        lines.append(f"=== REMOVED ({len(result.removed)}) ===")
        for rec in result.removed:
            name = rec.full_name or ""
            edid = rec.editor_id or ""
            lines.append(f"  - {rec.form_id_hex}  {rec.record_type:<6}  {edid:<40}  {name}")
            fields = store.get_decoded_fields(old_id, rec.form_id)
            if fields:
                for f in fields:
                    val = old_resolver.format_field_value(f) if old_resolver else f.field_value
                    lines.append(f"      {f.field_name}: {val}")
            lines.extend(_text_xref_lines(rec.form_id, old_xrefs[0], old_xrefs[1]))
        lines.append("")

    if result.modified:
        lines.append(f"=== MODIFIED ({len(result.modified)}) ===")
        for old_rec, new_rec in result.modified:
            name = new_rec.full_name or new_rec.editor_id or ""
            lines.append(f"  ~ {new_rec.form_id_hex}  {new_rec.record_type:<6}  {name}")

            # Show field-level changes
            changes = result.field_changes.get(new_rec.form_id, [])
            for change in changes:
                old_v = change.old_value or "(none)"
                new_v = change.new_value or "(none)"
                if change.field_type == "formid":
                    if old_resolver and old_v != "(none)":
                        old_v = old_resolver.format_value(old_v, "formid")
                    if new_resolver and new_v != "(none)":
                        new_v = new_resolver.format_value(new_v, "formid")
                lines.append(f"      {change.field_name}: {old_v} -> {new_v}")
            lines.extend(_text_xref_lines(new_rec.form_id, new_xrefs[0], new_xrefs[1]))

    return "\n".join(lines)


def _json_xrefs(form_id: int, fwd: dict, rev: dict) -> dict:
    """Return references/referenced_by dicts for JSON output."""
    out = {}
    fwd_list = fwd.get(form_id, [])
    rev_list = rev.get(form_id, [])
    if fwd_list:
        out["references"] = [
            {"field": fn, "target": f"0x{tfid:08X}", "name": tn}
            for fn, tfid, tn in fwd_list
        ]
    if rev_list:
        out["referenced_by"] = [
            {"source": f"0x{sfid:08X}", "name": sn, "field": fn}
            for sfid, sn, fn in rev_list
        ]
    return out


def _format_json(result: DiffResult, store: Store, old_id: int, new_id: int,
                 new_store: Optional[Store] = None,
                 old_resolver: Optional[FormIDResolver] = None,
                 new_resolver: Optional[FormIDResolver] = None,
                 old_xrefs: _XrefPair = _EMPTY_XREFS,
                 new_xrefs: _XrefPair = _EMPTY_XREFS) -> str:
    ns = new_store or store

    def _resolve_change(c):
        old_v = c.old_value
        new_v = c.new_value
        if c.field_type == "formid":
            if old_resolver and old_v:
                old_v = old_resolver.format_value(old_v, "formid")
            if new_resolver and new_v:
                new_v = new_resolver.format_value(new_v, "formid")
        return {"field": c.field_name, "old": old_v, "new": new_v}

    def _fields_dict(s, snap_id, form_id, resolver):
        fields = s.get_decoded_fields(snap_id, form_id)
        if not fields:
            return None
        return {
            f.field_name: (resolver.format_field_value(f) if resolver else f.field_value)
            for f in fields
        }

    added_list = []
    for r in result.added:
        entry = {"form_id": f"0x{r.form_id:08X}", "type": r.record_type,
                 "editor_id": r.editor_id, "name": r.full_name}
        fd = _fields_dict(ns, new_id, r.form_id, new_resolver)
        if fd:
            entry["fields"] = fd
        entry.update(_json_xrefs(r.form_id, new_xrefs[0], new_xrefs[1]))
        added_list.append(entry)

    removed_list = []
    for r in result.removed:
        entry = {"form_id": f"0x{r.form_id:08X}", "type": r.record_type,
                 "editor_id": r.editor_id, "name": r.full_name}
        fd = _fields_dict(store, old_id, r.form_id, old_resolver)
        if fd:
            entry["fields"] = fd
        entry.update(_json_xrefs(r.form_id, old_xrefs[0], old_xrefs[1]))
        removed_list.append(entry)

    data = {
        "added": added_list,
        "removed": removed_list,
        "modified": [
            {
                "form_id": f"0x{new.form_id:08X}", "type": new.record_type,
                "editor_id": new.editor_id, "name": new.full_name,
                "changes": [
                    _resolve_change(c)
                    for c in result.field_changes.get(new.form_id, [])
                ],
                **_json_xrefs(new.form_id, new_xrefs[0], new_xrefs[1]),
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


def _icon_cell(form_id: int, icon_map: Optional[dict[int, Optional[str]]]) -> str:
    """Return markdown image cell or empty string."""
    if icon_map is None:
        return None
    path = icon_map.get(form_id)
    if path:
        return f"![icon]({path})"
    return ""


def _md_xref_lines(form_id: int, fwd: dict, rev: dict) -> list[str]:
    """Return markdown lines for cross-refs in detail sections."""
    lines = []
    fwd_list = fwd.get(form_id, [])
    rev_list = rev.get(form_id, [])
    if fwd_list or rev_list:
        lines.append("")
        lines.append("**Related records in this diff:**")
        lines.append("")
    if fwd_list:
        for fn, tfid, tn in fwd_list:
            lines.append(f"- \u2192 `{fn}` \u2192 {tn} (`0x{tfid:08X}`)")
    if rev_list:
        for sfid, sn, fn in rev_list:
            lines.append(f"- \u2190 referenced by {sn} (`0x{sfid:08X}`) via `{fn}`")
    return lines


def _format_markdown(result: DiffResult, store: Store, old_id: int, new_id: int,
                     new_store: Optional[Store] = None,
                     icon_map: Optional[dict[int, Optional[str]]] = None,
                     old_resolver: Optional[FormIDResolver] = None,
                     new_resolver: Optional[FormIDResolver] = None,
                     old_xrefs: _XrefPair = _EMPTY_XREFS,
                     new_xrefs: _XrefPair = _EMPTY_XREFS) -> str:
    ns = new_store or store
    lines = []
    old_snap = store.get_snapshot(old_id)
    new_snap = ns.get_snapshot(new_id)
    has_icons = icon_map is not None and len(icon_map) > 0

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
        if has_icons:
            lines.append(f"| Icon | FormID | Type | Editor ID | Name |")
            lines.append(f"|------|--------|------|-----------|------|")
        else:
            lines.append(f"| FormID | Type | Editor ID | Name |")
            lines.append(f"|--------|------|-----------|------|")
        for rec in result.added:
            if has_icons:
                icon = _icon_cell(rec.form_id, icon_map)
                lines.append(f"| {icon} | {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
            else:
                lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        lines.append("")
        # Decoded fields detail for added records
        for rec in result.added:
            fields = ns.get_decoded_fields(new_id, rec.form_id)
            if fields:
                name = rec.full_name or rec.editor_id or rec.form_id_hex
                lines.append(f"### {name} ({rec.form_id_hex})")
                lines.append(f"| Field | Value |")
                lines.append(f"|-------|-------|")
                for f in fields:
                    val = new_resolver.format_field_value(f) if new_resolver else f.field_value
                    lines.append(f"| {f.field_name} | {val} |")
                lines.extend(_md_xref_lines(rec.form_id, new_xrefs[0], new_xrefs[1]))
                lines.append("")

    if result.removed:
        lines.append(f"## Removed ({len(result.removed)})")
        if has_icons:
            lines.append(f"| Icon | FormID | Type | Editor ID | Name |")
            lines.append(f"|------|--------|------|-----------|------|")
        else:
            lines.append(f"| FormID | Type | Editor ID | Name |")
            lines.append(f"|--------|------|-----------|------|")
        for rec in result.removed:
            if has_icons:
                icon = _icon_cell(rec.form_id, icon_map)
                lines.append(f"| {icon} | {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
            else:
                lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        lines.append("")
        # Decoded fields detail for removed records
        for rec in result.removed:
            fields = store.get_decoded_fields(old_id, rec.form_id)
            if fields:
                name = rec.full_name or rec.editor_id or rec.form_id_hex
                lines.append(f"### {name} ({rec.form_id_hex})")
                lines.append(f"| Field | Value |")
                lines.append(f"|-------|-------|")
                for f in fields:
                    val = old_resolver.format_field_value(f) if old_resolver else f.field_value
                    lines.append(f"| {f.field_name} | {val} |")
                lines.extend(_md_xref_lines(rec.form_id, old_xrefs[0], old_xrefs[1]))
                lines.append("")

    if result.modified:
        lines.append(f"## Modified ({len(result.modified)})")
        for old_rec, new_rec in result.modified:
            name = new_rec.full_name or new_rec.editor_id or new_rec.form_id_hex
            if has_icons:
                icon = _icon_cell(new_rec.form_id, icon_map)
                if icon:
                    lines.append(f"### {name} ({new_rec.form_id_hex}) {icon}")
                else:
                    lines.append(f"### {name} ({new_rec.form_id_hex})")
            else:
                lines.append(f"### {name} ({new_rec.form_id_hex})")
            changes = result.field_changes.get(new_rec.form_id, [])
            if changes:
                lines.append(f"| Field | Old | New |")
                lines.append(f"|-------|-----|-----|")
                for c in changes:
                    old_v = c.old_value or ''
                    new_v = c.new_value or ''
                    if c.field_type == "formid":
                        if old_resolver and old_v:
                            old_v = old_resolver.format_value(old_v, "formid")
                        if new_resolver and new_v:
                            new_v = new_resolver.format_value(new_v, "formid")
                    lines.append(f"| {c.field_name} | {old_v} | {new_v} |")
            lines.extend(_md_xref_lines(new_rec.form_id, new_xrefs[0], new_xrefs[1]))
            lines.append("")

    return "\n".join(lines)


# -- HTML output --

_HTML_CSS = """\
/* --- Base --- */
*, *::before, *::after { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #1a1a2e; color: #e0e0e0; margin: 2rem; margin-right: 200px; }
h1, h2, h3 { color: #00d4aa; }
a { color: #00d4aa; text-decoration: none; }
a:hover { text-decoration: underline; }

/* --- Tables --- */
table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }
thead th { background: #16213e; color: #00d4aa; text-align: left; padding: 8px 12px;
     border-bottom: 2px solid #0f3460; position: sticky; top: 0; z-index: 10;
     cursor: pointer; user-select: none; white-space: nowrap; }
thead th:hover { background: #1a2a4e; }
thead th .sort-arrow { font-size: 0.7rem; margin-left: 4px; opacity: 0.4; }
thead th.sort-asc .sort-arrow::after { content: ' \\25B2'; opacity: 1; }
thead th.sort-desc .sort-arrow::after { content: ' \\25BC'; opacity: 1; }
tbody td { padding: 6px 12px; border-bottom: 1px solid #1a1a3e; }
tbody tr:nth-child(even) { background: rgba(22, 33, 62, 0.3); }
tbody tr:hover { background: #16213e; }

/* --- Icons --- */
img.icon { width: 64px; height: 64px; object-fit: contain;
           image-rendering: pixelated; vertical-align: middle; cursor: pointer; }

/* --- Summary cards --- */
.summary { display: flex; gap: 2rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.summary .stat { background: #16213e; padding: 1rem 1.5rem; border-radius: 8px;
    border-left: 4px solid #0f3460; transition: transform 0.15s; }
.summary .stat:hover { transform: translateY(-2px); }
.stat .label { color: #aaa; font-size: 0.85rem; }
.stat .value { color: #00d4aa; font-size: 1.5rem; font-weight: bold; }
.stat-added { border-left-color: #4ade80 !important; }
.stat-removed { border-left-color: #f87171 !important; }
.stat-modified { border-left-color: #fbbf24 !important; }
.added { color: #4ade80; } .removed { color: #f87171; } .modified { color: #fbbf24; }

/* --- Record type badges --- */
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.8rem;
    font-weight: 600; letter-spacing: 0.03em; font-family: monospace; }
.badge-weap { background: #7f1d1d; color: #fca5a5; }
.badge-armo { background: #1e3a5f; color: #93c5fd; }
.badge-alch { background: #14532d; color: #86efac; }
.badge-npc  { background: #4a1d6a; color: #d8b4fe; }
.badge-misc { background: #713f12; color: #fde68a; }
.badge-ammo { background: #831843; color: #f9a8d4; }
.badge-book { background: #365314; color: #bef264; }
.badge-keym { background: #164e63; color: #67e8f9; }
.badge-note { background: #44403c; color: #d6d3d1; }
.badge-flst { background: #3b0764; color: #c084fc; }
.badge-glob { background: #0c4a6e; color: #7dd3fc; }
.badge-default { background: #1e293b; color: #94a3b8; }

/* --- Collapsible sections --- */
.section-header { cursor: pointer; user-select: none; display: flex;
    align-items: center; gap: 0.5rem; }
.section-header::before { content: '\\25BC'; font-size: 0.7rem; transition: transform 0.2s;
    display: inline-block; width: 1em; }
.section-header.collapsed::before { transform: rotate(-90deg); }
.section-body { overflow: hidden; transition: max-height 0.3s ease; }
.section-body.collapsed { display: none; }

/* --- Table filter --- */
.table-filter { margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.75rem; }
.table-filter input { background: #16213e; border: 1px solid #0f3460; color: #e0e0e0;
    padding: 6px 12px; border-radius: 4px; font-size: 0.9rem; width: 260px; }
.table-filter input:focus { outline: none; border-color: #00d4aa; }
.table-filter .count { color: #888; font-size: 0.85rem; }

/* --- TOC sidebar --- */
.toc { position: fixed; right: 0; top: 0; width: 180px; height: 100vh;
    background: #111827; border-left: 1px solid #1f2937; padding: 1rem 0.75rem;
    overflow-y: auto; z-index: 50; font-size: 0.82rem; }
.toc h3 { color: #00d4aa; margin: 0 0 0.75rem 0; font-size: 0.9rem; }
.toc a { display: block; color: #9ca3af; padding: 3px 0; border-left: 2px solid transparent;
    padding-left: 8px; }
.toc a:hover { color: #e0e0e0; text-decoration: none; }
.toc a.active { color: #00d4aa; border-left-color: #00d4aa; }

/* --- Scroll-to-top --- */
#scroll-top { display: none; position: fixed; bottom: 2rem; right: 200px; z-index: 100;
    background: #00d4aa; color: #1a1a2e; border: none; border-radius: 50%; width: 40px;
    height: 40px; font-size: 1.2rem; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.3); }
#scroll-top:hover { background: #00f0c0; }

/* --- Truncation notice --- */
.truncation-notice { background: #2d2206; border: 1px solid #854d0e; border-left: 4px solid #eab308;
    color: #fde68a; padding: 0.75rem 1rem; border-radius: 4px; margin-bottom: 1rem;
    font-size: 0.9rem; }

/* --- Change table / field details --- */
.change-table { width: auto; margin: 0.5rem 0 1.5rem 1rem; }
.change-table td, .change-table th { padding: 4px 10px; font-size: 0.9rem; }
.inline-changes { margin: 0.25rem 0; }
.inline-changes table { width: auto; margin: 0; }
.inline-changes td, .inline-changes th { padding: 2px 8px; font-size: 0.85rem; }
.btn-toggle { background: #0f3460; color: #00d4aa; border: 1px solid #16213e;
    border-radius: 4px; padding: 2px 10px; font-size: 0.8rem; cursor: pointer; }
.btn-toggle:hover { background: #16213e; }
.hash-only { color: #666; font-style: italic; font-size: 0.85rem; }
tr[data-hash-only] { display: none; }

/* --- Lightbox --- */
#lightbox { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(0,0,0,0); z-index: 1000; cursor: pointer;
    align-items: center; justify-content: center; flex-direction: column;
    transition: background 0.25s; }
#lightbox.visible { display: flex; background: rgba(0,0,0,0.92); }
#lightbox img { max-width: 90vw; max-height: 85vh; object-fit: contain;
    image-rendering: pixelated; border: 2px solid #00d4aa;
    transform: scale(0.95); opacity: 0; transition: transform 0.25s, opacity 0.25s; }
#lightbox.visible img { transform: scale(1); opacity: 1; }
#lightbox .caption { color: #aaa; margin-top: 0.75rem; font-size: 0.9rem; }

/* --- Responsive --- */
@media (max-width: 900px) {
    .toc { display: none; }
    body { margin-right: 2rem; }
    #scroll-top { right: 2rem; }
}
@media (max-width: 768px) {
    body { margin: 1rem; }
    .summary { gap: 1rem; }
    .summary .stat { padding: 0.75rem 1rem; }
    .table-filter input { width: 100%; }
    .table-filter { flex-wrap: wrap; }
}
"""

_HTML_LIGHTBOX_DIV = """\
<div id="lightbox">
  <img id="lb-img" alt="">
  <div class="caption" id="lb-caption"></div>
</div>
"""

_HTML_JS = """\
<script>
(function() {
  /* --- Table filter --- */
  document.querySelectorAll('.table-filter input').forEach(input => {
    const wrap = input.closest('.filterable');
    const tbody = wrap ? wrap.querySelector('tbody') : null;
    const countEl = input.parentElement.querySelector('.count');
    if (!tbody) return;
    const rows = Array.from(tbody.rows);
    input.addEventListener('input', () => {
      const q = input.value.toLowerCase();
      let visible = 0;
      rows.forEach(r => {
        const show = !q || r.textContent.toLowerCase().includes(q);
        r.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      if (countEl) countEl.textContent = q ? visible + ' / ' + rows.length : rows.length + ' rows';
    });
    if (countEl) countEl.textContent = rows.length + ' rows';
  });

  /* --- Column sorting --- */
  document.querySelectorAll('thead th[data-sortable]').forEach(th => {
    th.addEventListener('click', () => {
      const table = th.closest('table');
      const tbody = table.querySelector('tbody');
      if (!tbody) return;
      const idx = Array.from(th.parentElement.children).indexOf(th);
      const rows = Array.from(tbody.rows);
      const asc = !th.classList.contains('sort-asc');
      // Clear sibling sort classes
      th.parentElement.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
      th.classList.add(asc ? 'sort-asc' : 'sort-desc');
      rows.sort((a, b) => {
        let va = (a.cells[idx]?.textContent || '').trim();
        let vb = (b.cells[idx]?.textContent || '').trim();
        // Numeric-aware
        const na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) return asc ? na - nb : nb - na;
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      });
      rows.forEach(r => tbody.appendChild(r));
    });
  });

  /* --- Collapsible sections --- */
  document.querySelectorAll('.section-header').forEach(hdr => {
    hdr.addEventListener('click', () => {
      hdr.classList.toggle('collapsed');
      const body = hdr.nextElementSibling;
      if (body && body.classList.contains('section-body')) {
        body.classList.toggle('collapsed');
      }
    });
  });

  /* --- Toggle-detail buttons --- */
  document.querySelectorAll('.btn-toggle').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const target = document.getElementById(btn.dataset.target);
      if (!target) return;
      const hidden = target.style.display === 'none';
      target.style.display = hidden ? '' : 'none';
      const orig = btn.dataset.label || btn.textContent;
      if (!btn.dataset.label) btn.dataset.label = orig;
      btn.textContent = hidden ? orig.replace('Show', 'Hide') : orig;
    });
  });

  /* --- Scroll-to-top --- */
  const scrollBtn = document.getElementById('scroll-top');
  if (scrollBtn) {
    window.addEventListener('scroll', () => {
      scrollBtn.style.display = window.scrollY > 400 ? 'block' : 'none';
    });
    scrollBtn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  /* --- Hide hash-only checkbox --- */
  const hashCb = document.getElementById('hide-hash-only');
  if (hashCb) {
    hashCb.addEventListener('change', () => {
      const hide = hashCb.checked;
      document.querySelectorAll('tr[data-hash-only]').forEach(r => {
        r.style.display = hide ? 'none' : '';
      });
    });
  }

  /* --- TOC scroll spy --- */
  const tocLinks = document.querySelectorAll('.toc a');
  if (tocLinks.length > 0) {
    const sections = Array.from(tocLinks).map(a => {
      const id = a.getAttribute('href')?.slice(1);
      return id ? document.getElementById(id) : null;
    }).filter(Boolean);
    window.addEventListener('scroll', () => {
      let current = '';
      sections.forEach(sec => {
        if (sec.getBoundingClientRect().top <= 120) current = sec.id;
      });
      tocLinks.forEach(a => {
        a.classList.toggle('active', a.getAttribute('href') === '#' + current);
      });
    });
  }

  /* --- Lightbox --- */
  const lb = document.getElementById('lightbox');
  if (lb) {
    document.querySelectorAll('img.icon').forEach(img => {
      img.addEventListener('click', e => {
        e.stopPropagation();
        document.getElementById('lb-img').src = img.dataset.full || img.src;
        document.getElementById('lb-caption').textContent =
          img.closest('tr')?.querySelector('td:nth-child(2)')?.textContent || '';
        lb.classList.add('visible');
        // Force reflow for transition
        void lb.offsetWidth;
      });
    });
    lb.addEventListener('click', () => lb.classList.remove('visible'));
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') lb.classList.remove('visible');
    });
  }
})();
</script>
"""


def _html_icon(form_id: int, icon_map: Optional[dict]) -> str:
    if icon_map is None:
        return ""
    path = icon_map.get(form_id)
    if path:
        # Derive full-res path: icons/X.png -> icons/full/X.png
        full_path = path.replace("icons/", "icons/full/", 1)
        return f'<img class="icon" src="{path}" data-full="{full_path}" alt="">'
    return ""


def _esc(text: Optional[str]) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_BADGE_CLASSES = {
    "WEAP": "badge-weap", "ARMO": "badge-armo", "ALCH": "badge-alch",
    "NPC_": "badge-npc", "MISC": "badge-misc", "AMMO": "badge-ammo",
    "BOOK": "badge-book", "KEYM": "badge-keym", "NOTE": "badge-note",
    "FLST": "badge-flst", "GLOB": "badge-glob",
}


def _badge(record_type: str) -> str:
    """Return an HTML badge pill for a record type."""
    cls = _BADGE_CLASSES.get(record_type, "badge-default")
    return f'<span class="badge {cls}">{record_type}</span>'


def html_wrap(title: str, body: str) -> str:
    """Wrap body content in a full HTML document with shared CSS and lightbox."""
    return (
        f"<!DOCTYPE html>\n<html><head><meta charset='utf-8'>\n"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>\n"
        f"<title>{_esc(title)}</title>\n"
        f"<style>{_HTML_CSS}</style></head>\n"
        f"<body>\n{body}\n"
        f"{_HTML_LIGHTBOX_DIV}\n"
        f"<button id='scroll-top' title='Scroll to top'>&#9650;</button>\n"
        f"{_HTML_JS}\n</body></html>"
    )


def _html_xref_cell(form_id: int, fwd: dict, rev: dict, prefix: str, idx: int) -> str:
    """Build an HTML table cell with expandable cross-references."""
    fwd_list = fwd.get(form_id, [])
    rev_list = rev.get(form_id, [])
    total = len(fwd_list) + len(rev_list)
    if total == 0:
        return "<td></td>"
    xref_id = f"xref-{prefix}-{idx}"
    cell = (
        f'<td><button class="btn-toggle" data-target="{xref_id}">'
        f'Show related</button> ({total} ref{"s" if total != 1 else ""})'
        f'<div class="inline-changes" id="{xref_id}" style="display:none">'
        f'<table><tbody>'
    )
    for fn, tfid, tn in fwd_list:
        cell += f"<tr><td>&rarr; {_esc(fn)}</td><td>{_esc(tn)} (0x{tfid:08X})</td></tr>"
    for sfid, sn, fn in rev_list:
        cell += f"<tr><td>&larr; {_esc(fn)}</td><td>{_esc(sn)} (0x{sfid:08X})</td></tr>"
    cell += "</tbody></table></div></td>"
    return cell


def _format_html(result: DiffResult, store: Store, old_id: int, new_id: int,
                  new_store: Optional[Store] = None,
                  icon_map: Optional[dict[int, Optional[str]]] = None,
                  old_resolver: Optional[FormIDResolver] = None,
                  new_resolver: Optional[FormIDResolver] = None,
                  old_xrefs: _XrefPair = _EMPTY_XREFS,
                  new_xrefs: _XrefPair = _EMPTY_XREFS) -> str:
    ns = new_store or store
    old_snap = store.get_snapshot(old_id)
    new_snap = ns.get_snapshot(new_id)
    has_icons = icon_map is not None and any(v for v in icon_map.values())

    parts = []

    # --- TOC sidebar ---
    toc = ['<nav class="toc"><h3>Contents</h3>']
    toc.append('<a href="#summary">Summary</a>')
    if result.added:
        toc.append(f'<a href="#section-added">Added ({len(result.added)})</a>')
    if result.removed:
        toc.append(f'<a href="#section-removed">Removed ({len(result.removed)})</a>')
    if result.modified:
        toc.append(f'<a href="#section-modified">Modified ({len(result.modified)})</a>')
    toc.append('</nav>')
    parts.append("\n".join(toc))

    parts.append(f'<h1 id="summary">Diff: {_esc(old_snap.label)} &rarr; {_esc(new_snap.label)}</h1>')

    # Summary stats with colored borders
    parts.append('<div class="summary">')
    parts.append(f'<div class="stat stat-added"><div class="label">Added</div><div class="value added">{len(result.added)}</div></div>')
    parts.append(f'<div class="stat stat-removed"><div class="label">Removed</div><div class="value removed">{len(result.removed)}</div></div>')
    parts.append(f'<div class="stat stat-modified"><div class="label">Modified</div><div class="value modified">{len(result.modified)}</div></div>')
    parts.append('</div>')

    def _sortable_th(label):
        return f'<th data-sortable>{label}<span class="sort-arrow"></span></th>'

    def _record_table_with_fields(records, table_id, field_store, snap_id, resolver,
                                   detail_prefix, xrefs=_EMPTY_XREFS):
        """Build a record table with expandable decoded-field details and xrefs."""
        rows = []
        display = records
        xfwd, xrev = xrefs
        icon_hdr = _sortable_th("Icon").replace(" data-sortable", "") if has_icons else ""
        rows.append(f'<div class="filterable" id="{table_id}">')
        rows.append('<div class="table-filter"><input type="text" placeholder="Filter rows...">'
                    '<span class="count"></span></div>')
        rows.append(f"<table><thead><tr>{icon_hdr}"
                    f"{_sortable_th('FormID')}{_sortable_th('Type')}"
                    f"{_sortable_th('Editor ID')}{_sortable_th('Name')}"
                    f"{_sortable_th('Fields')}{_sortable_th('Related')}"
                    f"</tr></thead><tbody>")
        for idx, rec in enumerate(display):
            icon_td = f"<td>{_html_icon(rec.form_id, icon_map)}</td>" if has_icons else ""
            fields = field_store.get_decoded_fields(snap_id, rec.form_id)
            if fields:
                detail_id = f"{detail_prefix}-{idx}"
                field_cell = (
                    f'<td><button class="btn-toggle" data-target="{detail_id}">'
                    f'Show fields</button> ({len(fields)} field{"s" if len(fields) != 1 else ""})'
                    f'<div class="inline-changes" id="{detail_id}" style="display:none">'
                    f'<table><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>'
                )
                for f in fields:
                    val = resolver.format_field_value(f) if resolver else f.field_value
                    field_cell += f"<tr><td>{_esc(f.field_name)}</td><td>{_esc(val)}</td></tr>"
                field_cell += "</tbody></table></div></td>"
            else:
                field_cell = "<td></td>"
            related_cell = _html_xref_cell(rec.form_id, xfwd, xrev, detail_prefix, idx)
            rows.append(
                f"<tr>{icon_td}<td>{rec.form_id_hex}</td><td>{_badge(rec.record_type)}</td>"
                f"<td>{_esc(rec.editor_id)}</td><td>{_esc(rec.full_name)}</td>{field_cell}{related_cell}</tr>"
            )
        rows.append("</tbody></table></div>")
        return "\n".join(rows)

    if result.added:
        parts.append(f'<h2 class="section-header added" id="section-added">Added ({len(result.added)})</h2>')
        parts.append('<div class="section-body">')
        parts.append(_record_table_with_fields(
            result.added, "tbl-added", ns, new_id, new_resolver, "added-detail",
            xrefs=new_xrefs))
        parts.append('</div>')

    if result.removed:
        parts.append(f'<h2 class="section-header removed" id="section-removed">Removed ({len(result.removed)})</h2>')
        parts.append('<div class="section-body">')
        parts.append(_record_table_with_fields(
            result.removed, "tbl-removed", store, old_id, old_resolver, "removed-detail",
            xrefs=old_xrefs))
        parts.append('</div>')

    if result.modified:
        parts.append(f'<h2 class="section-header modified" id="section-modified">Modified ({len(result.modified)})</h2>')
        parts.append('<div class="section-body">')

        display_modified = result.modified

        parts.append('<div class="filterable" id="tbl-modified">')
        parts.append('<div class="table-filter"><input type="text" placeholder="Filter rows...">'
                     '<span class="count"></span>'
                     '<label style="margin-left:1rem;cursor:pointer;font-size:0.85rem;color:#aaa">'
                     '<input type="checkbox" id="hide-hash-only" checked style="margin-right:4px">'
                     'Hide hash-only</label></div>')

        icon_hdr = "<th>Icon</th>" if has_icons else ""
        parts.append(f"<table><thead><tr>{icon_hdr}"
                     f"{_sortable_th('FormID')}{_sortable_th('Type')}"
                     f"{_sortable_th('Name')}{_sortable_th('Changes')}"
                     f"{_sortable_th('Related')}"
                     f"</tr></thead><tbody>")

        new_fwd, new_rev = new_xrefs
        for idx, (old_rec, new_rec) in enumerate(display_modified):
            name = _esc(new_rec.full_name or new_rec.editor_id or new_rec.form_id_hex)
            icon_td = f"<td>{_html_icon(new_rec.form_id, icon_map)}</td>" if has_icons else ""
            changes = result.field_changes.get(new_rec.form_id, [])

            if changes:
                detail_id = f"detail-{idx}"
                change_cell = (
                    f'<td><button class="btn-toggle" data-target="{detail_id}">'
                    f'Show changes</button> ({len(changes)} field{"s" if len(changes) != 1 else ""})'
                    f'<div class="inline-changes" id="{detail_id}" style="display:none">'
                    f'<table><thead><tr><th>Field</th><th>Old</th><th>New</th></tr></thead><tbody>'
                )
                for c in changes:
                    old_v = c.old_value or ''
                    new_v = c.new_value or ''
                    if c.field_type == "formid":
                        if old_resolver and old_v:
                            old_v = old_resolver.format_value(old_v, "formid")
                        if new_resolver and new_v:
                            new_v = new_resolver.format_value(new_v, "formid")
                    change_cell += f"<tr><td>{_esc(c.field_name)}</td><td>{_esc(old_v)}</td><td>{_esc(new_v)}</td></tr>"
                change_cell += "</tbody></table></div></td>"
            else:
                change_cell = '<td><span class="hash-only">hash only</span></td>'

            is_hash_only = not changes
            row_attr = ' data-hash-only="1"' if is_hash_only else ''
            related_cell = _html_xref_cell(new_rec.form_id, new_fwd, new_rev, "modified", idx)
            parts.append(
                f"<tr{row_attr}>{icon_td}<td>{new_rec.form_id_hex}</td>"
                f"<td>{_badge(new_rec.record_type)}</td>"
                f"<td>{name}</td>{change_cell}{related_cell}</tr>"
            )

        parts.append("</tbody></table></div>")
        parts.append('</div>')

    title = f"Diff: {old_snap.label} \u2192 {new_snap.label}"
    return html_wrap(title, "\n".join(parts))
