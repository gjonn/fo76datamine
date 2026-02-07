"""Item image extraction from WorkshopIcons BA2.

Pre-rendered item images keyed by FormID, extracted from
SeventySix - WorkshopIcons.ba2 (GNRL format).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fo76datamine.ba2.reader import BA2Reader
from fo76datamine.config import derive_workshop_icons_ba2_path


class IconExtractor:
    """Extracts item images from the WorkshopIcons BA2 and converts to PNG."""

    def __init__(self, esm_path: Path):
        self._esm_path = esm_path
        self._workshop_reader: Optional[BA2Reader] = None
        self._workshop_loaded = False

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

    @staticmethod
    def _save_icon(dds_data: bytes, form_id: int, icons_dir: Path,
                   max_size: int) -> Optional[str]:
        """Save DDS data as thumbnail + full-res PNG. Returns relative path or None."""
        from fo76datamine.ba2.texture_convert import dds_to_png

        png_name = f"{form_id:08X}.png"

        # Thumbnail
        thumb_path = icons_dir / png_name
        if not thumb_path.exists():
            if not dds_to_png(dds_data, thumb_path, max_size=max_size):
                return None

        # Full resolution
        full_path = icons_dir / "full" / png_name
        if not full_path.exists():
            dds_to_png(dds_data, full_path, max_size=0)

        return f"icons/{png_name}"

    def extract_icons(self, form_ids: list[int], output_dir: Path,
                      max_size: int = 128) -> dict[int, Optional[str]]:
        """Extract workshop icons for the given form_ids.

        Produces thumbnails in icons/ and full-res in icons/full/.
        Returns dict mapping form_id to relative thumbnail PNG path or None.
        """
        if not form_ids:
            return {}

        reader = self._get_workshop_reader()
        if reader is None:
            return {fid: None for fid in form_ids}

        icons_dir = output_dir / "icons"
        result: dict[int, Optional[str]] = {}

        for fid in form_ids:
            target = f"textures/interface/workshopicons/{fid:08x}.dds"
            entry = reader.find_by_path(target)
            if entry is None:
                result[fid] = None
                continue

            try:
                dds_data = reader.extract_file(entry)
            except Exception:
                result[fid] = None
                continue

            result[fid] = self._save_icon(dds_data, fid, icons_dir, max_size)

        return result
