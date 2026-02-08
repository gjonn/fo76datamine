# fo76dm - Fallout 76 Datamining Tool

A Python CLI tool that parses Fallout 76's game data files (`SeventySix.esm` + localization BA2), stores all records in a versioned SQLite database, and compares snapshots between game updates to detect new items, stat changes, and unreleased content.

## Features

- **Full ESM parsing** - Parses all 478K+ datamineable records from SeventySix.esm in ~8 seconds (pure Python, no external Bethesda libraries)
- **String resolution** - Extracts and resolves 246K+ localized strings from the Localization BA2
- **Field decoding** - Decodes binary structs for weapons, armor, consumables, NPCs, quests, crafting recipes, ammo, and more into named fields (damage, weight, value, etc.)
- **Versioned snapshots** - Stores each parse in SQLite with SHA-256 hashes for change detection
- **Diff engine** - Compares snapshots to find added, removed, and modified records with field-level detail (e.g., "damage: 50.0 -> 65.0")
- **Unreleased content detection** - Heuristic scan for Atomic Shop items (ATX_), cut/test content (zzz_/CUT_/TEST_), high FormIDs, and disabled quests
- **Sound extraction** - Extracts `.xwm`, `.fuz`, and `.wav` audio from Sound BA2 archives, with optional xWMA-to-WAV conversion via ffmpeg
- **Item image extraction** - Extracts actual item textures from BA2 archives: workshop icons (3700+) and model diffuse textures via a NIF → BGSM → DDS pipeline
- **HTML output with inline images** - Dark-themed HTML reports with clickable icon thumbnails that expand to full resolution in a lightbox
- **Search** - Query by item name, editor ID, FormID, or record type
- **Export** - CSV, JSON, markdown, and HTML export with decoded fields

## Requirements

- Python 3.10+
- click (installed automatically)
- Pillow (installed automatically, used for DDS to PNG conversion)
- tomli (installed automatically for Python < 3.11, used for config file parsing)
- ffmpeg (optional, for xWMA-to-WAV sound conversion — install separately)

## Installation

```
cd fo76datamine
pip install -e .
```

## Quick Start

Run `fo76dm init` once to save your ESM path:

```
> fo76dm init
Set up fo76dm profiles. Each profile stores a path to SeventySix.esm.

Profile name [default]:
Path to SeventySix.esm: D:\Fallout76\Data\SeventySix.esm

Add another profile? [y/N]: y

Profile name: pts
Path to SeventySix.esm: D:\Fallout76PTS\Data\SeventySix.esm
Set 'pts' as the default profile? [y/N]:

Add another profile? [y/N]:

Config saved to C:\Users\you\AppData\Roaming\fo76dm\config.toml

Profiles:
  default: D:\Fallout76\Data\SeventySix.esm (default)
  pts: D:\Fallout76PTS\Data\SeventySix.esm
```

Now commands work without `--esm`:

```
fo76dm snapshot
fo76dm list
fo76dm diff --latest --vs pts
```

## Usage

Commands use the default profile automatically. Pass `--esm` or `--profile` to override:

```
fo76dm <command>                      # uses default profile
fo76dm --profile pts <command>        # uses named profile
fo76dm --esm "D:\...\SeventySix.esm" <command>  # explicit path (overrides profile)
```

### Create a snapshot

```
fo76dm snapshot --label "patch 1.2"
```

Takes ~35 seconds. Parses the ESM, loads strings, decodes fields, and writes everything to SQLite (~212 MB per snapshot).

### List snapshots

```
fo76dm list
```

```
  ID  Label                           Created               Records     Strings  ESM Hash
----------------------------------------------------------------------------------------------------
   1  patch-1.1                       2026-01-15 10:00:00   478,075     246,559  e57224741abb629b
   2  patch-1.2                       2026-02-07 18:47:18   478,312     246,801  a3b1c9f72de84510
```

### Compare snapshots

Compare the two most recent snapshots within the same database:

```
fo76dm diff --latest
```

Compare specific snapshot IDs:

```
fo76dm diff --old 1 --new 2
```

Filter by record type and change output format:

```
fo76dm diff --latest --type WEAP --format markdown
fo76dm diff --latest --format html -o diff.html
```

If both snapshots have the same ESM hash, it warns you that the game data hasn't changed.

Output shows added/removed/modified records with field-level changes:

```
Diff: #1 (patch-1.1) -> #2 (patch-1.2)
Added: 237  Removed: 0  Modified: 42

=== ADDED (237) ===
  + 0x006A1F00  WEAP    NewPlasmaCaster                           Plasma Caster

=== MODIFIED (42) ===
  ~ 0x00004822  WEAP    10mm
      damage: 25.0 -> 30.0
      min_range: 1270.0 -> 1350.0
```

### Cross-database diff (Production vs PTS)

Use `--vs` with a profile name to compare snapshots across databases:

```
fo76dm diff --latest --vs pts
```

Or pass an explicit path with `--other-esm`:

```
fo76dm diff --latest --other-esm "D:\Fallout76PTS\Data\SeventySix.esm"
```

The `--esm` / default profile provides the "old" snapshot and `--vs` / `--other-esm` provides the "new" snapshot.

```
Comparing snapshot #3 (patch-1.2) vs #1 (pts-2026-02-05)...
Diff: #3 (patch-1.2) -> #1 (pts-2026-02-05)
Added: 58  Removed: 3  Modified: 127

=== ADDED (58) ===
  + 0x006B2A10  WEAP    PTS_TestLaserRifle                        Experimental Laser Rifle

=== MODIFIED (127) ===
  ~ 0x00004822  WEAP    10mm
      damage: 30.0 -> 35.0
```

Compare specific snapshot IDs across databases (`--old` refers to the main DB, `--new` refers to the `--vs` / `--other-esm` DB):

```
fo76dm diff --old 3 --new 1 --vs pts
```

All format options (`--format text|json|markdown|html`) and type filters (`--type WEAP`) work with cross-database diffs.

Write diff output to a file with `--output` / `-o`:

```
fo76dm diff --latest -o diff.txt
fo76dm diff --latest --format markdown -o diff.md
fo76dm diff --latest --format html -o diff.html
```

### Search records

```
fo76dm search "Stimpak" --type ALCH
fo76dm search "Handmade" --type WEAP
fo76dm search 0x00004822
fo76dm search "" --edid "ATX_Weapon_*"
fo76dm search "Fixer" --format html -o search.html
```

### Show record detail

```
fo76dm show 0x00004822
fo76dm show 0x00004822 --expand   # expand leveled list entries into a tree
```

```
Record 0x00004822
  Type:       WEAP
  Editor ID:  10mm
  Name:       10mm
  Flags:      0x40000000
  Data Size:  1,797 bytes
  Data Hash:  993eb7ef4ee25abe...

  Decoded Fields:
    speed                     = 1.0000 (float)
    min_range                 = 1270.0 (float)
    max_range                 = 2538.0 (float)
    damage                    = 0.0 (float)
    crit_damage               = 2.5 (float)
    num_projectiles           = 1 (int)
```

### Find unreleased content

```
fo76dm unreleased
fo76dm unreleased --format html -o unreleased.html
```

Scans for:
- **Atomic Shop items** - `ATX_` prefix (23K+ items)
- **Cut/test content** - `zzz_`, `CUT_`, `TEST_`, `test_`, `DEBUG_`, `DVLP_` prefixes
- **High FormIDs** - Newly added records (top 0.5% of FormID range)
- **Disabled quests** - ATX_ quests not yet activated

### Search strings

```
fo76dm strings search "Nuka"
```

### Export

```
fo76dm export --format csv --type WEAP -o weapons.csv
fo76dm export --format json --type AMMO
fo76dm export --format html --type WEAP -o weapons.html
```

### Stats

```
fo76dm stats
```

### Purge old snapshots

```
fo76dm purge --keep 3
```

### Clear all snapshots

```
fo76dm clear         # prompts for confirmation
fo76dm clear --yes   # skip confirmation
```

Deletes every snapshot and all related data (records, decoded fields, strings, keywords, subrecords, diffs) from the database.

### Extract sounds

List all sound files in the archives:

```
fo76dm sounds --list-only
```

Filter by path fragment or glob:

```
fo76dm sounds --filter music --list-only
fo76dm sounds --filter "sound/fx/wpn/*.xwm" --list-only
```

Extract and convert to WAV (requires ffmpeg):

```
fo76dm sounds --filter music -o music_out
```

Extract raw `.xwm` files without conversion:

```
fo76dm sounds --raw --filter music
```

`.fuz` files (voice lines with lip-sync data) are automatically stripped to their audio portion before conversion. If ffmpeg is not installed, a warning is printed and raw `.xwm` files are saved instead.

## Configuration

`fo76dm init` saves profiles to a TOML config file:

- **Windows:** `%APPDATA%\fo76dm\config.toml`
- **Linux/macOS:** `~/.fo76dm/config.toml`

Format:

```toml
default_profile = "default"

[profiles.default]
esm = 'D:\Fallout76\Data\SeventySix.esm'

[profiles.pts]
esm = 'D:\Fallout76PTS\Data\SeventySix.esm'
```

**Resolution order:** `--esm` flag > `--profile` flag > default profile. If none resolve, commands show a helpful error pointing to `fo76dm init`.

## Database

The SQLite database path is derived from the `--esm` path — it goes up two directories from the ESM file and creates a `fo76datamine/db/` folder there. For example, if your ESM is at `D:\Fallout76\Data\SeventySix.esm`, the database will be at `D:\Fallout76\fo76datamine\db\fo76datamine.db`. It uses WAL mode for performance. Production and PTS installations each get their own database since the path is derived from the ESM location. Use `diff --vs` or `diff --other-esm` to compare across them.

| Table | Contents |
|-------|----------|
| `snapshots` | Metadata per parse (date, ESM hash, label) |
| `records` | All parsed records (form_id, type, editor_id, full_name, data_hash) |
| `decoded_fields` | Named field values (damage, weight, value, etc.) |
| `strings` | All localized strings |
| `keywords` | KYWD form_id to editor_id mapping |
| `subrecords` | Raw subrecord data (only with `--full` flag) |
| `diffs` / `diff_entries` | Pre-computed comparison results |

## Decoded Record Types

| Type | Fields |
|------|--------|
| WEAP | damage, speed, reach, min/max range, crit damage/multiplier, num projectiles, weight, value |
| ARMO | value, weight, health, armor rating, biped slots |
| ALCH | value, weight, food/medicine/poison flags, effects (magnitude, area, duration) |
| NPC_ | level, health/magicka/stamina offsets, essential/unique/protected flags, race |
| QUST | quest flags, start enabled, priority, quest type |
| COBJ | created object, workbench keyword, component requirements, created count |
| AMMO | projectile count, weight, speed, projectile reference |
| MISC/BOOK/KEYM | value, weight |
| GMST | value (float/int/string based on EDID prefix) |
| GLOB | type, value |
| CONT | contained items and counts |
| FLOR | harvest ingredient |

## Item Images

When writing to a file (`-o`), fo76dm extracts item images from the game's BA2 archives and saves them alongside the output. Use `--no-icons` to skip extraction.

```
fo76dm unreleased --format html -o unreleased.html    # icons/ and icons/full/ created next to output
fo76dm diff --latest --no-icons -o diff.html           # skip icon extraction
```

Two sizes are produced:

| Directory | Size | Purpose |
|-----------|------|---------|
| `icons/` | 128x128 | Thumbnails shown in tables |
| `icons/full/` | Native resolution | Loaded on click in HTML lightbox |

**Two-tier extraction pipeline:**

1. **WorkshopIcons BA2** (fast) — Pre-rendered item images stored by FormID. Covers ~3700 buildable/Atomic Shop items. Extracted from `SeventySix - WorkshopIcons.ba2` (GNRL format).

2. **Model texture fallback** (slower) — For items without a workshop icon, follows the model's material chain: MODL subrecord → `.nif` mesh (from Meshes BA2) → `.bgsm` material (from Materials BA2) → diffuse texture `_d.dds` (from Textures BA2, DX10 format). Parses NIF string tables and BGSM headers to resolve the chain.

In HTML output, clicking any thumbnail opens a lightbox overlay showing the full-resolution image. Press Escape or click the backdrop to close.

## How It Works

Custom pure-Python parser for Fallout 76's ESM format (version 208). No external Bethesda modding libraries are used since none support FO76's format.

- **Record header**: 24 bytes (type + datasize + flags + formID + revision + version)
- **GRUP header**: 24 bytes (GRUP tag + groupsize + label + grouptype + timestamp)
- **Compression**: zlib for records with flag `0x00040000` (mainly NPC_ records)
- **Skipped types**: REFR (5.1M placement refs), NAVM, ACHR - not useful for datamining
- **Localization**: Strings stored in separate `.strings`/`.dlstrings`/`.ilstrings` files inside the Localization BA2 archive (BTDX v1 GNRL format)
- **BA2 formats**: GNRL (general files — meshes, materials, workshop icons, sounds) and DX10 (textures with chunk-based mip levels and zlib compression)
- **NIF parsing**: Reads Gamebryo NIF headers (version 20.2.0.7, BS stream 155) to extract material paths from the string table
- **BGSM parsing**: Reads Bethesda material files to extract the diffuse texture path (first length-prefixed string after the 60-byte header)
