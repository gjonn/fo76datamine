"""Type-specific field decoders for key record types.

Decodes binary subrecord data into named field values for:
WEAP (DNAM 170 bytes), ARMO (DATA 12 bytes), ALCH (ENIT 33 bytes, DATA 4 bytes),
NPC_ (ACBS 20 bytes, DNAM 8 bytes), QUST (DATA 20 bytes),
COBJ (DNAM 8 bytes, FVPA components, CNAM/BNAM),
AMMO (DATA 8 bytes, DNAM 16 bytes), MISC/BOOK/KEYM (DATA), GMST, GLOB,
LVLI/LVLN (leveled lists), PERK (perk cards), ENCH (enchantments),
MGEF (magic effects), SPEL (spells), OMOD (object mods),
FACT (factions), RACE (races), TERM (terminals).
"""
from __future__ import annotations

import struct
from typing import Optional

from fo76datamine.esm.enums import (
    CASTING_TYPE,
    ENCH_TYPE,
    FACT_REACTION,
    FURN_BENCH_TYPE,
    MGEF_ARCHETYPE,
    OMOD_FUNCTION_TYPE,
    OMOD_VALUE_TYPE,
    QUST_TYPE,
    SPEL_TYPE,
    TARGET_TYPE,
    WEAP_ANIMATION_TYPE,
    WEAP_SOUND_LEVEL,
    lookup_enum,
)
from fo76datamine.esm.records import Record, Subrecord
from fo76datamine.strings.loader import StringTable


def decode_all_records(records: list[Record], strings: StringTable) -> list[tuple]:
    """Decode fields for all records. Returns list of (form_id, field_name, field_value, field_type)."""
    result = []
    for rec in records:
        fields = decode_record(rec, strings)
        if fields:
            result.extend(fields)
    return result


def decode_record(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode type-specific fields from a record."""
    fields = []
    decoder = _DECODERS.get(rec.type)
    if decoder:
        fields.extend(decoder(rec, strings))

    # Universal fields: icon paths
    icon = rec.get_subrecord("ICON")
    if icon and icon.size > 1:
        fields.append((rec.form_id, "icon", icon.as_string(), "str"))
    mico = rec.get_subrecord("MICO")
    if mico and mico.size > 1:
        fields.append((rec.form_id, "icon_small", mico.as_string(), "str"))

    # Universal fields: model path
    modl = rec.get_subrecord("MODL")
    if modl and modl.size > 1:
        fields.append((rec.form_id, "model", modl.as_string(), "str"))

    # Universal fields: keywords
    kwda = rec.get_subrecord("KWDA")
    if kwda and kwda.size >= 4:
        keyword_ids = kwda.as_formid_array()
        for i, kid in enumerate(keyword_ids):
            fields.append((rec.form_id, f"keyword_{i}", f"0x{kid:08X}", "formid"))

    return fields


def _decode_weap(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode WEAP record fields."""
    fields = []
    fid = rec.form_id

    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 170:
        d = dnam.data
        # WEAP DNAM struct (170 bytes) - Fallout 76 format
        fields.append((fid, "animation_type", lookup_enum(WEAP_ANIMATION_TYPE, struct.unpack_from("<I", d, 0)[0]), "enum"))
        fields.append((fid, "speed", f"{struct.unpack_from('<f', d, 4)[0]:.4f}", "float"))
        fields.append((fid, "reach", f"{struct.unpack_from('<f', d, 8)[0]:.4f}", "float"))
        fields.append((fid, "min_range", f"{struct.unpack_from('<f', d, 24)[0]:.1f}", "float"))
        fields.append((fid, "max_range", f"{struct.unpack_from('<f', d, 28)[0]:.1f}", "float"))
        fields.append((fid, "attack_delay", f"{struct.unpack_from('<f', d, 32)[0]:.4f}", "float"))
        fields.append((fid, "out_of_range_dmg_mult", f"{struct.unpack_from('<f', d, 44)[0]:.4f}", "float"))
        fields.append((fid, "secondary_damage", f"{struct.unpack_from('<f', d, 48)[0]:.4f}", "float"))
        fields.append((fid, "weight", f"{struct.unpack_from('<f', d, 52)[0]:.2f}", "float"))
        fields.append((fid, "value", str(struct.unpack_from("<I", d, 56)[0]), "int"))
        fields.append((fid, "damage", f"{struct.unpack_from('<f', d, 60)[0]:.1f}", "float"))
        fields.append((fid, "num_projectiles", str(struct.unpack_from("<B", d, 101)[0]), "int"))
        fields.append((fid, "sound_level", lookup_enum(WEAP_SOUND_LEVEL, struct.unpack_from("<I", d, 112)[0]), "enum"))

    # Critical data
    crdt = rec.get_subrecord("CRDT")
    if crdt and crdt.size >= 12:
        d = crdt.data
        fields.append((fid, "crit_damage", f"{struct.unpack_from('<f', d, 0)[0]:.1f}", "float"))
        fields.append((fid, "crit_multiplier", f"{struct.unpack_from('<f', d, 4)[0]:.4f}", "float"))

    # Damage type array
    dama = rec.get_subrecord("DAMA")
    if dama and dama.size >= 8:
        count = dama.size // 8
        for i in range(count):
            dtype_fid = struct.unpack_from("<I", dama.data, i * 8)[0]
            dtype_val = struct.unpack_from("<f", dama.data, i * 8 + 4)[0]
            fields.append((fid, f"damage_type_{i}_id", f"0x{dtype_fid:08X}", "formid"))
            fields.append((fid, f"damage_type_{i}_value", f"{dtype_val:.1f}", "float"))

    return fields


def _decode_armo(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode ARMO record fields."""
    fields = []
    fid = rec.form_id

    # DATA: 12 bytes = value(int32) + weight(float) + unknown(int32)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 8:
        d = data.data
        fields.append((fid, "value", str(struct.unpack_from("<i", d, 0)[0]), "int"))
        fields.append((fid, "weight", f"{struct.unpack_from('<f', d, 4)[0]:.2f}", "float"))
        if data.size >= 12:
            fields.append((fid, "health", str(struct.unpack_from("<I", d, 8)[0]), "int"))

    # DNAM: armor rating
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 4:
        fields.append((fid, "armor_rating", str(struct.unpack_from("<I", dnam.data, 0)[0]), "int"))

    # BOD2: body template (biped slots)
    bod2 = rec.get_subrecord("BOD2")
    if bod2 and bod2.size >= 8:
        first_person = struct.unpack_from("<I", bod2.data, 0)[0]
        fields.append((fid, "biped_slots", f"0x{first_person:08X}", "flags"))

    return fields


def _decode_alch(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode ALCH record fields."""
    fields = []
    fid = rec.form_id

    # DATA: 4 bytes = weight (float)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 4:
        fields.append((fid, "weight", f"{struct.unpack_from('<f', data.data, 0)[0]:.2f}", "float"))

    # ENIT: 33 bytes
    enit = rec.get_subrecord("ENIT")
    if enit and enit.size >= 12:
        d = enit.data
        fields.append((fid, "value", str(struct.unpack_from("<i", d, 0)[0]), "int"))
        flags = struct.unpack_from("<I", d, 4)[0]
        fields.append((fid, "enit_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "is_food", str(bool(flags & 0x00000002)), "str"))
        fields.append((fid, "is_medicine", str(bool(flags & 0x00010000)), "str"))
        fields.append((fid, "is_poison", str(bool(flags & 0x00020000)), "str"))

        if enit.size >= 12:
            addiction_formid = struct.unpack_from("<I", d, 8)[0]
            if addiction_formid:
                fields.append((fid, "addiction", f"0x{addiction_formid:08X}", "formid"))

        if enit.size >= 20:
            sound_consume = struct.unpack_from("<I", d, 16)[0]
            if sound_consume:
                fields.append((fid, "consume_sound", f"0x{sound_consume:08X}", "formid"))

    # Effect entries
    efids = rec.get_subrecords("EFID")
    efits = rec.get_subrecords("EFIT")
    for i, (efid_sub, efit_sub) in enumerate(zip(efids, efits)):
        effect_fid = struct.unpack_from("<I", efid_sub.data, 0)[0]
        fields.append((fid, f"effect_{i}_id", f"0x{effect_fid:08X}", "formid"))
        if efit_sub.size >= 12:
            magnitude = struct.unpack_from("<f", efit_sub.data, 0)[0]
            area = struct.unpack_from("<I", efit_sub.data, 4)[0]
            duration = struct.unpack_from("<I", efit_sub.data, 8)[0]
            fields.append((fid, f"effect_{i}_magnitude", f"{magnitude:.2f}", "float"))
            fields.append((fid, f"effect_{i}_area", str(area), "int"))
            fields.append((fid, f"effect_{i}_duration", str(duration), "int"))

    return fields


def _decode_npc(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode NPC_ record fields."""
    fields = []
    fid = rec.form_id

    # ACBS: 20 bytes - Actor Configuration
    acbs = rec.get_subrecord("ACBS")
    if acbs and acbs.size >= 20:
        d = acbs.data
        flags = struct.unpack_from("<I", d, 0)[0]
        fields.append((fid, "npc_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "is_essential", str(bool(flags & 0x00000002)), "str"))
        fields.append((fid, "is_unique", str(bool(flags & 0x00000004)), "str"))
        fields.append((fid, "is_protected", str(bool(flags & 0x00000800)), "str"))
        magicka_offset = struct.unpack_from("<H", d, 4)[0]
        stamina_offset = struct.unpack_from("<H", d, 6)[0]
        level = struct.unpack_from("<H", d, 8)[0]
        fields.append((fid, "level", str(level), "int"))
        health_offset = struct.unpack_from("<H", d, 14)[0]
        fields.append((fid, "health_offset", str(health_offset), "int"))
        fields.append((fid, "magicka_offset", str(magicka_offset), "int"))
        fields.append((fid, "stamina_offset", str(stamina_offset), "int"))

    # DNAM: 8 bytes for NPCs
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 4:
        d = dnam.data
        health = struct.unpack_from("<H", d, 0)[0]
        action_points = struct.unpack_from("<H", d, 2)[0]
        fields.append((fid, "base_health", str(health), "int"))
        fields.append((fid, "base_action_points", str(action_points), "int"))

    # RNAM: race
    rnam = rec.get_subrecord("RNAM")
    if rnam and rnam.size >= 4:
        race_fid = struct.unpack_from("<I", rnam.data, 0)[0]
        fields.append((fid, "race", f"0x{race_fid:08X}", "formid"))

    return fields


def _decode_qust(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode QUST record fields."""
    fields = []
    fid = rec.form_id

    # DATA: 20 bytes
    data = rec.get_subrecord("DATA")
    if data and data.size >= 4:
        d = data.data
        flags = struct.unpack_from("<I", d, 0)[0]
        fields.append((fid, "quest_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "start_game_enabled", str(bool(flags & 0x0001)), "str"))
        fields.append((fid, "wilderness_encounter", str(bool(flags & 0x0080)), "str"))

        if data.size >= 8:
            priority = struct.unpack_from("<I", d, 4)[0]
            fields.append((fid, "priority", str(priority), "int"))

        if data.size >= 16:
            quest_type = struct.unpack_from("<I", d, 8)[0]
            fields.append((fid, "quest_type", lookup_enum(QUST_TYPE, quest_type), "enum"))

    return fields


def _decode_cobj(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode COBJ (Constructible Object / crafting recipe) fields."""
    fields = []
    fid = rec.form_id

    # CNAM: created object FormID
    cnam = rec.get_subrecord("CNAM")
    if cnam and cnam.size >= 4:
        created_fid = struct.unpack_from("<I", cnam.data, 0)[0]
        fields.append((fid, "created_object", f"0x{created_fid:08X}", "formid"))

    # BNAM: workbench keyword
    bnam = rec.get_subrecord("BNAM")
    if bnam and bnam.size >= 4:
        bench_fid = struct.unpack_from("<I", bnam.data, 0)[0]
        fields.append((fid, "workbench_keyword", f"0x{bench_fid:08X}", "formid"))

    # DNAM: 8 bytes = unknown(4) + created_count(uint32)
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 8:
        created_count = struct.unpack_from("<I", dnam.data, 4)[0]
        fields.append((fid, "created_count", str(created_count), "int"))

    # FVPA: component requirements (array of 8-byte entries: formid + count)
    fvpa = rec.get_subrecord("FVPA")
    if fvpa and fvpa.size >= 8:
        count = fvpa.size // 8
        for i in range(count):
            comp_fid = struct.unpack_from("<I", fvpa.data, i * 8)[0]
            comp_count = struct.unpack_from("<I", fvpa.data, i * 8 + 4)[0]
            fields.append((fid, f"component_{i}_id", f"0x{comp_fid:08X}", "formid"))
            fields.append((fid, f"component_{i}_count", str(comp_count), "int"))

    return fields


def _decode_ammo(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode AMMO record fields."""
    fields = []
    fid = rec.form_id

    # DATA: 8 bytes = projectile_count(int32) + weight(float)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 8:
        d = data.data
        proj_count = struct.unpack_from("<i", d, 0)[0]
        weight = struct.unpack_from("<f", d, 4)[0]
        fields.append((fid, "projectile_count", str(proj_count), "int"))
        fields.append((fid, "weight", f"{weight:.4f}", "float"))

    # DNAM: 16 bytes
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 16:
        d = dnam.data
        projectile_fid = struct.unpack_from("<I", d, 0)[0]
        flags = struct.unpack_from("<I", d, 4)[0]
        speed = struct.unpack_from("<f", d, 8)[0]
        fields.append((fid, "projectile", f"0x{projectile_fid:08X}", "formid"))
        fields.append((fid, "ammo_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "speed", f"{speed:.1f}", "float"))

    return fields


def _decode_misc(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode MISC record fields."""
    fields = []
    fid = rec.form_id

    data = rec.get_subrecord("DATA")
    if data and data.size >= 8:
        d = data.data
        value = struct.unpack_from("<i", d, 0)[0]
        weight = struct.unpack_from("<f", d, 4)[0]
        fields.append((fid, "value", str(value), "int"))
        fields.append((fid, "weight", f"{weight:.2f}", "float"))

    return fields


def _decode_book(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode BOOK record fields."""
    fields = []
    fid = rec.form_id

    data = rec.get_subrecord("DATA")
    if data and data.size >= 8:
        d = data.data
        value = struct.unpack_from("<i", d, 0)[0]
        weight = struct.unpack_from("<f", d, 4)[0]
        fields.append((fid, "value", str(value), "int"))
        fields.append((fid, "weight", f"{weight:.2f}", "float"))

    return fields


def _decode_keym(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode KEYM record fields."""
    fields = []
    fid = rec.form_id

    data = rec.get_subrecord("DATA")
    if data and data.size >= 8:
        d = data.data
        value = struct.unpack_from("<i", d, 0)[0]
        weight = struct.unpack_from("<f", d, 4)[0]
        fields.append((fid, "value", str(value), "int"))
        fields.append((fid, "weight", f"{weight:.2f}", "float"))

    return fields


def _decode_gmst(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode GMST (Game Setting) fields."""
    fields = []
    fid = rec.form_id

    data = rec.get_subrecord("DATA")
    edid = rec.editor_id or ""

    if data and data.size >= 4:
        # Type is determined by first character of EDID
        if edid.startswith("f"):
            val = struct.unpack_from("<f", data.data, 0)[0]
            fields.append((fid, "value", f"{val:.6f}", "float"))
        elif edid.startswith("i") or edid.startswith("u"):
            val = struct.unpack_from("<i", data.data, 0)[0]
            fields.append((fid, "value", str(val), "int"))
        elif edid.startswith("s"):
            val = data.data.rstrip(b"\x00").decode("utf-8", errors="replace")
            fields.append((fid, "value", val, "str"))
        elif edid.startswith("b"):
            val = struct.unpack_from("<I", data.data, 0)[0]
            fields.append((fid, "value", str(bool(val)), "str"))

    return fields


def _decode_glob(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode GLOB (Global Variable) fields."""
    fields = []
    fid = rec.form_id

    fnam = rec.get_subrecord("FNAM")
    fltv = rec.get_subrecord("FLTV")

    if fnam and fnam.size >= 1:
        type_code = fnam.data[0]
        type_name = {0x73: "short", 0x6C: "long", 0x66: "float"}.get(type_code, f"0x{type_code:02X}")
        fields.append((fid, "type", type_name, "str"))

    if fltv and fltv.size >= 4:
        val = struct.unpack_from("<f", fltv.data, 0)[0]
        fields.append((fid, "value", f"{val:.6f}", "float"))

    return fields


def _decode_cont(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode CONT (Container) fields."""
    fields = []
    fid = rec.form_id

    # Container items (CNTO subrecords)
    cntos = rec.get_subrecords("CNTO")
    for i, cnto in enumerate(cntos):
        if cnto.size >= 8:
            item_fid = struct.unpack_from("<I", cnto.data, 0)[0]
            item_count = struct.unpack_from("<i", cnto.data, 4)[0]
            fields.append((fid, f"item_{i}_id", f"0x{item_fid:08X}", "formid"))
            fields.append((fid, f"item_{i}_count", str(item_count), "int"))

    return fields


def _decode_flor(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode FLOR (Flora) fields."""
    fields = []
    fid = rec.form_id

    # PFIG: ingredient produced
    pfig = rec.get_subrecord("PFIG")
    if pfig and pfig.size >= 4:
        ingredient = struct.unpack_from("<I", pfig.data, 0)[0]
        fields.append((fid, "harvest_ingredient", f"0x{ingredient:08X}", "formid"))

    return fields


def _decode_lvli(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode LVLI (Leveled Item) fields."""
    fields = []
    fid = rec.form_id

    # LVLD: chance none (uint8)
    lvld = rec.get_subrecord("LVLD")
    if lvld and lvld.size >= 1:
        fields.append((fid, "chance_none", str(lvld.data[0]), "int"))

    # LVLF: flags (uint8)
    lvlf = rec.get_subrecord("LVLF")
    if lvlf and lvlf.size >= 1:
        flags = lvlf.data[0]
        fields.append((fid, "lvl_flags", f"0x{flags:02X}", "flags"))
        fields.append((fid, "calculate_all", str(bool(flags & 0x01)), "str"))
        fields.append((fid, "calculate_all_lte_pc", str(bool(flags & 0x02)), "str"))
        fields.append((fid, "use_all", str(bool(flags & 0x04)), "str"))

    # LLCT: entry count (uint8)
    llct = rec.get_subrecord("LLCT")
    if llct and llct.size >= 1:
        fields.append((fid, "entry_count", str(llct.data[0]), "int"))

    # LVLO: leveled list entries (12 bytes each)
    lvlos = rec.get_subrecords("LVLO")
    for i, lvlo in enumerate(lvlos):
        if lvlo.size >= 12:
            d = lvlo.data
            level = struct.unpack_from("<H", d, 0)[0]
            ref = struct.unpack_from("<I", d, 4)[0]
            count = struct.unpack_from("<H", d, 8)[0]
            fields.append((fid, f"entry_{i}_level", str(level), "int"))
            fields.append((fid, f"entry_{i}_ref", f"0x{ref:08X}", "formid"))
            fields.append((fid, f"entry_{i}_count", str(count), "int"))

    return fields


def _decode_lvln(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode LVLN (Leveled NPC) fields."""
    fields = []
    fid = rec.form_id

    # LVLD: chance none (uint8)
    lvld = rec.get_subrecord("LVLD")
    if lvld and lvld.size >= 1:
        fields.append((fid, "chance_none", str(lvld.data[0]), "int"))

    # LVLF: flags (uint8)
    lvlf = rec.get_subrecord("LVLF")
    if lvlf and lvlf.size >= 1:
        flags = lvlf.data[0]
        fields.append((fid, "lvl_flags", f"0x{flags:02X}", "flags"))
        fields.append((fid, "calculate_all", str(bool(flags & 0x01)), "str"))
        fields.append((fid, "calculate_all_lte_pc", str(bool(flags & 0x02)), "str"))
        fields.append((fid, "use_all", str(bool(flags & 0x04)), "str"))

    # LLCT: entry count (uint8)
    llct = rec.get_subrecord("LLCT")
    if llct and llct.size >= 1:
        fields.append((fid, "entry_count", str(llct.data[0]), "int"))

    # LVLO: leveled list entries (12 bytes each)
    lvlos = rec.get_subrecords("LVLO")
    for i, lvlo in enumerate(lvlos):
        if lvlo.size >= 12:
            d = lvlo.data
            level = struct.unpack_from("<H", d, 0)[0]
            ref = struct.unpack_from("<I", d, 4)[0]
            count = struct.unpack_from("<H", d, 8)[0]
            fields.append((fid, f"entry_{i}_level", str(level), "int"))
            fields.append((fid, f"entry_{i}_ref", f"0x{ref:08X}", "formid"))
            fields.append((fid, f"entry_{i}_count", str(count), "int"))

    return fields


def _decode_perk(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode PERK (Perk Card) fields."""
    fields = []
    fid = rec.form_id

    # DATA: 5 bytes
    data = rec.get_subrecord("DATA")
    if data and data.size >= 5:
        d = data.data
        fields.append((fid, "is_playable", str(bool(d[0])), "str"))
        fields.append((fid, "trait", str(d[1]), "int"))
        fields.append((fid, "level", str(d[2]), "int"))
        fields.append((fid, "num_ranks", str(d[3]), "int"))
        fields.append((fid, "hidden", str(bool(d[4])), "str"))

    # NNAM: next perk FormID (for ranked perks)
    nnam = rec.get_subrecord("NNAM")
    if nnam and nnam.size >= 4:
        next_perk = struct.unpack_from("<I", nnam.data, 0)[0]
        if next_perk:
            fields.append((fid, "next_perk", f"0x{next_perk:08X}", "formid"))

    return fields


def _decode_ench(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode ENCH (Enchantment / Legendary Effect) fields."""
    fields = []
    fid = rec.form_id

    # ENIT: 36 bytes
    enit = rec.get_subrecord("ENIT")
    if enit and enit.size >= 36:
        d = enit.data
        fields.append((fid, "cost", str(struct.unpack_from("<I", d, 0)[0]), "int"))
        fields.append((fid, "ench_flags", f"0x{struct.unpack_from('<I', d, 4)[0]:08X}", "flags"))
        fields.append((fid, "cast_type", lookup_enum(CASTING_TYPE, struct.unpack_from("<I", d, 8)[0]), "enum"))
        fields.append((fid, "charge_amount", str(struct.unpack_from("<I", d, 12)[0]), "int"))
        fields.append((fid, "target_type", lookup_enum(TARGET_TYPE, struct.unpack_from("<I", d, 16)[0]), "enum"))
        fields.append((fid, "enchant_type", lookup_enum(ENCH_TYPE, struct.unpack_from("<I", d, 20)[0]), "enum"))
        fields.append((fid, "charge_time", f"{struct.unpack_from('<f', d, 24)[0]:.4f}", "float"))
        base_ench = struct.unpack_from("<I", d, 28)[0]
        if base_ench:
            fields.append((fid, "base_enchantment", f"0x{base_ench:08X}", "formid"))

    # Effect entries (same pattern as ALCH)
    efids = rec.get_subrecords("EFID")
    efits = rec.get_subrecords("EFIT")
    for i, (efid_sub, efit_sub) in enumerate(zip(efids, efits)):
        effect_fid = struct.unpack_from("<I", efid_sub.data, 0)[0]
        fields.append((fid, f"effect_{i}_id", f"0x{effect_fid:08X}", "formid"))
        if efit_sub.size >= 12:
            magnitude = struct.unpack_from("<f", efit_sub.data, 0)[0]
            area = struct.unpack_from("<I", efit_sub.data, 4)[0]
            duration = struct.unpack_from("<I", efit_sub.data, 8)[0]
            fields.append((fid, f"effect_{i}_magnitude", f"{magnitude:.2f}", "float"))
            fields.append((fid, f"effect_{i}_area", str(area), "int"))
            fields.append((fid, f"effect_{i}_duration", str(duration), "int"))

    return fields


def _decode_mgef(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode MGEF (Magic Effect) fields."""
    fields = []
    fid = rec.form_id

    # DATA: 152+ bytes — extract key fields from first ~60 bytes
    data = rec.get_subrecord("DATA")
    if data and data.size >= 52:
        d = data.data
        flags = struct.unpack_from("<I", d, 0)[0]
        fields.append((fid, "mgef_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "base_cost", f"{struct.unpack_from('<f', d, 4)[0]:.4f}", "float"))
        related_id = struct.unpack_from("<I", d, 8)[0]
        if related_id:
            fields.append((fid, "related_id", f"0x{related_id:08X}", "formid"))
        fields.append((fid, "magic_skill", str(struct.unpack_from("<i", d, 12)[0]), "int"))
        fields.append((fid, "resist_value", str(struct.unpack_from("<I", d, 16)[0]), "int"))
        casting_light = struct.unpack_from("<I", d, 24)[0]
        if casting_light:
            fields.append((fid, "casting_light", f"0x{casting_light:08X}", "formid"))
        fields.append((fid, "taper_weight", f"{struct.unpack_from('<f', d, 28)[0]:.4f}", "float"))
        if data.size >= 60:
            fields.append((fid, "archetype", lookup_enum(MGEF_ARCHETYPE, struct.unpack_from("<I", d, 48)[0]), "enum"))
            fields.append((fid, "casting_type", lookup_enum(CASTING_TYPE, struct.unpack_from("<I", d, 52)[0]), "enum"))
        if data.size >= 64:
            fields.append((fid, "delivery", lookup_enum(TARGET_TYPE, struct.unpack_from("<I", d, 56)[0]), "enum"))

    return fields


def _decode_spel(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode SPEL (Spell / Ability) fields."""
    fields = []
    fid = rec.form_id

    # SPIT: 36 bytes
    spit = rec.get_subrecord("SPIT")
    if spit and spit.size >= 36:
        d = spit.data
        fields.append((fid, "cost", str(struct.unpack_from("<I", d, 0)[0]), "int"))
        fields.append((fid, "spell_flags", f"0x{struct.unpack_from('<I', d, 4)[0]:08X}", "flags"))
        fields.append((fid, "spell_type", lookup_enum(SPEL_TYPE, struct.unpack_from("<I", d, 8)[0]), "enum"))
        fields.append((fid, "charge_time", f"{struct.unpack_from('<f', d, 12)[0]:.4f}", "float"))
        fields.append((fid, "cast_type", lookup_enum(CASTING_TYPE, struct.unpack_from("<I", d, 16)[0]), "enum"))
        fields.append((fid, "target_type", lookup_enum(TARGET_TYPE, struct.unpack_from("<I", d, 20)[0]), "enum"))
        fields.append((fid, "cast_duration", f"{struct.unpack_from('<f', d, 24)[0]:.4f}", "float"))
        fields.append((fid, "range", f"{struct.unpack_from('<f', d, 28)[0]:.4f}", "float"))
        half_cost_perk = struct.unpack_from("<I", d, 32)[0]
        if half_cost_perk:
            fields.append((fid, "half_cost_perk", f"0x{half_cost_perk:08X}", "formid"))

    # Effect entries (same pattern as ALCH/ENCH)
    efids = rec.get_subrecords("EFID")
    efits = rec.get_subrecords("EFIT")
    for i, (efid_sub, efit_sub) in enumerate(zip(efids, efits)):
        effect_fid = struct.unpack_from("<I", efid_sub.data, 0)[0]
        fields.append((fid, f"effect_{i}_id", f"0x{effect_fid:08X}", "formid"))
        if efit_sub.size >= 12:
            magnitude = struct.unpack_from("<f", efit_sub.data, 0)[0]
            area = struct.unpack_from("<I", efit_sub.data, 4)[0]
            duration = struct.unpack_from("<I", efit_sub.data, 8)[0]
            fields.append((fid, f"effect_{i}_magnitude", f"{magnitude:.2f}", "float"))
            fields.append((fid, f"effect_{i}_area", str(area), "int"))
            fields.append((fid, f"effect_{i}_duration", str(duration), "int"))

    return fields


def _decode_omod(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode OMOD (Object Modification) fields."""
    fields = []
    fid = rec.form_id

    data = rec.get_subrecord("DATA")
    if data and data.size >= 2:
        d = data.data
        include_count = d[0]
        property_count = d[1]
        fields.append((fid, "include_count", str(include_count), "int"))
        fields.append((fid, "property_count", str(property_count), "int"))

        # Properties start after a header; each property is 24 bytes
        # Header size varies but properties typically start at offset 8
        header_size = 8
        prop_start = header_size
        for i in range(property_count):
            offset = prop_start + i * 24
            if offset + 24 > data.size:
                break
            value_type = d[offset]
            function_type = d[offset + 1]
            prop_keyword = struct.unpack_from("<I", d, offset + 4)[0]
            value1 = struct.unpack_from("<f", d, offset + 8)[0]
            value2 = struct.unpack_from("<f", d, offset + 12)[0]
            step = struct.unpack_from("<f", d, offset + 16)[0]
            fields.append((fid, f"prop_{i}_value_type", lookup_enum(OMOD_VALUE_TYPE, value_type), "enum"))
            fields.append((fid, f"prop_{i}_function_type", lookup_enum(OMOD_FUNCTION_TYPE, function_type), "enum"))
            fields.append((fid, f"prop_{i}_keyword", f"0x{prop_keyword:08X}", "formid"))
            fields.append((fid, f"prop_{i}_value1", f"{value1:.4f}", "float"))
            fields.append((fid, f"prop_{i}_value2", f"{value2:.4f}", "float"))
            fields.append((fid, f"prop_{i}_step", f"{step:.4f}", "float"))

    return fields


def _decode_fact(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode FACT (Faction) fields."""
    fields = []
    fid = rec.form_id

    # DATA: 4 bytes = flags (uint32)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 4:
        flags = struct.unpack_from("<I", data.data, 0)[0]
        fields.append((fid, "faction_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "hidden_from_pc", str(bool(flags & 0x01)), "str"))
        fields.append((fid, "special_combat", str(bool(flags & 0x02)), "str"))
        fields.append((fid, "track_crime", str(bool(flags & 0x40)), "str"))
        fields.append((fid, "can_be_owner", str(bool(flags & 0x80)), "str"))

    # XNAM: inter-faction relations (12 bytes each)
    xnams = rec.get_subrecords("XNAM")
    for i, xnam in enumerate(xnams):
        if xnam.size >= 12:
            d = xnam.data
            relation_fid = struct.unpack_from("<I", d, 0)[0]
            modifier = struct.unpack_from("<i", d, 4)[0]
            reaction = struct.unpack_from("<I", d, 8)[0]
            fields.append((fid, f"relation_{i}_faction", f"0x{relation_fid:08X}", "formid"))
            fields.append((fid, f"relation_{i}_modifier", str(modifier), "int"))
            fields.append((fid, f"relation_{i}_reaction", lookup_enum(FACT_REACTION, reaction), "enum"))

    return fields


def _decode_race(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode RACE fields — extract key datamine-relevant stats."""
    fields = []
    fid = rec.form_id

    data = rec.get_subrecord("DATA")
    if data and data.size >= 48:
        d = data.data
        flags = struct.unpack_from("<I", d, 0)[0]
        fields.append((fid, "race_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "starting_health", f"{struct.unpack_from('<f', d, 36)[0]:.1f}", "float"))
        fields.append((fid, "starting_magicka", f"{struct.unpack_from('<f', d, 40)[0]:.1f}", "float"))
        fields.append((fid, "starting_stamina", f"{struct.unpack_from('<f', d, 44)[0]:.1f}", "float"))

    # DNAM: default hair FormID
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 4:
        hair = struct.unpack_from("<I", dnam.data, 0)[0]
        if hair:
            fields.append((fid, "default_hair", f"0x{hair:08X}", "formid"))

    return fields


def _decode_term(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode TERM (Terminal) fields."""
    fields = []
    fid = rec.form_id

    # DNAM: terminal header/subtype
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size > 1:
        fields.append((fid, "terminal_header", dnam.as_string(), "str"))

    # BTXT: menu item text entries
    btxts = rec.get_subrecords("BTXT")
    for i, btxt in enumerate(btxts):
        if btxt.size > 1:
            fields.append((fid, f"menu_item_{i}", btxt.as_string(), "str"))

    # ITXT: item/body text entries
    itxts = rec.get_subrecords("ITXT")
    for i, itxt in enumerate(itxts):
        if itxt.size > 1:
            fields.append((fid, f"item_text_{i}", itxt.as_string(), "str"))

    return fields


def _decode_avif(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode AVIF (Actor Value Info) fields."""
    fields = []
    fid = rec.form_id

    # ANAM: abbreviation string
    anam = rec.get_subrecord("ANAM")
    if anam and anam.size > 1:
        fields.append((fid, "abbreviation", anam.as_string(), "str"))

    # AVFL: default value (float)
    avfl = rec.get_subrecord("AVFL")
    if avfl and avfl.size >= 4:
        val = struct.unpack_from("<f", avfl.data, 0)[0]
        fields.append((fid, "default_value", f"{val:.4f}", "float"))

    # DATA: avif_flags (uint32)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 4:
        flags = struct.unpack_from("<I", data.data, 0)[0]
        fields.append((fid, "avif_flags", f"0x{flags:08X}", "flags"))

    return fields


def _decode_acti(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode ACTI (Activator) fields."""
    fields = []
    fid = rec.form_id

    # FNAM: flags (uint16)
    fnam = rec.get_subrecord("FNAM")
    if fnam and fnam.size >= 2:
        flags = struct.unpack_from("<H", fnam.data, 0)[0]
        fields.append((fid, "acti_flags", f"0x{flags:04X}", "flags"))

    # WNAM: water type FormID
    wnam = rec.get_subrecord("WNAM")
    if wnam and wnam.size >= 4:
        water_fid = struct.unpack_from("<I", wnam.data, 0)[0]
        if water_fid:
            fields.append((fid, "water_type", f"0x{water_fid:08X}", "formid"))

    # RNAM: sound FormID
    rnam = rec.get_subrecord("RNAM")
    if rnam and rnam.size >= 4:
        sound_fid = struct.unpack_from("<I", rnam.data, 0)[0]
        if sound_fid:
            fields.append((fid, "sound", f"0x{sound_fid:08X}", "formid"))

    # VNAM: verb override (localized string ID)
    vnam = rec.get_subrecord("VNAM")
    if vnam and vnam.size >= 4:
        str_id = struct.unpack_from("<I", vnam.data, 0)[0]
        if str_id:
            text = strings.lookup(str_id)
            fields.append((fid, "verb_override", text or f"0x{str_id:08X}", "str"))

    return fields


def _decode_lscr(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode LSCR (Loading Screen) fields."""
    fields = []
    fid = rec.form_id

    # NNAM: loading screen NIF path
    nnam = rec.get_subrecord("NNAM")
    if nnam and nnam.size > 1:
        fields.append((fid, "loading_screen_nif", nnam.as_string(), "str"))

    # ONAM: rotation/zoom floats
    onam = rec.get_subrecord("ONAM")
    if onam and onam.size >= 12:
        d = onam.data
        rot_min = struct.unpack_from("<f", d, 0)[0]
        rot_max = struct.unpack_from("<f", d, 4)[0]
        zoom = struct.unpack_from("<f", d, 8)[0]
        fields.append((fid, "rotation_min", f"{rot_min:.4f}", "float"))
        fields.append((fid, "rotation_max", f"{rot_max:.4f}", "float"))
        fields.append((fid, "zoom", f"{zoom:.4f}", "float"))

    return fields


def _decode_mesg(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode MESG (Message) fields."""
    fields = []
    fid = rec.form_id

    # DNAM: flags (uint32) — bit 0 = is_message_box
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 4:
        flags = struct.unpack_from("<I", dnam.data, 0)[0]
        fields.append((fid, "mesg_flags", f"0x{flags:08X}", "flags"))
        fields.append((fid, "is_message_box", str(bool(flags & 0x01)), "str"))

    # TNAM: display time (uint32)
    tnam = rec.get_subrecord("TNAM")
    if tnam and tnam.size >= 4:
        display_time = struct.unpack_from("<I", tnam.data, 0)[0]
        fields.append((fid, "display_time", str(display_time), "int"))

    # ITXT: button text entries (try localized string ID, fall back to raw)
    itxts = rec.get_subrecords("ITXT")
    for i, itxt in enumerate(itxts):
        if itxt.size >= 4:
            str_id = struct.unpack_from("<I", itxt.data, 0)[0]
            text = strings.lookup(str_id) if str_id else None
            if text:
                fields.append((fid, f"button_{i}", text, "str"))
            elif itxt.size > 4:
                fields.append((fid, f"button_{i}", itxt.as_string(), "str"))

    return fields


def _decode_furn(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode FURN (Furniture) fields."""
    fields = []
    fid = rec.form_id

    # FNAM: flags (uint16)
    fnam = rec.get_subrecord("FNAM")
    if fnam and fnam.size >= 2:
        flags = struct.unpack_from("<H", fnam.data, 0)[0]
        fields.append((fid, "furn_flags", f"0x{flags:04X}", "flags"))

    # WBDT: bench type + uses skill (2 bytes)
    wbdt = rec.get_subrecord("WBDT")
    if wbdt and wbdt.size >= 2:
        bench_type = wbdt.data[0]
        uses_skill = wbdt.data[1]
        fields.append((fid, "bench_type", lookup_enum(FURN_BENCH_TYPE, bench_type), "enum"))
        fields.append((fid, "uses_skill", str(uses_skill), "int"))

    # KNAM: interact keyword FormID
    knam = rec.get_subrecord("KNAM")
    if knam and knam.size >= 4:
        kw_fid = struct.unpack_from("<I", knam.data, 0)[0]
        if kw_fid:
            fields.append((fid, "interact_keyword", f"0x{kw_fid:08X}", "formid"))

    return fields


# Decoder registry
_DECODERS = {
    "WEAP": _decode_weap,
    "ARMO": _decode_armo,
    "ALCH": _decode_alch,
    "NPC_": _decode_npc,
    "QUST": _decode_qust,
    "COBJ": _decode_cobj,
    "AMMO": _decode_ammo,
    "MISC": _decode_misc,
    "BOOK": _decode_book,
    "KEYM": _decode_keym,
    "GMST": _decode_gmst,
    "GLOB": _decode_glob,
    "CONT": _decode_cont,
    "FLOR": _decode_flor,
    "LVLI": _decode_lvli,
    "LVLN": _decode_lvln,
    "PERK": _decode_perk,
    "ENCH": _decode_ench,
    "MGEF": _decode_mgef,
    "SPEL": _decode_spel,
    "OMOD": _decode_omod,
    "FACT": _decode_fact,
    "RACE": _decode_race,
    "TERM": _decode_term,
    "AVIF": _decode_avif,
    "ACTI": _decode_acti,
    "LSCR": _decode_lscr,
    "MESG": _decode_mesg,
    "FURN": _decode_furn,
}
