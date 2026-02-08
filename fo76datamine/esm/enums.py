"""Enum lookup dicts for integer-coded fields in ESM records."""
from __future__ import annotations


def lookup_enum(table: dict[int, str], value: int) -> str:
    """Return human-readable name for an enum value, or str(value) for unknowns."""
    return table.get(value, str(value))


# WEAP DNAM animation type
WEAP_ANIMATION_TYPE: dict[int, str] = {
    0: "hand_to_hand",
    1: "melee_1h",
    2: "melee_2h",
    3: "pistol_ballistic",
    4: "pistol_automatic",
    5: "rifle_ballistic",
    6: "rifle_automatic",
    7: "shotgun",
    8: "thrown",
    9: "mine",
    10: "bow",
    11: "crossbow",
    12: "cryolator",
}

# WEAP DNAM sound level
WEAP_SOUND_LEVEL: dict[int, str] = {
    0: "loud",
    1: "normal",
    2: "silent",
    3: "very_loud",
}

# MGEF DATA archetype
MGEF_ARCHETYPE: dict[int, str] = {
    0: "value_modifier",
    1: "script",
    2: "dispel",
    3: "cure_disease",
    4: "absorb",
    5: "dual_value_modifier",
    6: "calm",
    7: "demoralize",
    8: "frenzy",
    9: "disarm",
    10: "command_summoned",
    11: "invisibility",
    12: "light",
    13: "darkness",
    14: "nighteye",
    15: "lock",
    16: "open",
    17: "bound_weapon",
    18: "summon_creature",
    19: "detect_life",
    20: "telekinesis",
    21: "paralysis",
    22: "reanimate",
    23: "soul_trap",
    24: "turn_undead",
    25: "guide",
    26: "werewolf_feed",
    27: "cure_paralysis",
    28: "cure_addiction",
    29: "cure_poison",
    30: "concussion",
    31: "stimpak",
    32: "accumulate_magnitude",
    33: "stagger",
    34: "peak_value_modifier",
    35: "cloak",
    36: "werewolf",
    37: "slow_time",
    38: "rally",
    39: "enhance_weapon",
    40: "spawn_hazard",
    41: "etherealize",
    42: "banish",
    43: "spawn_scripted_ref",
    44: "disguise",
    45: "grab_actor",
    46: "vampire_lord",
}

# MGEF/ENCH/SPEL cast_type
CASTING_TYPE: dict[int, str] = {
    0: "constant_effect",
    1: "fire_and_forget",
    2: "concentration",
}

# MGEF delivery / ENCH/SPEL target_type
TARGET_TYPE: dict[int, str] = {
    0: "self",
    1: "touch",
    2: "aimed",
    3: "target_actor",
    4: "target_location",
}

# SPEL spell_type
SPEL_TYPE: dict[int, str] = {
    0: "spell",
    1: "disease",
    2: "power",
    3: "lesser_power",
    4: "ability",
    5: "addiction",
}

# ENCH enchant_type
ENCH_TYPE: dict[int, str] = {
    6: "enchantment",
    12: "staff_enchantment",
}

# OMOD property value_type
OMOD_VALUE_TYPE: dict[int, str] = {
    0: "int",
    1: "float",
    2: "bool",
    3: "formid_int",
    4: "formid_float",
    5: "enum",
}

# OMOD property function_type
OMOD_FUNCTION_TYPE: dict[int, str] = {
    0: "set",
    1: "mul_add",
    2: "add",
}

# FACT inter-faction reaction
FACT_REACTION: dict[int, str] = {
    0: "neutral",
    1: "enemy",
    2: "ally",
    3: "friend",
}

# QUST quest_type
QUST_TYPE: dict[int, str] = {
    0: "none",
    1: "main_quest",
    2: "side_quest",
    3: "misc",
    4: "daily",
    5: "event",
    6: "dungeon",
    7: "challenge",
    8: "world_event",
}

# FURN bench_type (inline, used by FURN decoder)
FURN_BENCH_TYPE: dict[int, str] = {
    0: "none",
    1: "create_object",
    2: "smithing_armor",
    3: "enchanting",
    4: "alchemy",
    5: "smithing_weapon",
    6: "power_armor",
}

# CELL DATA flags (bitfield)
CELL_FLAGS: dict[int, str] = {
    0x0001: "is_interior",
    0x0002: "has_water",
    0x0004: "cant_travel_from",
    0x0008: "no_lod_water",
    0x0020: "public_area",
    0x0040: "hand_changed",
    0x0080: "show_sky",
    0x0100: "use_sky_lighting",
}

# DIAL topic type
DIAL_TYPE: dict[int, str] = {
    0: "topic",
    1: "conversation",
    2: "combat",
    3: "persuasion",
    4: "detection",
    5: "service",
    6: "misc",
    7: "scene_dialog",
}

# DIAL topic subtype
DIAL_SUBTYPE: dict[int, str] = {
    0: "custom",
    1: "force_greet",
    2: "rumors",
    3: "custom_2",
    4: "call",
    5: "follow",
    6: "move",
    7: "attack",
    8: "inspect",
    9: "retrieve",
    10: "stay",
    11: "release",
    12: "show_relationships",
    13: "reject",
    14: "heal",
    15: "assign",
    16: "enter",
    17: "custom_3",
    18: "custom_4",
    19: "custom_5",
}

# REGN data entry type
REGN_DATA_TYPE: dict[int, str] = {
    2: "objects",
    3: "weather",
    4: "map",
    5: "land",
    6: "grass",
    7: "sound",
    8: "imposter",
}

# PROJ projectile type
PROJ_TYPE: dict[int, str] = {
    1: "missile",
    2: "lobber",
    3: "beam",
    4: "flame",
    5: "cone",
    6: "barrier",
    7: "arrow",
}

# EXPL explosion flags (bitfield)
EXPL_FLAGS: dict[int, str] = {
    0x0001: "always_use_world_orientation",
    0x0002: "knock_down_always",
    0x0004: "knock_down_by_formula",
    0x0008: "ignore_los_check",
    0x0010: "no_visual",
    0x0020: "no_sound",
}
