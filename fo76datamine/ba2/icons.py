"""Item image extraction — two-tier pipeline for actual item textures.

Tier 1 (fast): WorkshopIcons BA2 — pre-rendered item images keyed by FormID.
Tier 2 (fallback): MODL → .nif → .bgsm → diffuse texture from DX10 BA2.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fo76datamine.ba2.reader import BA2Reader
from fo76datamine.config import (
    derive_material_ba2_paths,
    derive_mesh_ba2_paths,
    derive_texture_ba2_paths,
    derive_workshop_icons_ba2_path,
)
from fo76datamine.db.store import Store


class IconExtractor:
    """Extracts item images from BA2 archives and converts to PNG."""

    def __init__(self, esm_path: Path):
        self._esm_path = esm_path
        # Lazy-loaded readers
        self._workshop_reader: Optional[BA2Reader] = None
        self._workshop_loaded = False
        self._mesh_readers: Optional[list[BA2Reader]] = None
        self._material_readers: Optional[list[BA2Reader]] = None
        self._texture_readers = None  # list[DX10Reader]
        self._texture_loaded = False

    # -- Lazy loaders --

    def _get_workshop_reader(self) -> Optional[BA2Reader]:
        if not self._workshop_loaded:
            self._workshop_loaded = True
            ws_path = derive_workshop_icons_ba2_path(self._esm_path)
            if ws_path is not None:
                try:
                    self._workshop_reader = BA2Reader(ws_path)
                except (ValueError, OSError):
                    pass
        return self._workshop_reader

    def _get_mesh_readers(self) -> list[BA2Reader]:
        if self._mesh_readers is None:
            self._mesh_readers = []
            for p in derive_mesh_ba2_paths(self._esm_path):
                try:
                    self._mesh_readers.append(BA2Reader(p))
                except (ValueError, OSError):
                    continue
        return self._mesh_readers

    def _get_material_readers(self) -> list[BA2Reader]:
        if self._material_readers is None:
            self._material_readers = []
            for p in derive_material_ba2_paths(self._esm_path):
                try:
                    self._material_readers.append(BA2Reader(p))
                except (ValueError, OSError):
                    continue
        return self._material_readers

    def _get_texture_readers(self):
        from fo76datamine.ba2.dx10_reader import DX10Reader

        if not self._texture_loaded:
            self._texture_loaded = True
            self._texture_readers = []
            for p in derive_texture_ba2_paths(self._esm_path):
                try:
                    self._texture_readers.append(DX10Reader(p))
                except (ValueError, OSError):
                    continue
        return self._texture_readers or []

    # -- Path helpers --

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Normalize a path from the ESM to match BA2 entry names."""
        normalized = path.lower().replace("\\", "/")
        for prefix in ("data/", "./"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        return normalized

    def _find_in_gnrl(self, readers: list[BA2Reader], path: str):
        """Search GNRL BA2 readers for a file. Returns (reader, entry) or (None, None)."""
        normalized = self._normalize_path(path)
        for reader in readers:
            entry = reader.find_by_path(normalized)
            if entry is not None:
                return reader, entry
        return None, None

    def _find_in_dx10(self, texture_path: str):
        """Search DX10 texture BA2s for a texture. Returns (reader, entry) or (None, None)."""
        normalized = self._normalize_path(texture_path)
        # Ensure the path starts with textures/ for BA2 lookup
        if not normalized.startswith("textures/"):
            normalized = "textures/" + normalized
        for reader in self._get_texture_readers():
            entry = reader.find_by_path(normalized)
            if entry is not None:
                return reader, entry
        return None, None

    # -- Save helpers --

    @staticmethod
    def _save_icon(dds_data: bytes, form_id: int, icons_dir: Path,
                   max_size: int) -> Optional[str]:
        """Save DDS data as thumbnail + full-res PNG. Returns thumbnail relative path."""
        from fo76datamine.ba2.texture_convert import dds_to_png

        png_name = f"{form_id:08X}.png"

        # Thumbnail
        thumb_path = icons_dir / png_name
        if not thumb_path.exists():
            if not dds_to_png(dds_data, thumb_path, max_size=max_size):
                return None

        # Full resolution
        full_dir = icons_dir / "full"
        full_path = full_dir / png_name
        if not full_path.exists():
            dds_to_png(dds_data, full_path, max_size=0)

        return f"icons/{png_name}"

    # -- Tier 1: WorkshopIcons --

    def _try_workshop_icon(self, form_id: int, icons_dir: Path,
                           max_size: int) -> Optional[str]:
        """Try to extract a pre-rendered workshop icon for the given FormID."""
        reader = self._get_workshop_reader()
        if reader is None:
            return None

        target = f"textures/interface/workshopicons/{form_id:08x}.dds"
        entry = reader.find_by_path(target)
        if entry is None:
            return None

        try:
            dds_data = reader.extract_file(entry)
        except Exception:
            return None

        return self._save_icon(dds_data, form_id, icons_dir, max_size)

    # -- Tier 2: MODL → NIF → BGSM → diffuse texture --

    def _try_model_texture(self, model_path: str, form_id: int,
                           icons_dir: Path, max_size: int) -> Optional[str]:
        """Follow MODL → NIF → BGSM → diffuse texture → PNG pipeline."""
        from fo76datamine.ba2.bgsm_reader import extract_diffuse_path
        from fo76datamine.ba2.dds import build_dds_first_mip
        from fo76datamine.ba2.nif_reader import extract_material_paths

        # Step 1: Find and extract the NIF from mesh BA2s
        reader, entry = self._find_in_gnrl(self._get_mesh_readers(), model_path)
        if reader is None or entry is None:
            return None

        try:
            nif_data = reader.extract_file(entry)
        except Exception:
            return None

        # Step 2: Parse NIF for material paths
        material_paths = extract_material_paths(nif_data)
        if not material_paths:
            return None

        # Step 3: Find and extract the first BGSM from material BA2s
        bgsm_data = None
        for mat_path in material_paths:
            mat_reader, mat_entry = self._find_in_gnrl(
                self._get_material_readers(), mat_path)
            if mat_reader is not None and mat_entry is not None:
                try:
                    bgsm_data = mat_reader.extract_file(mat_entry)
                    break
                except Exception:
                    continue
        if bgsm_data is None:
            return None

        # Step 4: Parse BGSM for diffuse texture path
        diffuse = extract_diffuse_path(bgsm_data)
        if not diffuse:
            return None

        # Step 5: Find the diffuse texture in DX10 texture BA2s
        tex_reader, tex_entry = self._find_in_dx10(diffuse)
        if tex_reader is None or tex_entry is None:
            return None

        # Step 6: Extract first chunk and build DDS
        try:
            chunk_data = tex_reader.extract_chunk(tex_entry.chunks[0])
            dds_data = build_dds_first_mip(tex_entry, chunk_data)
        except Exception:
            return None

        # Step 7: Save thumbnail + full-res
        return self._save_icon(dds_data, form_id, icons_dir, max_size)

    # -- Public API --

    def extract_icons(self, store: Store, snapshot_id: int,
                      form_ids: list[int], output_dir: Path,
                      max_size: int = 128) -> dict[int, Optional[str]]:
        """Extract item images for the given form_ids.

        Uses a two-tier strategy:
        1. WorkshopIcons BA2 — pre-rendered images by FormID (fast)
        2. MODL → NIF → BGSM → diffuse texture (slower, covers more items)

        Produces thumbnails in icons/ and full-res in icons/full/.
        Returns dict mapping form_id to relative thumbnail PNG path or None.
        """
        if not form_ids:
            return {}

        icons_dir = output_dir / "icons"
        result: dict[int, Optional[str]] = {}

        # Tier 1: WorkshopIcons (batch — check all form_ids)
        remaining = []
        for fid in form_ids:
            png_rel = self._try_workshop_icon(fid, icons_dir, max_size)
            if png_rel is not None:
                result[fid] = png_rel
            else:
                remaining.append(fid)

        # Tier 2: MODL fallback for remaining form_ids
        if remaining:
            model_paths = store.get_model_paths(snapshot_id, remaining)
            for fid in remaining:
                model = model_paths.get(fid)
                if model is None:
                    result[fid] = None
                    continue
                png_rel = self._try_model_texture(model, fid, icons_dir, max_size)
                result[fid] = png_rel

        return result
