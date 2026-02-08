"""Click CLI for Fallout 76 datamining tool."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import click

from fo76datamine.config import derive_ba2_path, derive_db_path
from fo76datamine.profiles import (
    load_config,
    profile_name_for_esm,
    resolve_esm,
    resolve_profile_esm,
    save_config,
    validate_profile_name,
    Config,
    Profile,
    get_config_path,
)


class Context:
    """Holds resolved paths derived from --esm / --profile / config."""

    def __init__(self, esm: Path | None = None, profile: str | None = None):
        self._explicit_esm = esm
        self._profile_name = profile
        self._resolved_esm: Path | None = None
        self._resolved_profile: str | None = None
        self._resolved = False

    def _resolve(self):
        if not self._resolved:
            self._resolved_esm = resolve_esm(self._explicit_esm, self._profile_name)
            # Determine effective profile name
            if self._profile_name is not None:
                self._resolved_profile = self._profile_name
            elif self._explicit_esm is not None:
                self._resolved_profile = profile_name_for_esm(self._explicit_esm)
            else:
                config = load_config()
                self._resolved_profile = config.default_profile or "default"
            self._resolved = True

    @property
    def esm(self) -> Path:
        self._resolve()
        return self._resolved_esm  # type: ignore[return-value]

    @property
    def profile_name(self) -> str:
        self._resolve()
        return self._resolved_profile  # type: ignore[return-value]

    @property
    def ba2(self) -> Path:
        return derive_ba2_path(self.esm)

    @property
    def db(self) -> Path:
        return derive_db_path(self.profile_name)


pass_ctx = click.make_pass_decorator(Context)


def _extract_icons_for_form_ids(
    esm_path: Path,
    form_ids: list[int],
    output_dir: Path,
    max_size: int = 128,
) -> dict[int, Optional[str]]:
    """Extract icons for a list of form_ids, printing progress."""
    if not form_ids:
        return {}

    from fo76datamine.ba2.icons import IconExtractor

    click.echo("Extracting item icons...", nl=False)
    t0 = time.perf_counter()
    extractor = IconExtractor(esm_path)
    icon_map = extractor.extract_icons(form_ids, output_dir, max_size=max_size)
    elapsed = time.perf_counter() - t0
    count = sum(1 for v in icon_map.values() if v is not None)
    click.echo(f" {count} icons in {elapsed:.1f}s")
    return icon_map


@click.group()
@click.option(
    "--esm", required=False, default=None,
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    help="Path to SeventySix.esm (optional if profiles configured)",
)
@click.option(
    "--profile", "-p", default=None, type=str,
    help="Named profile to use (from fo76dm init)",
)
@click.version_option(package_name="fo76datamine")
@click.pass_context
def cli(ctx, esm: Optional[Path], profile: Optional[str]):
    """fo76dm - Fallout 76 Datamining Tool.

    Parse SeventySix.esm, store versioned snapshots, and compare
    game updates to detect new items, stat changes, and unreleased content.
    """
    ctx.ensure_object(dict)
    ctx.obj = Context(esm=esm, profile=profile)


@cli.command()
def init():
    """Set up config profiles for ESM paths (interactive)."""
    config = load_config()

    # Show existing profiles
    if config.profiles:
        click.echo("Current profiles:")
        for name, p in config.profiles.items():
            default_marker = " (default)" if name == config.default_profile else ""
            click.echo(f"  {name}: {p.esm}{default_marker}")
        click.echo()
        if not click.confirm("Overwrite existing configuration?", default=False):
            click.echo("Aborted.")
            return
        config = Config()

    click.echo("Set up fo76dm profiles. Each profile stores a path to SeventySix.esm.\n")

    while True:
        # Prompt profile name
        default_name = "default" if not config.profiles else None
        name = click.prompt("Profile name", default=default_name).strip()
        if not validate_profile_name(name):
            click.echo(f"Invalid profile name '{name}'. Use letters, digits, hyphens, underscores.")
            continue

        # Prompt ESM path
        while True:
            esm_str = click.prompt("Path to SeventySix.esm").strip().strip('"').strip("'")
            esm_path = Path(esm_str)
            if esm_path.exists() and esm_path.is_file():
                break
            click.echo(f"File not found: {esm_path}")
            click.echo("Please enter the full path to SeventySix.esm.")

        config.profiles[name] = Profile(name=name, esm=esm_path)

        # Default profile
        if len(config.profiles) == 1:
            config.default_profile = name
        else:
            if click.confirm(f"Set '{name}' as the default profile?", default=False):
                config.default_profile = name

        if not click.confirm("\nAdd another profile?", default=False):
            break
        click.echo()

    # Ensure there's a default
    if config.default_profile is None and config.profiles:
        config.default_profile = next(iter(config.profiles))

    saved_path = save_config(config)
    click.echo(f"\nConfig saved to {saved_path}\n")

    # Summary
    click.echo("Profiles:")
    for name, p in config.profiles.items():
        default_marker = " (default)" if name == config.default_profile else ""
        click.echo(f"  {name}: {p.esm}{default_marker}")

    click.echo("\nExample commands:")
    click.echo("  fo76dm snapshot")
    click.echo("  fo76dm list")
    if len(config.profiles) > 1:
        other = [n for n in config.profiles if n != config.default_profile]
        if other:
            click.echo(f"  fo76dm diff --latest --vs {other[0]}")
    click.echo("  fo76dm --esm <path> snapshot   (override profile)")


@cli.command()
@click.option("--label", "-l", default=None, help="Label for this snapshot (default: auto-generated)")
@click.option("--full", is_flag=True, help="Store raw subrecord data (increases DB size significantly)")
@pass_ctx
def snapshot(ctx: Context, label: Optional[str], full: bool):
    """Parse ESM + strings and create a versioned snapshot."""
    from fo76datamine.db.store import Store
    from fo76datamine.esm.reader import ESMReader
    from fo76datamine.strings.loader import StringTable

    esm = ctx.esm
    ba2 = ctx.ba2
    db = ctx.db

    click.echo(f"ESM: {esm} ({esm.stat().st_size / 1024 / 1024:.0f} MB)")
    click.echo(f"BA2: {ba2.name}")
    click.echo(f"DB:  {db}")

    if label is None:
        from datetime import datetime
        label = f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    store = Store(db)

    # Create snapshot record
    snapshot_id = store.create_snapshot(label, esm)
    click.echo(f"\nSnapshot #{snapshot_id}: {label}")

    # Parse ESM
    click.echo("\nParsing ESM records...", nl=False)
    t0 = time.perf_counter()
    reader = ESMReader(esm)
    records = reader.parse_all()
    click.echo(f" {len(records):,} records in {time.perf_counter() - t0:.1f}s")

    # Load strings
    click.echo("Loading string tables...", nl=False)
    t0 = time.perf_counter()
    strings = StringTable()
    strings.load_from_ba2(ba2)
    click.echo(f" {strings.count:,} strings in {time.perf_counter() - t0:.2f}s")

    # Resolve full names and build DB rows
    click.echo("Building database rows...", nl=False)
    t0 = time.perf_counter()
    db_rows = []
    keyword_rows = []
    decoded_rows = []
    subrecord_rows = []

    for rec in records:
        # Resolve localized name
        full_name = None
        full_name_id = rec.full_name_id
        if full_name_id is not None:
            full_name = strings.lookup(full_name_id)

        # Resolve description
        desc_text = None
        desc_id = rec.desc_id
        if desc_id is not None:
            desc_text = strings.lookup(desc_id)

        db_rows.append((
            rec.form_id,
            rec.type,
            rec.editor_id,
            full_name,
            full_name_id,
            desc_text,
            desc_id,
            rec.data_hash(),
            rec.flags,
            rec.data_size,
        ))

        # Collect keywords
        if rec.type == "KYWD" and rec.editor_id:
            keyword_rows.append((rec.form_id, rec.editor_id))

        # Store raw subrecords if --full
        if full:
            for idx, sub in enumerate(rec.subrecords):
                subrecord_rows.append((rec.form_id, sub.type, idx, sub.data))

    click.echo(f" done in {time.perf_counter() - t0:.1f}s")

    # Batch insert into DB
    click.echo("Writing to database...", nl=False)
    t0 = time.perf_counter()

    # Insert in batches of 50K for memory efficiency
    batch_size = 50000
    for i in range(0, len(db_rows), batch_size):
        store.insert_records(snapshot_id, db_rows[i:i + batch_size])

    if keyword_rows:
        store.insert_keywords(snapshot_id, keyword_rows)

    # Insert strings
    string_rows = [(sid, text, "") for sid, text in strings.strings.items()]
    for i in range(0, len(string_rows), batch_size):
        store.insert_strings(snapshot_id, string_rows[i:i + batch_size])

    if subrecord_rows:
        for i in range(0, len(subrecord_rows), batch_size):
            store.insert_subrecords(snapshot_id, subrecord_rows[i:i + batch_size])

    store.update_snapshot_counts(snapshot_id, len(db_rows), strings.count, full)
    click.echo(f" done in {time.perf_counter() - t0:.1f}s")

    # Decode fields for key record types
    click.echo("Decoding type-specific fields...", nl=False)
    t0 = time.perf_counter()
    try:
        from fo76datamine.esm.decoders import decode_all_records
        decoded_rows = decode_all_records(records, strings)
        if decoded_rows:
            for i in range(0, len(decoded_rows), batch_size):
                store.insert_decoded_fields(snapshot_id, decoded_rows[i:i + batch_size])
        click.echo(f" {len(decoded_rows):,} fields in {time.perf_counter() - t0:.1f}s")
    except ImportError:
        click.echo(" skipped (decoders not yet implemented)")

    store.close()

    db_size = db.stat().st_size / 1024 / 1024
    click.echo(f"\nSnapshot #{snapshot_id} complete. DB size: {db_size:.1f} MB")


@cli.command("list")
@pass_ctx
def list_snapshots(ctx: Context):
    """List all snapshots."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)
    snapshots = store.list_snapshots()
    store.close()

    if not snapshots:
        click.echo("No snapshots found. Run 'fo76dm snapshot' first.")
        return

    click.echo(f"{'ID':>4}  {'Label':<30}  {'Created':<20}  {'Records':>10}  {'Strings':>10}  {'ESM Hash':<16}")
    click.echo("-" * 100)
    for s in snapshots:
        click.echo(
            f"{s.id:>4}  {s.label:<30}  {s.created_at:<20}  {s.record_count:>10,}  "
            f"{s.string_count:>10,}  {s.esm_hash[:16]}"
        )


@cli.command()
@click.option("--latest", is_flag=True, help="Compare the two most recent snapshots")
@click.option("--old", "old_id", type=int, help="Old snapshot ID")
@click.option("--new", "new_id", type=int, help="New snapshot ID")
@click.option("--type", "record_type", help="Filter by record type (e.g., WEAP)")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown", "html"]), default="text")
@click.option("--other-esm", "other_esm",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None,
              help="Path to a second ESM for cross-database diff (new snapshots come from this DB)")
@click.option("--vs", "vs_profile", default=None, type=str,
              help="Profile name for cross-database diff (alternative to --other-esm)")
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Write diff output to a file instead of stdout")
@click.option("--icons/--no-icons", default=True,
              help="Extract item icons to disk (default: enabled)")
@pass_ctx
def diff(ctx: Context, latest: bool, old_id: Optional[int], new_id: Optional[int],
         record_type: Optional[str], fmt: str, other_esm: Optional[Path],
         vs_profile: Optional[str], output_path: Optional[str], icons: bool):
    """Compare two snapshots to find added/removed/modified records."""
    from fo76datamine.db.store import Store
    from fo76datamine.diff.engine import DiffEngine
    from fo76datamine.diff.report import format_diff

    if vs_profile is not None and other_esm is not None:
        raise click.UsageError("Cannot use both --vs and --other-esm. Choose one.")

    if vs_profile is not None:
        other_esm = resolve_profile_esm(vs_profile)

    store = Store(ctx.db)
    new_store = None

    if other_esm is not None:
        if vs_profile is not None:
            other_db = derive_db_path(vs_profile)
        else:
            other_db = derive_db_path(profile_name_for_esm(other_esm))
        new_store = Store(other_db)

    # The store used for "new" snapshot lookups
    ns = new_store or store

    if latest:
        if new_store is not None:
            # Cross-DB: latest from each database
            old_snap = store.get_latest_snapshot()
            new_snap = ns.get_latest_snapshot()
            if old_snap is None:
                click.echo("No snapshots in main database. Run 'fo76dm snapshot' first.")
                store.close()
                ns.close()
                return
            if new_snap is None:
                click.echo("No snapshots in --other-esm database. Run 'fo76dm snapshot' with that ESM first.")
                store.close()
                ns.close()
                return
        else:
            old_snap, new_snap = store.get_two_latest_snapshots()
            if old_snap is None or new_snap is None:
                click.echo("Need at least 2 snapshots. Run 'fo76dm snapshot' again after a game update.")
                store.close()
                return
        old_id, new_id = old_snap.id, new_snap.id
    elif old_id is None or new_id is None:
        click.echo("Specify --latest or both --old and --new snapshot IDs.")
        store.close()
        if new_store is not None:
            new_store.close()
        return

    old_snap = store.get_snapshot(old_id)
    new_snap = ns.get_snapshot(new_id)
    if not old_snap or not new_snap:
        click.echo("Snapshot not found.")
        store.close()
        if new_store is not None:
            new_store.close()
        return

    # Check if same ESM version (skip for cross-DB since they're expected to differ)
    if new_store is None and old_snap.esm_hash == new_snap.esm_hash:
        click.echo(f"Warning: Both snapshots have the same ESM hash ({old_snap.esm_hash[:16]}...).")
        click.echo("The game data hasn't changed between these snapshots.")
        if not click.confirm("Continue anyway?"):
            store.close()
            return

    click.echo(f"Comparing snapshot #{old_id} ({old_snap.label}) vs #{new_id} ({new_snap.label})...")

    engine = DiffEngine(store, new_store=new_store)
    result = engine.compare(old_id, new_id, record_type=record_type)

    # Extract icons when writing to file (any format)
    icon_map = None
    if icons and output_path:
        out_dir = Path(output_path).parent
        # Collect all form_ids from diff result
        all_fids = []
        # Added + modified use new snapshot
        new_fids = [r.form_id for r in result.added]
        new_fids += [new_rec.form_id for _, new_rec in result.modified]
        # Removed use old snapshot
        old_fids = [r.form_id for r in result.removed]

        icon_map = {}
        # For cross-DB diffs, new items come from the other ESM's BA2 archives
        new_esm = other_esm if other_esm is not None else ctx.esm
        if new_fids:
            icon_map.update(_extract_icons_for_form_ids(
                new_esm, new_fids, out_dir))
        if old_fids:
            icon_map.update(_extract_icons_for_form_ids(
                ctx.esm, old_fids, out_dir))

    output = format_diff(result, store, old_id, new_id, fmt=fmt,
                         new_store=new_store, icon_map=icon_map)
    if output_path:
        Path(output_path).write_text(output, encoding="utf-8")
        click.echo(f"Diff written to {output_path}")
    else:
        click.echo(output)

    store.close()
    if new_store is not None:
        new_store.close()


@cli.command()
@click.argument("query")
@click.option("--type", "record_type", help="Filter by record type (e.g., WEAP)")
@click.option("--edid", help="Filter by editor ID pattern (supports * wildcards)")
@click.option("--snapshot", "snapshot_id", type=int, help="Snapshot ID (default: latest)")
@click.option("--format", "fmt", type=click.Choice(["text", "markdown", "html"]), default="text")
@click.option("--icons/--no-icons", default=True,
              help="Extract item icons to disk (default: enabled)")
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Write output to a file instead of stdout")
@pass_ctx
def search(ctx: Context, query: str, record_type: Optional[str], edid: Optional[str],
           snapshot_id: Optional[int], fmt: str, icons: bool,
           output_path: Optional[str]):
    """Search records by name, editor ID, or FormID."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)

    if snapshot_id is None:
        snap = store.get_latest_snapshot()
        if snap is None:
            click.echo("No snapshots found.")
            store.close()
            return
        snapshot_id = snap.id

    results = store.search_records(snapshot_id, query, record_type=record_type, edid_pattern=edid)

    if not results:
        click.echo(f"No records found matching '{query}'.")
        store.close()
        return

    # Extract icons when writing to file (any format)
    icon_map = None
    if icons and output_path:
        out_dir = Path(output_path).parent
        form_ids = [r.form_id for r in results]
        icon_map = _extract_icons_for_form_ids(
            ctx.esm, form_ids, out_dir)

    if fmt == "markdown":
        lines = _format_search_markdown(results, store, snapshot_id, icon_map)
        output = "\n".join(lines)
    elif fmt == "html":
        output = _format_search_html(results, store, snapshot_id, icon_map)
    else:
        output = None

    if output is not None:
        if output_path:
            Path(output_path).write_text(output, encoding="utf-8")
            click.echo(f"Search results written to {output_path}")
        else:
            click.echo(output)
    else:
        click.echo(f"Found {len(results)} records:\n")
        click.echo(f"{'FormID':<12}  {'Type':<6}  {'Editor ID':<40}  {'Name'}")
        click.echo("-" * 90)
        for rec in results:
            name = rec.full_name or ""
            edid_str = rec.editor_id or ""
            click.echo(f"{rec.form_id_hex:<12}  {rec.record_type:<6}  {edid_str:<40}  {name}")

        # Show decoded fields for results
        from fo76datamine.db.resolve import FormIDResolver
        resolver = FormIDResolver(store, snapshot_id)
        for rec in results[:10]:
            fields = store.get_decoded_fields(snapshot_id, rec.form_id)
            if fields:
                click.echo(f"\n  {rec.form_id_hex} decoded fields:")
                for f in fields:
                    click.echo(f"    {f.field_name}: {resolver.format_field_value(f)}")

    store.close()


def _format_search_markdown(results, store, snapshot_id, icon_map):
    """Format search results as markdown with optional icons."""
    lines = []
    has_icons = icon_map is not None and len(icon_map) > 0

    lines.append(f"# Search Results ({len(results)} records)")
    lines.append("")
    if has_icons:
        lines.append("| Icon | FormID | Type | Editor ID | Name |")
        lines.append("|------|--------|------|-----------|------|")
    else:
        lines.append("| FormID | Type | Editor ID | Name |")
        lines.append("|--------|------|-----------|------|")

    for rec in results:
        if has_icons:
            path = icon_map.get(rec.form_id)
            icon = f"![icon]({path})" if path else ""
            lines.append(f"| {icon} | {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        else:
            lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")

    # Decoded fields for first 10 results
    from fo76datamine.db.resolve import FormIDResolver
    resolver = FormIDResolver(store, snapshot_id)
    for rec in results[:10]:
        fields = store.get_decoded_fields(snapshot_id, rec.form_id)
        if fields:
            lines.append("")
            lines.append(f"### {rec.full_name or rec.editor_id or rec.form_id_hex} ({rec.form_id_hex})")
            lines.append("| Field | Value |")
            lines.append("|-------|-------|")
            for f in fields:
                if f.field_name not in ("icon", "icon_small"):
                    lines.append(f"| {f.field_name} | {resolver.format_field_value(f)} |")

    return lines


def _format_search_html(results, store, snapshot_id, icon_map):
    """Format search results as HTML with inline icons."""
    from fo76datamine.diff.report import _esc, _html_icon, _badge, html_wrap

    has_icons = icon_map is not None and any(v for v in icon_map.values())
    parts = []
    parts.append(f"<h1>Search Results ({len(results)} records)</h1>")

    def _sortable_th(label):
        return f'<th data-sortable>{label}<span class="sort-arrow"></span></th>'

    icon_hdr = "<th>Icon</th>" if has_icons else ""
    parts.append('<div class="filterable" id="tbl-search">')
    parts.append('<div class="table-filter"><input type="text" placeholder="Filter rows...">'
                 '<span class="count"></span></div>')
    parts.append(f"<table><thead><tr>{icon_hdr}"
                 f"{_sortable_th('FormID')}{_sortable_th('Type')}"
                 f"{_sortable_th('Editor ID')}{_sortable_th('Name')}"
                 f"</tr></thead><tbody>")
    for rec in results:
        icon_td = f"<td>{_html_icon(rec.form_id, icon_map)}</td>" if has_icons else ""
        parts.append(
            f"<tr>{icon_td}<td>{rec.form_id_hex}</td><td>{_badge(rec.record_type)}</td>"
            f"<td>{_esc(rec.editor_id)}</td><td>{_esc(rec.full_name)}</td></tr>"
        )
    parts.append("</tbody></table></div>")

    # Decoded fields for first 10 as collapsible details
    from fo76datamine.db.resolve import FormIDResolver
    resolver = FormIDResolver(store, snapshot_id)
    for idx, rec in enumerate(results[:10]):
        fields = store.get_decoded_fields(snapshot_id, rec.form_id)
        if fields:
            name = _esc(rec.full_name or rec.editor_id or rec.form_id_hex)
            icon = _html_icon(rec.form_id, icon_map) if has_icons else ""
            parts.append(f'<h3 class="section-header">{icon} {name} ({rec.form_id_hex})</h3>')
            parts.append(f'<div class="section-body">')
            parts.append('<table class="change-table"><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>')
            for f in fields:
                if f.field_name not in ("icon", "icon_small"):
                    parts.append(f"<tr><td>{_esc(f.field_name)}</td><td>{_esc(resolver.format_field_value(f))}</td></tr>")
            parts.append("</tbody></table></div>")

    return html_wrap("Search Results", "\n".join(parts))


@cli.command()
@click.argument("form_id_str")
@click.option("--snapshot", "snapshot_id", type=int, help="Snapshot ID (default: latest)")
@click.option("--expand", is_flag=True, help="Expand leveled list entries into a tree")
@pass_ctx
def show(ctx: Context, form_id_str: str, snapshot_id: Optional[int], expand: bool):
    """Show full record detail for a FormID (hex or decimal)."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)

    if snapshot_id is None:
        snap = store.get_latest_snapshot()
        if snap is None:
            click.echo("No snapshots found.")
            store.close()
            return
        snapshot_id = snap.id

    try:
        form_id = int(form_id_str, 16) if form_id_str.startswith("0x") else int(form_id_str, 0)
    except ValueError:
        click.echo(f"Invalid FormID: {form_id_str}")
        store.close()
        return

    rec = store.get_record(snapshot_id, form_id)
    if rec is None:
        click.echo(f"Record {form_id_str} not found in snapshot #{snapshot_id}.")
        store.close()
        return

    click.echo(f"Record {rec.form_id_hex}")
    click.echo(f"  Type:       {rec.record_type}")
    click.echo(f"  Editor ID:  {rec.editor_id or '(none)'}")
    click.echo(f"  Name:       {rec.full_name or '(none)'}")
    if rec.desc_text:
        desc = rec.desc_text[:200] + "..." if len(rec.desc_text) > 200 else rec.desc_text
        click.echo(f"  Description:{desc}")
    click.echo(f"  Flags:      0x{rec.flags:08X}")
    click.echo(f"  Data Size:  {rec.data_size:,} bytes")
    click.echo(f"  Data Hash:  {rec.data_hash[:16]}...")

    # Show decoded fields
    fields = store.get_decoded_fields(snapshot_id, form_id)
    if fields:
        from fo76datamine.db.resolve import FormIDResolver
        resolver = FormIDResolver(store, snapshot_id)
        click.echo(f"\n  Decoded Fields:")
        for f in fields:
            display_val = resolver.format_field_value(f)
            click.echo(f"    {f.field_name:<25} = {display_val} ({f.field_type})")

    # Expand leveled list tree if requested
    if expand and rec.record_type in ("LVLI", "LVLN"):
        from fo76datamine.db.leveled_list import expand_leveled_list, format_tree_text
        tree = expand_leveled_list(store, snapshot_id, form_id)
        if tree:
            click.echo(f"\n  Leveled List Tree:")
            click.echo(format_tree_text(tree))

    store.close()


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["text", "markdown", "html"]), default="text")
@click.option("--icons/--no-icons", default=True,
              help="Extract item icons to disk (default: enabled)")
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Write output to a file instead of stdout")
@pass_ctx
def unreleased(ctx: Context, fmt: str, icons: bool, output_path: Optional[str]):
    """Scan for unreleased content using heuristics."""
    from fo76datamine.db.store import Store
    from fo76datamine.diff.filters import find_unreleased

    store = Store(ctx.db)
    snap = store.get_latest_snapshot()
    if snap is None:
        click.echo("No snapshots found.")
        store.close()
        return

    click.echo(f"Scanning snapshot #{snap.id} ({snap.label}) for unreleased content...\n")
    results = find_unreleased(store, snap.id)

    # Extract icons when writing to file (any format)
    icon_map = None
    if icons and output_path:
        out_dir = Path(output_path).parent
        all_fids = []
        for items in results.values():
            all_fids.extend(r.form_id for r in items)
        if all_fids:
            icon_map = _extract_icons_for_form_ids(
                ctx.esm, all_fids, out_dir)

    if fmt == "markdown":
        lines = _format_unreleased_markdown(results, icon_map)
        output = "\n".join(lines)
        if output_path:
            Path(output_path).write_text(output, encoding="utf-8")
            click.echo(f"Unreleased content written to {output_path}")
        else:
            click.echo(output)
    elif fmt == "html":
        output = _format_unreleased_html(results, icon_map)
        if output_path:
            Path(output_path).write_text(output, encoding="utf-8")
            click.echo(f"Unreleased content written to {output_path}")
        else:
            click.echo(output)
    else:
        for category, items in results.items():
            if items:
                click.echo(f"\n{'=' * 60}")
                click.echo(f"  {category} ({len(items)} items)")
                click.echo(f"{'=' * 60}")
                for rec in items[:50]:
                    name = rec.full_name or ""
                    edid = rec.editor_id or ""
                    click.echo(f"  {rec.form_id_hex}  {rec.record_type:<6}  {edid:<45}  {name}")
                if len(items) > 50:
                    click.echo(f"  ... and {len(items) - 50} more")

    store.close()


def _format_unreleased_markdown(results, icon_map):
    """Format unreleased content as markdown with optional icons."""
    lines = []
    has_icons = icon_map is not None and len(icon_map) > 0

    lines.append("# Unreleased Content")
    lines.append("")

    # Summary table
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for category, items in results.items():
        if items:
            lines.append(f"| {category} | {len(items)} |")
    lines.append("")

    for category, items in results.items():
        if not items:
            continue
        lines.append(f"## {category} ({len(items)} items)")
        if has_icons:
            lines.append("| Icon | FormID | Type | Editor ID | Name |")
            lines.append("|------|--------|------|-----------|------|")
        else:
            lines.append("| FormID | Type | Editor ID | Name |")
            lines.append("|--------|------|-----------|------|")

        for rec in items[:100]:
            if has_icons:
                path = icon_map.get(rec.form_id)
                icon = f"![icon]({path})" if path else ""
                lines.append(f"| {icon} | {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
            else:
                lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        lines.append("")

    return lines


def _format_unreleased_html(results, icon_map):
    """Format unreleased content as HTML with inline icons."""
    from fo76datamine.diff.report import _esc, _html_icon, _badge, html_wrap

    has_icons = icon_map is not None and any(v for v in icon_map.values())
    parts = []

    def _sortable_th(label):
        return f'<th data-sortable>{label}<span class="sort-arrow"></span></th>'

    # --- TOC sidebar ---
    categories_with_items = [(cat, items) for cat, items in results.items() if items]
    toc = ['<nav class="toc"><h3>Contents</h3>']
    toc.append('<a href="#summary">Summary</a>')
    for cat, items in categories_with_items:
        safe_id = cat.replace(" ", "-").lower()
        toc.append(f'<a href="#cat-{safe_id}">{_esc(cat)} ({len(items)})</a>')
    toc.append('</nav>')
    parts.append("\n".join(toc))

    parts.append('<h1 id="summary">Unreleased Content</h1>')

    # Summary
    parts.append('<div class="summary">')
    total = sum(len(items) for items in results.values())
    parts.append(f'<div class="stat"><div class="label">Total Items</div><div class="value">{total}</div></div>')
    for category, items in categories_with_items:
        parts.append(f'<div class="stat"><div class="label">{_esc(category)}</div><div class="value">{len(items)}</div></div>')
    parts.append('</div>')

    for cat_idx, (category, items) in enumerate(categories_with_items):
        safe_id = category.replace(" ", "-").lower()
        parts.append(f'<h2 class="section-header" id="cat-{safe_id}">{_esc(category)} ({len(items)} items)</h2>')
        parts.append('<div class="section-body">')

        limit = 500
        truncated = len(items) > limit
        display = items[:limit]

        icon_hdr = "<th>Icon</th>" if has_icons else ""
        parts.append(f'<div class="filterable" id="tbl-unrel-{cat_idx}">')
        parts.append('<div class="table-filter"><input type="text" placeholder="Filter rows...">'
                     '<span class="count"></span></div>')
        if truncated:
            parts.append(f'<div class="truncation-notice">Showing {limit} of {len(items)} records.</div>')
        parts.append(f"<table><thead><tr>{icon_hdr}"
                     f"{_sortable_th('FormID')}{_sortable_th('Type')}"
                     f"{_sortable_th('Editor ID')}{_sortable_th('Name')}"
                     f"</tr></thead><tbody>")
        for rec in display:
            icon_td = f"<td>{_html_icon(rec.form_id, icon_map)}</td>" if has_icons else ""
            parts.append(
                f"<tr>{icon_td}<td>{rec.form_id_hex}</td><td>{_badge(rec.record_type)}</td>"
                f"<td>{_esc(rec.editor_id)}</td><td>{_esc(rec.full_name)}</td></tr>"
            )
        parts.append("</tbody></table></div>")
        parts.append('</div>')

    return html_wrap("Unreleased Content", "\n".join(parts))


@cli.command()
@pass_ctx
def stats(ctx: Context):
    """Show record type counts and database size."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)
    snap = store.get_latest_snapshot()
    if snap is None:
        click.echo("No snapshots found.")
        store.close()
        return

    click.echo(f"Snapshot #{snap.id}: {snap.label} ({snap.created_at})")
    click.echo(f"Records: {snap.record_count:,}  Strings: {snap.string_count:,}")
    click.echo(f"DB size: {store.get_db_size() / 1024 / 1024:.1f} MB\n")

    counts = store.get_record_type_counts(snap.id)
    click.echo(f"{'Type':<8}  {'Count':>8}")
    click.echo("-" * 18)
    for rtype, count in counts:
        click.echo(f"{rtype:<8}  {count:>8,}")

    store.close()


@cli.group("strings")
def strings_group():
    """String table operations."""


@strings_group.command("search")
@click.argument("query")
@click.option("--snapshot", "snapshot_id", type=int, help="Snapshot ID (default: latest)")
@click.pass_obj
def strings_search(ctx: Context, query: str, snapshot_id: Optional[int]):
    """Search localized strings."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)

    if snapshot_id is None:
        snap = store.get_latest_snapshot()
        if snap is None:
            click.echo("No snapshots found.")
            store.close()
            return
        snapshot_id = snap.id

    results = store.search_strings(snapshot_id, query)

    if not results:
        click.echo(f"No strings found matching '{query}'.")
        store.close()
        return

    click.echo(f"Found {len(results)} strings:\n")
    for sid, text in results:
        display = text[:100] + "..." if len(text) > 100 else text
        click.echo(f"  0x{sid:08X}: {display}")

    store.close()


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "json", "markdown", "html"]), required=True)
@click.option("--type", "record_type", help="Record type to export (e.g., WEAP)")
@click.option("--snapshot", "snapshot_id", type=int, help="Snapshot ID (default: latest)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option("--icons/--no-icons", default=True,
              help="Extract item icons to disk (default: enabled)")
@pass_ctx
def export(ctx: Context, fmt: str, record_type: Optional[str], snapshot_id: Optional[int],
           output: Optional[str], icons: bool):
    """Export records as CSV, JSON, or markdown."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)

    if snapshot_id is None:
        snap = store.get_latest_snapshot()
        if snap is None:
            click.echo("No snapshots found.")
            store.close()
            return
        snapshot_id = snap.id

    # Extract icons when writing to file (any format)
    icon_map = None
    if icons and output:
        from fo76datamine.db.models import DbRecord
        if record_type:
            recs = store.get_records_by_type(snapshot_id, record_type)
        else:
            cur = store.conn.execute(
                "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
                "desc_text, desc_id, data_hash, flags, data_size "
                "FROM records WHERE snapshot_id=? ORDER BY record_type, form_id",
                (snapshot_id,),
            )
            recs = [DbRecord(*row) for row in cur.fetchall()]
        form_ids = [r.form_id for r in recs]
        icon_map = _extract_icons_for_form_ids(ctx.esm, form_ids, Path(output).parent)
    else:
        recs = None

    if fmt == "csv":
        from fo76datamine.export.csv_export import export_csv
        data = export_csv(store, snapshot_id, record_type)
    elif fmt == "json":
        from fo76datamine.export.json_export import export_json
        data = export_json(store, snapshot_id, record_type)
    elif fmt == "html":
        data = _export_html(store, snapshot_id, record_type, icon_map, recs)
    else:  # markdown
        data = _export_markdown(store, snapshot_id, record_type, icon_map, recs)

    if output:
        Path(output).write_text(data, encoding="utf-8")
        click.echo(f"Exported to {output}")
    else:
        click.echo(data)

    store.close()


def _get_export_records(store, snapshot_id, record_type):
    """Fetch records for export if not already loaded."""
    from fo76datamine.db.models import DbRecord
    if record_type:
        return store.get_records_by_type(snapshot_id, record_type)
    cur = store.conn.execute(
        "SELECT snapshot_id, form_id, record_type, editor_id, full_name, full_name_id, "
        "desc_text, desc_id, data_hash, flags, data_size "
        "FROM records WHERE snapshot_id=? ORDER BY record_type, form_id",
        (snapshot_id,),
    )
    return [DbRecord(*row) for row in cur.fetchall()]


def _export_markdown(store, snapshot_id, record_type, icon_map, records=None):
    """Export records as markdown with optional icons."""
    if records is None:
        records = _get_export_records(store, snapshot_id, record_type)

    has_icons = icon_map is not None and len(icon_map) > 0
    lines = []
    title = f"Export: {record_type}" if record_type else "Export: All Records"
    lines.append(f"# {title}")
    lines.append(f"")
    lines.append(f"Total: {len(records)} records")
    lines.append("")

    if has_icons:
        lines.append("| Icon | FormID | Type | Editor ID | Name |")
        lines.append("|------|--------|------|-----------|------|")
    else:
        lines.append("| FormID | Type | Editor ID | Name |")
        lines.append("|--------|------|-----------|------|")

    for rec in records:
        if has_icons:
            path = icon_map.get(rec.form_id)
            icon = f"![icon]({path})" if path else ""
            lines.append(f"| {icon} | {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")
        else:
            lines.append(f"| {rec.form_id_hex} | {rec.record_type} | {rec.editor_id or ''} | {rec.full_name or ''} |")

    return "\n".join(lines)


def _export_html(store, snapshot_id, record_type, icon_map, records=None):
    """Export records as HTML with inline icons."""
    from fo76datamine.diff.report import _esc, _html_icon, _badge, html_wrap

    if records is None:
        records = _get_export_records(store, snapshot_id, record_type)

    has_icons = icon_map is not None and any(v for v in icon_map.values())
    parts = []
    title = f"Export: {record_type}" if record_type else "Export: All Records"
    parts.append(f"<h1>{_esc(title)}</h1>")
    parts.append(f"<p>Total: {len(records)} records</p>")

    def _sortable_th(label):
        return f'<th data-sortable>{label}<span class="sort-arrow"></span></th>'

    limit = 5000
    truncated = len(records) > limit
    display = records[:limit]

    icon_hdr = "<th>Icon</th>" if has_icons else ""
    parts.append('<div class="filterable" id="tbl-export">')
    parts.append('<div class="table-filter"><input type="text" placeholder="Filter rows...">'
                 '<span class="count"></span></div>')
    if truncated:
        parts.append(f'<div class="truncation-notice">Showing {limit} of {len(records)} records.</div>')
    parts.append(f"<table><thead><tr>{icon_hdr}"
                 f"{_sortable_th('FormID')}{_sortable_th('Type')}"
                 f"{_sortable_th('Editor ID')}{_sortable_th('Name')}"
                 f"</tr></thead><tbody>")
    for rec in display:
        icon_td = f"<td>{_html_icon(rec.form_id, icon_map)}</td>" if has_icons else ""
        parts.append(
            f"<tr>{icon_td}<td>{rec.form_id_hex}</td><td>{_badge(rec.record_type)}</td>"
            f"<td>{_esc(rec.editor_id)}</td><td>{_esc(rec.full_name)}</td></tr>"
        )
    parts.append("</tbody></table></div>")

    return html_wrap(title, "\n".join(parts))


@cli.command()
@click.option("--keep", type=int, default=5, help="Number of recent snapshots to keep")
@pass_ctx
def purge(ctx: Context, keep: int):
    """Delete old snapshots, keeping the N most recent."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)
    count = store.purge_old_snapshots(keep)
    store.close()

    if count:
        click.echo(f"Deleted {count} old snapshot(s). Kept {keep} most recent.")
    else:
        click.echo("Nothing to purge.")


@cli.command()
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@pass_ctx
def clear(ctx: Context, yes: bool):
    """Delete ALL snapshots and related data from the database."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)
    total = store.conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    if total == 0:
        click.echo("Database is already empty.")
        store.close()
        return

    if not yes:
        click.confirm(f"Delete all {total} snapshot(s)?", abort=True)

    count = store.clear_all_snapshots()
    store.close()
    click.echo(f"Deleted {count} snapshot(s).")


@cli.command()
@click.option("--filter", "-f", "filter_pattern", default=None,
              help="Path fragment or glob pattern (e.g. music, sound/fx/wpn/*.xwm)")
@click.option("--output", "-o", "output_dir", type=click.Path(path_type=Path),
              default=Path("./sounds"), help="Output directory (default: ./sounds)")
@click.option("--raw", is_flag=True, help="Skip xwm-to-wav conversion")
@click.option("--list-only", is_flag=True, help="List matching files without extracting")
@pass_ctx
def sounds(ctx: Context, filter_pattern: Optional[str], output_dir: Path,
           raw: bool, list_only: bool):
    """Extract sound files (.xwm, .fuz, .wav) from Sound BA2 archives."""
    from fo76datamine.ba2.sounds import SoundExtractor, check_ffmpeg

    extractor = SoundExtractor(ctx.esm)
    matches = extractor.list_sounds(filter_pattern)

    if not matches:
        click.echo("No sound files found.")
        return

    if list_only:
        click.echo(f"{'Size':>10}  Path")
        click.echo("-" * 70)
        for _reader, entry in matches:
            size_kb = entry.unpacked_size / 1024
            click.echo(f"{size_kb:>8.0f}KB  {entry.name}")
        click.echo(f"\n{len(matches)} sound file(s)")
        return

    convert = not raw
    if convert and not check_ffmpeg():
        click.echo("Warning: ffmpeg not found on PATH. Saving raw .xwm files (use --raw to suppress this warning).")
        convert = False

    def _progress(current: int, total: int) -> None:
        click.echo(f"\rExtracting sounds... {current}/{total}", nl=False)

    t0 = time.perf_counter()
    result = extractor.extract_sounds(
        output_dir, filter_pattern=filter_pattern, convert=convert,
        progress_callback=_progress,
    )
    elapsed = time.perf_counter() - t0

    click.echo()  # newline after progress
    click.echo(f"Extracted: {result.extracted}  Converted: {result.converted}  "
               f"Errors: {result.errors}  Time: {elapsed:.1f}s")


@cli.command()
@click.option("--filter", "-f", "filter_pattern", default=None,
              help="Path fragment or glob pattern (e.g. quest*, scripts/source/*.pex)")
@click.option("--output", "-o", "output_dir", type=click.Path(path_type=Path),
              default=Path("./scripts"), help="Output directory (default: ./scripts)")
@click.option("--list-only", is_flag=True, help="List matching files without extracting")
@pass_ctx
def scripts(ctx: Context, filter_pattern: Optional[str], output_dir: Path,
            list_only: bool):
    """Extract Papyrus .pex scripts from BA2 archives."""
    from fo76datamine.ba2.scripts import ScriptExtractor, parse_pex_header

    extractor = ScriptExtractor(ctx.esm)
    matches = extractor.list_scripts(filter_pattern)

    if not matches:
        click.echo("No script files found.")
        return

    if list_only:
        click.echo(f"{'Size':>10}  {'Source':<50}  Path")
        click.echo("-" * 100)
        for reader, entry in matches:
            size_kb = entry.unpacked_size / 1024
            # Try to parse header for source file info
            source = ""
            try:
                raw = reader.extract_file(entry)
                hdr = parse_pex_header(raw)
                if hdr and hdr.source_file:
                    source = hdr.source_file
            except Exception:
                pass
            click.echo(f"{size_kb:>8.0f}KB  {source:<50}  {entry.name}")
        click.echo(f"\n{len(matches)} script file(s)")
        return

    def _progress(current: int, total: int) -> None:
        click.echo(f"\rExtracting scripts... {current}/{total}", nl=False)

    t0 = time.perf_counter()
    result = extractor.extract_scripts(
        output_dir, filter_pattern=filter_pattern,
        progress_callback=_progress,
    )
    elapsed = time.perf_counter() - t0

    click.echo()  # newline after progress
    click.echo(f"Extracted: {result.extracted}  Errors: {result.errors}  Time: {elapsed:.1f}s")


@cli.command()
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Write output to a file instead of stdout")
@pass_ctx
def seq(ctx: Context, output_path: Optional[str]):
    """Parse SeventySix.seq and list auto-start quest FormIDs."""
    import struct as _struct

    from fo76datamine.db.store import Store

    seq_path = ctx.esm.parent / "SeventySix.seq"
    if not seq_path.exists():
        click.echo(f"SEQ file not found: {seq_path}")
        return

    data = seq_path.read_bytes()
    if len(data) < 4:
        click.echo("SEQ file is empty or too small.")
        return

    count = len(data) // 4
    form_ids = list(_struct.unpack(f"<{count}I", data[:count * 4]))

    click.echo(f"Found {count} auto-start quest FormIDs in {seq_path.name}\n")

    # Cross-reference with quest names from DB
    store = Store(ctx.db)
    snap = store.get_latest_snapshot()
    names: dict[int, str] = {}
    if snap:
        for fid in form_ids:
            rec = store.get_record(snap.id, fid)
            if rec:
                names[fid] = rec.full_name or rec.editor_id or ""

    lines = []
    click.echo(f"{'FormID':<12}  {'Name/Editor ID'}")
    click.echo("-" * 60)
    for fid in form_ids:
        name = names.get(fid, "")
        line = f"0x{fid:08X}  {name}"
        lines.append(line)
        click.echo(f"  {line}")

    if output_path:
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        click.echo(f"\nWritten to {output_path}")

    store.close()
