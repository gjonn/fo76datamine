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
    DIAL_SUBTYPE,
    DIAL_TYPE,
    ENCH_TYPE,
    EXPL_FLAGS,
    FACT_REACTION,
    FURN_BENCH_TYPE,
    MGEF_ARCHETYPE,
    OMOD_FUNCTION_TYPE,
    OMOD_VALUE_TYPE,
    PROJ_TYPE,
    QUST_TYPE,
    REGN_DATA_TYPE,
    SPEL_TYPE,
    TARGET_TYPE,
    WEAP_ANIMATION_TYPE,
    WEAP_SOUND_LEVEL,
    lookup_enum,
)
from fo76datamine.esm.conditions import (
    format_condition_summary,
    function_name,
    function_param_types,
    operator_str,
    run_on_str,
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

    # Universal fields: CTDA condition blocks (present across many record types).
    fields.extend(_decode_ctda_conditions(rec))

    return fields


def _decode_ctda_conditions(rec: Record) -> list[tuple]:
    """Decode CTDA condition blocks into diff/search-friendly fields.

    Walks subrecords sequentially to link each CTDA with its trailing
    CIS1/CIS2 string parameter subrecords. Resolves function names and
    comparison operators using function table.
    """
    fields: list[tuple] = []
    fid = rec.form_id

    # Group CTDA + trailing CIS1/CIS2 by walking subrecords in order.
    groups: list[tuple[Subrecord, str | None, str | None]] = []
    current_ctda: Subrecord | None = None
    cis1: str | None = None
    cis2: str | None = None
    for sub in rec.subrecords:
        if sub.type == "CTDA":
            if current_ctda is not None:
                groups.append((current_ctda, cis1, cis2))
            current_ctda = sub
            cis1 = cis2 = None
        elif sub.type == "CIS1" and current_ctda is not None:
            cis1 = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "CIS2" and current_ctda is not None:
            cis2 = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
    if current_ctda is not None:
        groups.append((current_ctda, cis1, cis2))

    if not groups:
        return fields

    fields.append((fid, "condition_count", str(len(groups)), "int"))

    for i, (ctda, cis1_str, cis2_str) in enumerate(groups):
        d = ctda.data
        pfx = f"condition_{i}"

        # Raw data (lossless)
        fields.append((fid, f"{pfx}_raw", d.hex(), "str"))

        # Parse standard CTDA layout (32 bytes):
        # offset 0: op_byte, 1-3: padding, 4-7: comparison (float),
        # 8-9: function (uint16), 10-11: padding,
        # 12-15: param1, 16-19: param2, 20-23: run_on,
        # 24-27: reference, 28-31: unknown
        op_byte = d[0] if ctda.size >= 1 else 0
        comp_val = struct.unpack_from("<f", d, 4)[0] if ctda.size >= 8 else 0.0
        func_idx = struct.unpack_from("<H", d, 8)[0] if ctda.size >= 10 else 0
        param1 = struct.unpack_from("<I", d, 12)[0] if ctda.size >= 16 else 0
        param2 = struct.unpack_from("<I", d, 16)[0] if ctda.size >= 20 else 0
        run_on = struct.unpack_from("<I", d, 20)[0] if ctda.size >= 24 else 0
        ref_fid = struct.unpack_from("<I", d, 24)[0] if ctda.size >= 28 else 0

        # Function name and operator
        fields.append((fid, f"{pfx}_function", str(func_idx), "int"))
        fields.append((fid, f"{pfx}_function_name", function_name(func_idx), "str"))
        fields.append((fid, f"{pfx}_operator", operator_str(op_byte), "str"))

        # Comparison value
        if ctda.size >= 8:
            fields.append((fid, f"{pfx}_comparison", f"{comp_val:.6f}", "float"))

        # Parameters (raw hex preserved, plus string values from CIS1/CIS2)
        if ctda.size >= 16:
            fields.append((fid, f"{pfx}_param1_hex", f"0x{param1:08X}", "str"))
        if cis1_str:
            fields.append((fid, f"{pfx}_param1_string", cis1_str, "str"))
        if ctda.size >= 20:
            fields.append((fid, f"{pfx}_param2_hex", f"0x{param2:08X}", "str"))
        if cis2_str:
            fields.append((fid, f"{pfx}_param2_string", cis2_str, "str"))

        # Run-on target
        if ctda.size >= 24:
            fields.append((fid, f"{pfx}_run_on", run_on_str(run_on), "str"))

        # Reference FormID
        if ctda.size >= 28 and ref_fid != 0 and ref_fid != 0xFFFFFFFF:
            fields.append((fid, f"{pfx}_reference", f"0x{ref_fid:08X}", "formid"))

        # Human-readable summary
        if ctda.size >= 10:
            summary = format_condition_summary(
                func_idx, op_byte, comp_val,
                param1, param2, cis1_str, cis2_str, run_on,
            )
            fields.append((fid, f"{pfx}_summary", summary, "str"))

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


def _decode_aact(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode AACT (Action) fields."""
    fields = []
    fid = rec.form_id

    # CNAM: color (uint32 RGBA)
    cnam = rec.get_subrecord("CNAM")
    if cnam and cnam.size >= 4:
        fields.append((fid, "color", f"0x{struct.unpack_from('<I', cnam.data, 0)[0]:08X}", "flags"))

    return fields


def _decode_stat(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode STAT (Static) fields."""
    fields = []
    fid = rec.form_id

    # DNAM: max angle (float) + leaf amplitude/frequency
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 4:
        max_angle = struct.unpack_from("<f", dnam.data, 0)[0]
        fields.append((fid, "max_angle", f"{max_angle:.2f}", "float"))
        if dnam.size >= 8:
            leaf_amplitude = struct.unpack_from("<f", dnam.data, 4)[0]
            fields.append((fid, "leaf_amplitude", f"{leaf_amplitude:.4f}", "float"))
            if dnam.size >= 12:
                leaf_frequency = struct.unpack_from("<f", dnam.data, 8)[0]
                fields.append((fid, "leaf_frequency", f"{leaf_frequency:.4f}", "float"))

    return fields


def _decode_mstt(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode MSTT (Moveable Static) fields."""
    fields = []
    fid = rec.form_id

    # DATA: flags (byte)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 1:
        flags = data.data[0]
        fields.append((fid, "mstt_flags", f"0x{flags:02X}", "flags"))
        fields.append((fid, "on_local_map", str(bool(flags & 0x01)), "str"))

    # SNAM: sound FormID
    snam = rec.get_subrecord("SNAM")
    if snam and snam.size >= 4:
        sound_fid = struct.unpack_from("<I", snam.data, 0)[0]
        if sound_fid:
            fields.append((fid, "sound", f"0x{sound_fid:08X}", "formid"))

    return fields


def _decode_cell(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode CELL (Cell) fields."""
    fields = []
    fid = rec.form_id

    # DATA: cell flags (uint16)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 2:
        flags = struct.unpack_from("<H", data.data, 0)[0]
        fields.append((fid, "cell_flags", f"0x{flags:04X}", "flags"))
        fields.append((fid, "is_interior", str(bool(flags & 0x0001)), "str"))
        fields.append((fid, "has_water", str(bool(flags & 0x0002)), "str"))
        fields.append((fid, "public_area", str(bool(flags & 0x0020)), "str"))

    # XCLC: grid position (int32 x, int32 y)
    xclc = rec.get_subrecord("XCLC")
    if xclc and xclc.size >= 8:
        grid_x = struct.unpack_from("<i", xclc.data, 0)[0]
        grid_y = struct.unpack_from("<i", xclc.data, 4)[0]
        fields.append((fid, "grid_x", str(grid_x), "int"))
        fields.append((fid, "grid_y", str(grid_y), "int"))

    # XNAM: water height (float)
    xnam = rec.get_subrecord("XNAM")
    if xnam and xnam.size >= 4:
        water_height = struct.unpack_from("<f", xnam.data, 0)[0]
        fields.append((fid, "water_height", f"{water_height:.2f}", "float"))

    # XCMO: music type FormID
    xcmo = rec.get_subrecord("XCMO")
    if xcmo and xcmo.size >= 4:
        music_fid = struct.unpack_from("<I", xcmo.data, 0)[0]
        if music_fid:
            fields.append((fid, "music_type", f"0x{music_fid:08X}", "formid"))

    return fields


def _decode_wrld(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode WRLD (Worldspace) fields."""
    fields = []
    fid = rec.form_id

    # DNAM: default land height (float) + default water height (float)
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 8:
        fields.append((fid, "default_land_height", f"{struct.unpack_from('<f', dnam.data, 0)[0]:.2f}", "float"))
        fields.append((fid, "default_water_height", f"{struct.unpack_from('<f', dnam.data, 4)[0]:.2f}", "float"))

    # MNAM: map dimensions
    mnam = rec.get_subrecord("MNAM")
    if mnam and mnam.size >= 16:
        d = mnam.data
        fields.append((fid, "usable_x", str(struct.unpack_from("<I", d, 0)[0]), "int"))
        fields.append((fid, "usable_y", str(struct.unpack_from("<I", d, 4)[0]), "int"))

    # NAM0: min world coords
    nam0 = rec.get_subrecord("NAM0")
    if nam0 and nam0.size >= 8:
        fields.append((fid, "min_x", f"{struct.unpack_from('<f', nam0.data, 0)[0]:.2f}", "float"))
        fields.append((fid, "min_y", f"{struct.unpack_from('<f', nam0.data, 4)[0]:.2f}", "float"))

    # NAM9: max world coords
    nam9 = rec.get_subrecord("NAM9")
    if nam9 and nam9.size >= 8:
        fields.append((fid, "max_x", f"{struct.unpack_from('<f', nam9.data, 0)[0]:.2f}", "float"))
        fields.append((fid, "max_y", f"{struct.unpack_from('<f', nam9.data, 4)[0]:.2f}", "float"))

    # CNAM: climate FormID
    cnam = rec.get_subrecord("CNAM")
    if cnam and cnam.size >= 4:
        climate_fid = struct.unpack_from("<I", cnam.data, 0)[0]
        if climate_fid:
            fields.append((fid, "climate", f"0x{climate_fid:08X}", "formid"))

    # WNAM: water type FormID
    wnam = rec.get_subrecord("WNAM")
    if wnam and wnam.size >= 4:
        water_fid = struct.unpack_from("<I", wnam.data, 0)[0]
        if water_fid:
            fields.append((fid, "water_type", f"0x{water_fid:08X}", "formid"))

    return fields


def _decode_lctn(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode LCTN (Location) fields."""
    fields = []
    fid = rec.form_id

    # PNAM: parent location FormID
    pnam = rec.get_subrecord("PNAM")
    if pnam and pnam.size >= 4:
        parent_fid = struct.unpack_from("<I", pnam.data, 0)[0]
        if parent_fid:
            fields.append((fid, "parent_location", f"0x{parent_fid:08X}", "formid"))

    # LCEC: encounter zone FormID
    lcec = rec.get_subrecord("LCEC")
    if lcec and lcec.size >= 4:
        enc_zone = struct.unpack_from("<I", lcec.data, 0)[0]
        if enc_zone:
            fields.append((fid, "encounter_zone", f"0x{enc_zone:08X}", "formid"))

    # CNAM: location color (uint32)
    cnam = rec.get_subrecord("CNAM")
    if cnam and cnam.size >= 4:
        fields.append((fid, "location_color", f"0x{struct.unpack_from('<I', cnam.data, 0)[0]:08X}", "flags"))

    # NAM1: minimum level (int32)
    nam1 = rec.get_subrecord("NAM1")
    if nam1 and nam1.size >= 4:
        min_level = struct.unpack_from("<i", nam1.data, 0)[0]
        fields.append((fid, "min_level", str(min_level), "int"))

    return fields


def _decode_regn(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode REGN (Region) fields."""
    fields = []
    fid = rec.form_id

    # RDMP: map name string
    rdmp = rec.get_subrecord("RDMP")
    if rdmp and rdmp.size > 1:
        fields.append((fid, "map_name", rdmp.as_string(), "str"))

    # RDAT: region data headers (8 bytes each: type uint32 + flags uint32)
    rdats = rec.get_subrecords("RDAT")
    for i, rdat in enumerate(rdats):
        if rdat.size >= 8:
            data_type = struct.unpack_from("<I", rdat.data, 0)[0]
            flags = struct.unpack_from("<I", rdat.data, 4)[0]
            fields.append((fid, f"region_data_{i}_type", lookup_enum(REGN_DATA_TYPE, data_type), "enum"))
            fields.append((fid, f"region_data_{i}_flags", f"0x{flags:08X}", "flags"))

    # RDWT: weather entries (12 bytes each: weather FormID + weight + global FormID)
    rdwt = rec.get_subrecord("RDWT")
    if rdwt and rdwt.size >= 12:
        count = rdwt.size // 12
        for j in range(count):
            offset = j * 12
            weather_fid = struct.unpack_from("<I", rdwt.data, offset)[0]
            weight = struct.unpack_from("<I", rdwt.data, offset + 4)[0]
            if weather_fid:
                fields.append((fid, f"weather_{j}_id", f"0x{weather_fid:08X}", "formid"))
                fields.append((fid, f"weather_{j}_weight", str(weight), "int"))

    return fields


def _decode_wthr(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode WTHR (Weather) fields."""
    fields = []
    fid = rec.form_id

    # DNAM: fog distances (32+ bytes)
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 24:
        d = dnam.data
        fields.append((fid, "fog_day_near", f"{struct.unpack_from('<f', d, 0)[0]:.2f}", "float"))
        fields.append((fid, "fog_day_far", f"{struct.unpack_from('<f', d, 4)[0]:.2f}", "float"))
        fields.append((fid, "fog_night_near", f"{struct.unpack_from('<f', d, 8)[0]:.2f}", "float"))
        fields.append((fid, "fog_night_far", f"{struct.unpack_from('<f', d, 12)[0]:.2f}", "float"))
        fields.append((fid, "fog_day_power", f"{struct.unpack_from('<f', d, 16)[0]:.4f}", "float"))
        fields.append((fid, "fog_night_power", f"{struct.unpack_from('<f', d, 20)[0]:.4f}", "float"))

    # DATA: wind/precipitation (19+ bytes)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 19:
        d = data.data
        fields.append((fid, "wind_speed", str(d[0]), "int"))
        fields.append((fid, "trans_delta", str(d[4]), "int"))
        fields.append((fid, "sun_glare", str(d[5]), "int"))
        fields.append((fid, "sun_damage", str(d[6]), "int"))
        fields.append((fid, "precip_begin_fade_in", str(d[7]), "int"))
        fields.append((fid, "precip_end_fade_out", str(d[8]), "int"))

    # Count cloud textures (subrecords like 00TX, 10TX, etc.)
    cloud_count = 0
    for sub in rec.subrecords:
        if len(sub.type) == 4 and sub.type.endswith("0TX") and sub.size > 1:
            cloud_count += 1
    if cloud_count:
        fields.append((fid, "cloud_texture_count", str(cloud_count), "int"))

    return fields


def _decode_dial(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode DIAL (Dialog Topic) fields."""
    fields = []
    fid = rec.form_id

    # DATA: topic flags, type, subtype
    data = rec.get_subrecord("DATA")
    if data and data.size >= 1:
        topic_flags = data.data[0]
        fields.append((fid, "topic_flags", f"0x{topic_flags:02X}", "flags"))
        if data.size >= 2:
            topic_type = data.data[1]
            fields.append((fid, "topic_type", lookup_enum(DIAL_TYPE, topic_type), "enum"))
        if data.size >= 4:
            subtype = struct.unpack_from("<H", data.data, 2)[0]
            fields.append((fid, "topic_subtype", lookup_enum(DIAL_SUBTYPE, subtype), "enum"))

    # SNAM: top-level branch FormID
    snam = rec.get_subrecord("SNAM")
    if snam and snam.size >= 4:
        branch_fid = struct.unpack_from("<I", snam.data, 0)[0]
        if branch_fid:
            fields.append((fid, "branch", f"0x{branch_fid:08X}", "formid"))

    # QNAM: quest FormID
    qnam = rec.get_subrecord("QNAM")
    if qnam and qnam.size >= 4:
        quest_fid = struct.unpack_from("<I", qnam.data, 0)[0]
        if quest_fid:
            fields.append((fid, "quest", f"0x{quest_fid:08X}", "formid"))

    return fields


def _decode_info(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode INFO (Dialog Response) fields."""
    fields = []
    fid = rec.form_id

    # ENAM: info flags (uint16) + hours until reset (uint16)
    enam = rec.get_subrecord("ENAM")
    if enam and enam.size >= 2:
        flags = struct.unpack_from("<H", enam.data, 0)[0]
        fields.append((fid, "info_flags", f"0x{flags:04X}", "flags"))
        if enam.size >= 4:
            hours_until_reset = struct.unpack_from("<H", enam.data, 2)[0]
            if hours_until_reset:
                fields.append((fid, "hours_until_reset", str(hours_until_reset), "int"))

    # NAM1: response text (raw embedded string)
    nam1 = rec.get_subrecord("NAM1")
    if nam1 and nam1.size > 1:
        fields.append((fid, "response_text", nam1.as_string(), "str"))

    # RNAM: response text localized string ID
    rnam = rec.get_subrecord("RNAM")
    if rnam and rnam.size >= 4:
        str_id = struct.unpack_from("<I", rnam.data, 0)[0]
        if str_id:
            text = strings.lookup(str_id)
            fields.append((fid, "response_text_loc", text or f"0x{str_id:08X}", "str"))

    # CTDA: condition count
    ctdas = rec.get_subrecords("CTDA")
    if ctdas:
        fields.append((fid, "condition_count", str(len(ctdas)), "int"))

    return fields


def _decode_idle(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode IDLE (Idle Animation) fields."""
    fields = []
    fid = rec.form_id

    # DNAM: animation file path
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size > 1:
        fields.append((fid, "animation_file", dnam.as_string(), "str"))

    # ENAM: animation event string
    enam = rec.get_subrecord("ENAM")
    if enam and enam.size > 1:
        fields.append((fid, "animation_event", enam.as_string(), "str"))

    # ANAM: parent idle FormID
    anam = rec.get_subrecord("ANAM")
    if anam and anam.size >= 4:
        parent_fid = struct.unpack_from("<I", anam.data, 0)[0]
        if parent_fid:
            fields.append((fid, "parent_idle", f"0x{parent_fid:08X}", "formid"))

    return fields


def _decode_entm(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode ENTM (Entitlement) fields — Atomic Shop items."""
    fields = []
    fid = rec.form_id

    # BNAM: entitlement ID string
    bnam = rec.get_subrecord("BNAM")
    if bnam and bnam.size > 1:
        fields.append((fid, "entitlement_id", bnam.as_string(), "str"))

    # DNAM: price (uint32) + flags (uint32)
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 4:
        price = struct.unpack_from("<I", dnam.data, 0)[0]
        fields.append((fid, "price", str(price), "int"))
        if dnam.size >= 8:
            flags = struct.unpack_from("<I", dnam.data, 4)[0]
            fields.append((fid, "entm_flags", f"0x{flags:08X}", "flags"))

    # INAM: image path string
    inam = rec.get_subrecord("INAM")
    if inam and inam.size > 1:
        fields.append((fid, "image_path", inam.as_string(), "str"))

    return fields


def _decode_scol(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode SCOL (Static Collection) fields."""
    fields = []
    fid = rec.form_id

    # ONAM: static FormIDs (each ONAM begins a group with following DATA placements)
    onams = rec.get_subrecords("ONAM")
    for i, onam in enumerate(onams):
        if onam.size >= 4:
            static_fid = struct.unpack_from("<I", onam.data, 0)[0]
            fields.append((fid, f"static_{i}_ref", f"0x{static_fid:08X}", "formid"))

    # Count total placements from DATA subrecords (28 bytes each: pos XYZ + rot XYZ + scale)
    datas = rec.get_subrecords("DATA")
    placement_count = 0
    for data_sub in datas:
        if data_sub.size >= 28:
            placement_count += data_sub.size // 28
    if placement_count:
        fields.append((fid, "placement_count", str(placement_count), "int"))

    return fields


def _decode_expl(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode EXPL (Explosion) fields."""
    fields = []
    fid = rec.form_id

    # DATA: explosion data struct (40+ bytes)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 40:
        d = data.data
        light_fid = struct.unpack_from("<I", d, 0)[0]
        if light_fid:
            fields.append((fid, "light", f"0x{light_fid:08X}", "formid"))
        sound1_fid = struct.unpack_from("<I", d, 4)[0]
        if sound1_fid:
            fields.append((fid, "sound1", f"0x{sound1_fid:08X}", "formid"))
        sound2_fid = struct.unpack_from("<I", d, 8)[0]
        if sound2_fid:
            fields.append((fid, "sound2", f"0x{sound2_fid:08X}", "formid"))
        imad_fid = struct.unpack_from("<I", d, 12)[0]
        if imad_fid:
            fields.append((fid, "image_space_modifier", f"0x{imad_fid:08X}", "formid"))
        fields.append((fid, "force", f"{struct.unpack_from('<f', d, 16)[0]:.2f}", "float"))
        fields.append((fid, "damage", f"{struct.unpack_from('<f', d, 20)[0]:.2f}", "float"))
        fields.append((fid, "radius", f"{struct.unpack_from('<f', d, 24)[0]:.2f}", "float"))
        flags = struct.unpack_from("<I", d, 36)[0]
        fields.append((fid, "expl_flags", f"0x{flags:08X}", "flags"))

    return fields


def _decode_proj(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode PROJ (Projectile) fields."""
    fields = []
    fid = rec.form_id

    # DATA: projectile data struct (48+ bytes)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 36:
        d = data.data
        flags = struct.unpack_from("<I", d, 0)[0]
        fields.append((fid, "proj_flags", f"0x{flags:08X}", "flags"))
        proj_type = struct.unpack_from("<H", d, 4)[0]
        fields.append((fid, "proj_type", lookup_enum(PROJ_TYPE, proj_type), "enum"))
        fields.append((fid, "gravity", f"{struct.unpack_from('<f', d, 8)[0]:.4f}", "float"))
        fields.append((fid, "speed", f"{struct.unpack_from('<f', d, 12)[0]:.2f}", "float"))
        fields.append((fid, "range", f"{struct.unpack_from('<f', d, 16)[0]:.2f}", "float"))
        light_fid = struct.unpack_from("<I", d, 20)[0]
        if light_fid:
            fields.append((fid, "light", f"0x{light_fid:08X}", "formid"))
        muzzle_light_fid = struct.unpack_from("<I", d, 24)[0]
        if muzzle_light_fid:
            fields.append((fid, "muzzle_light", f"0x{muzzle_light_fid:08X}", "formid"))
        expl_fid = struct.unpack_from("<I", d, 28)[0]
        if expl_fid:
            fields.append((fid, "explosion", f"0x{expl_fid:08X}", "formid"))
        sound_fid = struct.unpack_from("<I", d, 32)[0]
        if sound_fid:
            fields.append((fid, "sound", f"0x{sound_fid:08X}", "formid"))

    return fields


def _decode_hazd(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode HAZD (Hazard) fields."""
    fields = []
    fid = rec.form_id

    # DATA: hazard data struct (28+ bytes)
    data = rec.get_subrecord("DATA")
    if data and data.size >= 28:
        d = data.data
        fields.append((fid, "limit", str(struct.unpack_from("<I", d, 0)[0]), "int"))
        fields.append((fid, "radius", f"{struct.unpack_from('<f', d, 4)[0]:.2f}", "float"))
        fields.append((fid, "lifetime", f"{struct.unpack_from('<f', d, 8)[0]:.2f}", "float"))
        imad_fid = struct.unpack_from("<I", d, 12)[0]
        if imad_fid:
            fields.append((fid, "image_space_modifier", f"0x{imad_fid:08X}", "formid"))
        flags = struct.unpack_from("<I", d, 16)[0]
        fields.append((fid, "hazd_flags", f"0x{flags:08X}", "flags"))
        spell_fid = struct.unpack_from("<I", d, 20)[0]
        if spell_fid:
            fields.append((fid, "spell", f"0x{spell_fid:08X}", "formid"))
        light_fid = struct.unpack_from("<I", d, 24)[0]
        if light_fid:
            fields.append((fid, "light", f"0x{light_fid:08X}", "formid"))

    return fields


def _decode_watr(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode WATR (Water) fields."""
    fields = []
    fid = rec.form_id

    # DNAM: water properties (opacity, colors, etc.)
    dnam = rec.get_subrecord("DNAM")
    if dnam and dnam.size >= 16:
        d = dnam.data
        fields.append((fid, "opacity", f"{struct.unpack_from('<f', d, 0)[0]:.4f}", "float"))
        if dnam.size >= 12:
            fields.append((fid, "shallow_color_r", str(d[4]), "int"))
            fields.append((fid, "shallow_color_g", str(d[5]), "int"))
            fields.append((fid, "shallow_color_b", str(d[6]), "int"))
            fields.append((fid, "deep_color_r", str(d[8]), "int"))
            fields.append((fid, "deep_color_g", str(d[9]), "int"))
            fields.append((fid, "deep_color_b", str(d[10]), "int"))

    # ANAM: fog near amount (float)
    anam = rec.get_subrecord("ANAM")
    if anam and anam.size >= 4:
        fields.append((fid, "fog_near_amount", f"{struct.unpack_from('<f', anam.data, 0)[0]:.4f}", "float"))

    # FNAM: flags
    fnam = rec.get_subrecord("FNAM")
    if fnam and fnam.size >= 1:
        fields.append((fid, "watr_flags", f"0x{fnam.data[0]:02X}", "flags"))

    # SNAM: spell FormID (damage on contact)
    snam = rec.get_subrecord("SNAM")
    if snam and snam.size >= 4:
        spell_fid = struct.unpack_from("<I", snam.data, 0)[0]
        if spell_fid:
            fields.append((fid, "damage_spell", f"0x{spell_fid:08X}", "formid"))

    return fields


def _decode_curv(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode CURV (Curve Table) fields."""
    fields = []
    fid = rec.form_id

    # JASF: JSON asset file path
    jasf = rec.get_subrecord("JASF")
    if jasf and jasf.size > 1:
        fields.append((fid, "json_asset_file", jasf.as_string(), "str"))

    # CRVE: embedded curve entries (variable size)
    crves = rec.get_subrecords("CRVE")
    if crves:
        fields.append((fid, "curve_entry_count", str(len(crves)), "int"))

    return fields


def _decode_cncy(rec: Record, strings: StringTable) -> list[tuple]:
    """Decode CNCY (Currency) fields."""
    fields = []
    fid = rec.form_id

    # DURL: display name string
    durl = rec.get_subrecord("DURL")
    if durl and durl.size > 1:
        fields.append((fid, "display_name", durl.as_string(), "str"))

    # MXCT: max count (uint32)
    mxct = rec.get_subrecord("MXCT")
    if mxct and mxct.size >= 4:
        max_count = struct.unpack_from("<I", mxct.data, 0)[0]
        fields.append((fid, "max_count", str(max_count), "int"))

    # CRTY: currency type (uint16)
    crty = rec.get_subrecord("CRTY")
    if crty and crty.size >= 2:
        currency_type = struct.unpack_from("<H", crty.data, 0)[0]
        fields.append((fid, "currency_type", str(currency_type), "int"))

    # FNAM: flags (uint32)
    fnam = rec.get_subrecord("FNAM")
    if fnam and fnam.size >= 4:
        flags = struct.unpack_from("<I", fnam.data, 0)[0]
        if flags:
            fields.append((fid, "cncy_flags", f"0x{flags:08X}", "flags"))

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
    "AACT": _decode_aact,
    "STAT": _decode_stat,
    "MSTT": _decode_mstt,
    "CELL": _decode_cell,
    "WRLD": _decode_wrld,
    "LCTN": _decode_lctn,
    "REGN": _decode_regn,
    "WTHR": _decode_wthr,
    "DIAL": _decode_dial,
    "INFO": _decode_info,
    "IDLE": _decode_idle,
    "ENTM": _decode_entm,
    "SCOL": _decode_scol,
    "EXPL": _decode_expl,
    "PROJ": _decode_proj,
    "HAZD": _decode_hazd,
    "WATR": _decode_watr,
    "CURV": _decode_curv,
    "CNCY": _decode_cncy,
}
