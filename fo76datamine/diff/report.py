"""Format diff results as text, JSON, or markdown."""
from __future__ import annotations

import json
from typing import Optional

from fo76datamine.db.store import Store
from fo76datamine.diff.engine import DiffResult


def format_diff(result: DiffResult, store: Store,
                old_id: int, new_id: int, fmt: str = "text",
                new_store: Optional[Store] = None,
                icon_map: Optional[dict[int, Optional[str]]] = None) -> str:
    """Format a diff result in the specified format."""
    ns = new_store or store
    if fmt == "json":
        return _format_json(result)
    elif fmt == "markdown":
        return _format_markdown(result, store, old_id, new_id, new_store=ns,
                                icon_map=icon_map)
    elif fmt == "html":
        return _format_html(result, store, old_id, new_id, new_store=ns,
                            icon_map=icon_map)
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


def _icon_cell(form_id: int, icon_map: Optional[dict[int, Optional[str]]]) -> str:
    """Return markdown image cell or empty string."""
    if icon_map is None:
        return None
    path = icon_map.get(form_id)
    if path:
        return f"![icon]({path})"
    return ""


def _format_markdown(result: DiffResult, store: Store, old_id: int, new_id: int,
                     new_store: Optional[Store] = None,
                     icon_map: Optional[dict[int, Optional[str]]] = None) -> str:
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
        for rec in result.added[:100]:
            if has_icons:
                icon = _icon_cell(rec.form_id, icon_map)
                lines.append(f"| {icon} | {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
            else:
                lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        lines.append("")

    if result.removed:
        lines.append(f"## Removed ({len(result.removed)})")
        if has_icons:
            lines.append(f"| Icon | FormID | Type | Editor ID | Name |")
            lines.append(f"|------|--------|------|-----------|------|")
        else:
            lines.append(f"| FormID | Type | Editor ID | Name |")
            lines.append(f"|--------|------|-----------|------|")
        for rec in result.removed[:100]:
            if has_icons:
                icon = _icon_cell(rec.form_id, icon_map)
                lines.append(f"| {icon} | {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
            else:
                lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        lines.append("")

    if result.modified:
        lines.append(f"## Modified ({len(result.modified)})")
        for old_rec, new_rec in result.modified[:100]:
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
                    lines.append(f"| {c.field_name} | {c.old_value or ''} | {c.new_value or ''} |")
            lines.append("")

    return "\n".join(lines)


# -- HTML output --

_HTML_CSS = """\
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #1a1a2e; color: #e0e0e0; margin: 2rem; }
h1, h2, h3 { color: #00d4aa; }
table { border-collapse: collapse; width: 100%; margin-bottom: 1.5rem; }
th { background: #16213e; color: #00d4aa; text-align: left; padding: 8px 12px;
     border-bottom: 2px solid #0f3460; }
td { padding: 6px 12px; border-bottom: 1px solid #1a1a3e; }
tr:hover { background: #16213e; }
img.icon { width: 64px; height: 64px; object-fit: contain;
           image-rendering: pixelated; vertical-align: middle; cursor: pointer; }
.summary { display: flex; gap: 2rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.summary .stat { background: #16213e; padding: 1rem 1.5rem; border-radius: 8px; }
.stat .label { color: #aaa; font-size: 0.85rem; }
.stat .value { color: #00d4aa; font-size: 1.5rem; font-weight: bold; }
.added { color: #4ade80; } .removed { color: #f87171; } .modified { color: #fbbf24; }
.change-table { width: auto; margin: 0.5rem 0 1.5rem 1rem; }
.change-table td, .change-table th { padding: 4px 10px; font-size: 0.9rem; }
#lightbox { display:none; position:fixed; top:0; left:0; width:100%; height:100%;
            background:rgba(0,0,0,0.92); z-index:1000; cursor:pointer;
            align-items:center; justify-content:center; flex-direction:column; }
#lightbox img { max-width:90vw; max-height:85vh; object-fit:contain;
                image-rendering:pixelated; border:2px solid #00d4aa; }
#lightbox .caption { color:#aaa; margin-top:0.75rem; font-size:0.9rem; }
"""

_HTML_LIGHTBOX = """\
<div id="lightbox" onclick="this.style.display='none'">
  <img id="lb-img" alt="">
  <div class="caption" id="lb-caption"></div>
</div>
<script>
document.querySelectorAll('img.icon').forEach(img => {
  img.addEventListener('click', e => {
    e.stopPropagation();
    const lb = document.getElementById('lightbox');
    document.getElementById('lb-img').src = img.dataset.full || img.src;
    document.getElementById('lb-caption').textContent =
      img.closest('tr')?.querySelector('td:nth-child(2)')?.textContent || '';
    lb.style.display = 'flex';
  });
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.getElementById('lightbox').style.display = 'none';
});
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


def html_wrap(title: str, body: str) -> str:
    """Wrap body content in a full HTML document with shared CSS and lightbox."""
    return (
        f"<!DOCTYPE html>\n<html><head><meta charset='utf-8'>\n"
        f"<title>{_esc(title)}</title>\n"
        f"<style>{_HTML_CSS}</style></head>\n"
        f"<body>\n{body}\n{_HTML_LIGHTBOX}\n</body></html>"
    )


def _format_html(result: DiffResult, store: Store, old_id: int, new_id: int,
                  new_store: Optional[Store] = None,
                  icon_map: Optional[dict[int, Optional[str]]] = None) -> str:
    ns = new_store or store
    old_snap = store.get_snapshot(old_id)
    new_snap = ns.get_snapshot(new_id)
    has_icons = icon_map is not None and any(v for v in icon_map.values())

    parts = []
    parts.append(f"<h1>Diff: {_esc(old_snap.label)} &rarr; {_esc(new_snap.label)}</h1>")

    # Summary stats
    parts.append('<div class="summary">')
    parts.append(f'<div class="stat"><div class="label">Added</div><div class="value added">{len(result.added)}</div></div>')
    parts.append(f'<div class="stat"><div class="label">Removed</div><div class="value removed">{len(result.removed)}</div></div>')
    parts.append(f'<div class="stat"><div class="label">Modified</div><div class="value modified">{len(result.modified)}</div></div>')
    parts.append('</div>')

    def _record_table(records):
        rows = []
        icon_hdr = "<th>Icon</th>" if has_icons else ""
        rows.append(f"<table><tr>{icon_hdr}<th>FormID</th><th>Type</th><th>Editor ID</th><th>Name</th></tr>")
        for rec in records[:500]:
            icon_td = f"<td>{_html_icon(rec.form_id, icon_map)}</td>" if has_icons else ""
            rows.append(
                f"<tr>{icon_td}<td>{rec.form_id_hex}</td><td>{rec.record_type}</td>"
                f"<td>{_esc(rec.editor_id)}</td><td>{_esc(rec.full_name)}</td></tr>"
            )
        rows.append("</table>")
        return "\n".join(rows)

    if result.added:
        parts.append(f'<h2 class="added">Added ({len(result.added)})</h2>')
        parts.append(_record_table(result.added))

    if result.removed:
        parts.append(f'<h2 class="removed">Removed ({len(result.removed)})</h2>')
        parts.append(_record_table(result.removed))

    if result.modified:
        parts.append(f'<h2 class="modified">Modified ({len(result.modified)})</h2>')
        for old_rec, new_rec in result.modified[:200]:
            name = _esc(new_rec.full_name or new_rec.editor_id or new_rec.form_id_hex)
            icon = _html_icon(new_rec.form_id, icon_map)
            parts.append(f"<h3>{icon} {name} ({new_rec.form_id_hex})</h3>")
            changes = result.field_changes.get(new_rec.form_id, [])
            if changes:
                parts.append('<table class="change-table"><tr><th>Field</th><th>Old</th><th>New</th></tr>')
                for c in changes:
                    parts.append(f"<tr><td>{_esc(c.field_name)}</td><td>{_esc(c.old_value)}</td><td>{_esc(c.new_value)}</td></tr>")
                parts.append("</table>")

    title = f"Diff: {old_snap.label} \u2192 {new_snap.label}"
    return html_wrap(title, "\n".join(parts))
