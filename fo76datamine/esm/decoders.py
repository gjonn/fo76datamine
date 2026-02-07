"""Type-specific field decoders for key record types.

Decodes binary subrecord data into named field values for:
WEAP (DNAM 170 bytes), ARMO (DATA 12 bytes), ALCH (ENIT 33 bytes, DATA 4 bytes),
NPC_ (ACBS 20 bytes, DNAM 8 bytes), QUST (DATA 20 bytes),
COBJ (DNAM 8 bytes, FVPA components, CNAM/BNAM),
AMMO (DATA 8 bytes, DNAM 16 bytes), MISC/BOOK/KEYM (DATA), GMST, GLOB, etc.
"""
from __future__ import annotations

import struct
from typing import Optional

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
        fields.append((fid, "animation_type", str(struct.unpack_from("<I", d, 0)[0]), "int"))
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
        fields.append((fid, "sound_level", str(struct.unpack_from("<I", d, 112)[0]), "int"))

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
            fields.append((fid, "quest_type", str(quest_type), "int"))

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
}
