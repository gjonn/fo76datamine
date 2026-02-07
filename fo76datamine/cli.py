"""Click CLI for Fallout 76 datamining tool."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import click

from fo76datamine.config import derive_ba2_path, derive_db_path
from fo76datamine.profiles import (
    load_config,
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
        self._resolved = False

    def _resolve(self):
        if not self._resolved:
            self._resolved_esm = resolve_esm(self._explicit_esm, self._profile_name)
            self._resolved = True

    @property
    def esm(self) -> Path:
        self._resolve()
        return self._resolved_esm  # type: ignore[return-value]

    @property
    def ba2(self) -> Path:
        return derive_ba2_path(self.esm)

    @property
    def db(self) -> Path:
        return derive_db_path(self.esm)


pass_ctx = click.make_pass_decorator(Context)


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
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]), default="text")
@click.option("--other-esm", "other_esm",
              type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None,
              help="Path to a second ESM for cross-database diff (new snapshots come from this DB)")
@click.option("--vs", "vs_profile", default=None, type=str,
              help="Profile name for cross-database diff (alternative to --other-esm)")
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Write diff output to a file instead of stdout")
@pass_ctx
def diff(ctx: Context, latest: bool, old_id: Optional[int], new_id: Optional[int],
         record_type: Optional[str], fmt: str, other_esm: Optional[Path],
         vs_profile: Optional[str], output_path: Optional[str]):
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
        other_db = derive_db_path(other_esm)
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

    output = format_diff(result, store, old_id, new_id, fmt=fmt, new_store=new_store)
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
@pass_ctx
def search(ctx: Context, query: str, record_type: Optional[str], edid: Optional[str],
           snapshot_id: Optional[int]):
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

    click.echo(f"Found {len(results)} records:\n")
    click.echo(f"{'FormID':<12}  {'Type':<6}  {'Editor ID':<40}  {'Name'}")
    click.echo("-" * 90)
    for rec in results:
        name = rec.full_name or ""
        edid_str = rec.editor_id or ""
        click.echo(f"{rec.form_id_hex:<12}  {rec.record_type:<6}  {edid_str:<40}  {name}")

    # Show decoded fields for results
    for rec in results[:10]:
        fields = store.get_decoded_fields(snapshot_id, rec.form_id)
        if fields:
            click.echo(f"\n  {rec.form_id_hex} decoded fields:")
            for f in fields:
                click.echo(f"    {f.field_name}: {f.field_value}")

    store.close()


@cli.command()
@click.argument("form_id_str")
@click.option("--snapshot", "snapshot_id", type=int, help="Snapshot ID (default: latest)")
@pass_ctx
def show(ctx: Context, form_id_str: str, snapshot_id: Optional[int]):
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
        click.echo(f"\n  Decoded Fields:")
        for f in fields:
            click.echo(f"    {f.field_name:<25} = {f.field_value} ({f.field_type})")

    store.close()


@cli.command()
@pass_ctx
def unreleased(ctx: Context):
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
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), required=True)
@click.option("--type", "record_type", help="Record type to export (e.g., WEAP)")
@click.option("--snapshot", "snapshot_id", type=int, help="Snapshot ID (default: latest)")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@pass_ctx
def export(ctx: Context, fmt: str, record_type: Optional[str], snapshot_id: Optional[int],
           output: Optional[str]):
    """Export records as CSV or JSON."""
    from fo76datamine.db.store import Store

    store = Store(ctx.db)

    if snapshot_id is None:
        snap = store.get_latest_snapshot()
        if snap is None:
            click.echo("No snapshots found.")
            store.close()
            return
        snapshot_id = snap.id

    if fmt == "csv":
        from fo76datamine.export.csv_export import export_csv
        data = export_csv(store, snapshot_id, record_type)
    else:
        from fo76datamine.export.json_export import export_json
        data = export_json(store, snapshot_id, record_type)

    if output:
        Path(output).write_text(data, encoding="utf-8")
        click.echo(f"Exported to {output}")
    else:
        click.echo(data)

    store.close()


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