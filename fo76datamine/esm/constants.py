"""ESM format constants, flags, and magic numbers."""

# Record flags
FLAG_MASTER = 0x00000001
FLAG_LOCALIZED = 0x00000080
FLAG_COMPRESSED = 0x00040000
FLAG_INITIALLY_DISABLED = 0x00000800

# Group types
GROUP_TOP = 0           # Top-level group, label = record type
GROUP_WORLD_CHILDREN = 1
GROUP_INTERIOR_CELL_BLOCK = 2
GROUP_INTERIOR_CELL_SUBBLOCK = 3
GROUP_EXTERIOR_CELL_BLOCK = 4
GROUP_EXTERIOR_CELL_SUBBLOCK = 5
GROUP_CELL_CHILDREN = 6
GROUP_TOPIC_CHILDREN = 7
GROUP_CELL_PERSISTENT = 8
GROUP_CELL_TEMPORARY = 9

# Common subrecord types
SUB_EDID = b"EDID"  # Editor ID
SUB_FULL = b"FULL"  # Display name (localized string ID)
SUB_DESC = b"DESC"  # Description (localized string ID)
SUB_OBND = b"OBND"  # Object bounds
SUB_KWDA = b"KWDA"  # Keyword array data
SUB_KSIZ = b"KSIZ"  # Keyword array size
SUB_DATA = b"DATA"  # Generic data
SUB_DNAM = b"DNAM"  # Type-specific data
SUB_MODL = b"MODL"  # Model filename

# WEAP subtypes
SUB_DAMA = b"DAMA"  # Damage types
SUB_INAM = b"INAM"  # Impact data set
SUB_MASE = b"MASE"  # Melee attack speed

# Quest flags (DATA subrecord)
QUEST_FLAG_START_ENABLED = 0x0001
QUEST_FLAG_COMPLETED = 0x0002
QUEST_FLAG_WILDERNESS = 0x0080

# Datamining-relevant record types (all types except placement refs)
SKIP_TYPES = frozenset({
    b"REFR",  # Object references (~5.1M)
    b"NAVM",  # Navmeshes (~25K)
    b"ACHR",  # Placed NPCs
    b"PGRE",  # Placed grenades
    b"PMIS",  # Placed missiles
    b"PHZD",  # Placed hazards
    b"PARW",  # Placed arrows
})

# Types with interesting decoded fields
DECODED_TYPES = frozenset({
    b"WEAP",  # Weapons
    b"ARMO",  # Armor
    b"ALCH",  # Consumables
    b"NPC_",  # NPCs
    b"QUST",  # Quests
    b"COBJ",  # Constructible objects (crafting recipes)
    b"AMMO",  # Ammunition
    b"BOOK",  # Notes/holotapes
    b"MISC",  # Miscellaneous items
    b"KEYM",  # Keys
    b"FLOR",  # Harvestable flora
    b"GLOB",  # Global variables
    b"GMST",  # Game settings
    b"CONT",  # Containers
    b"PERK",  # Perks
    b"LVLI",  # Leveled item lists
    b"LVLN",  # Leveled NPC lists
    b"ENCH",  # Enchantments
    b"MGEF",  # Magic effects
    b"SPEL",  # Spells/abilities
    b"OMOD",  # Object modifications
    b"FACT",  # Factions
    b"RACE",  # Races
    b"TERM",  # Terminals
    b"AVIF",  # Actor values
    b"ACTI",  # Activators
    b"LSCR",  # Loading screens
    b"MESG",  # Messages
    b"FURN",  # Furniture
})

# Prefixes that indicate unreleased content
UNRELEASED_PREFIXES = (
    "ATX_",    # Atomic Shop items
    "zzz_",    # Disabled/cut content
    "CUT_",    # Cut content
    "TEST_",   # Test items
    "test_",
    "DEBUG_",  # Debug items
    "DVLP_",   # Development items
    "DLC",     # Unreleased DLC
)
