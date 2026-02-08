"""Papyrus .pex script extraction from Fallout 76 BA2 archives.

Extracts compiled Papyrus scripts (.pex) from BA2 archives (GNRL format).
Parses PEX headers to expose script name, source file, and compilation metadata.
"""
from __future__ import annotations

import fnmatch
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from fo76datamine.ba2.reader import BA2FileEntry, BA2Reader
from fo76datamine.config import derive_scripts_ba2_paths

_SCRIPT_EXTENSIONS = frozenset({".pex"})
PEX_MAGIC = 0xFA57C0DE


@dataclass
class PexHeader:
    """Parsed PEX file header metadata."""
    major_version: int
    minor_version: int
    game_id: int
    compilation_time: int
    source_file: str
    user_name: str
    machine_name: str


@dataclass
class ScriptExtractionResult:
    """Counters for a script extraction run."""
    total_found: int = 0
    extracted: int = 0
    errors: int = 0


def _read_pex_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read a length-prefixed string from PEX data (uint16 length + bytes)."""
    if offset + 2 > len(data):
        return "", offset
    length = struct.unpack_from("<H", data, offset)[0]
    offset += 2
    if offset + length > len(data):
        return "", offset
    s = data[offset:offset + length].decode("utf-8", errors="replace")
    return s, offset + length


def parse_pex_header(data: bytes) -> PexHeader | None:
    """Parse the PEX file header.

    PEX format:
      magic (4B big-endian 0xFA57C0DE) + major (1B) + minor (1B) +
      game_id (2B) + compilation_time (8B) +
      source_file (uint16 len + bytes) + user_name + machine_name
    Returns None if invalid.
    """
    if len(data) < 16:
        return None
    magic = struct.unpack_from(">I", data, 0)[0]
    if magic != PEX_MAGIC:
        return None
    major = data[4]
    minor = data[5]
    game_id = struct.unpack_from("<H", data, 6)[0]
    compilation_time = struct.unpack_from("<Q", data, 8)[0]

    offset = 16
    source_file, offset = _read_pex_string(data, offset)
    user_name, offset = _read_pex_string(data, offset)
    machine_name, offset = _read_pex_string(data, offset)

    return PexHeader(
        major_version=major,
        minor_version=minor,
        game_id=game_id,
        compilation_time=compilation_time,
        source_file=source_file,
        user_name=user_name,
        machine_name=machine_name,
    )


def _write_file(path: Path, data: bytes) -> None:
    """Write bytes to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class ScriptExtractor:
    """Extracts Papyrus .pex scripts from Fallout 76 BA2 archives."""

    def __init__(self, esm_path: Path):
        self._esm_path = esm_path
        self._readers: list[BA2Reader] | None = None

    def _get_readers(self) -> list[BA2Reader]:
        if self._readers is None:
            self._readers = []
            for ba2_path in derive_scripts_ba2_paths(self._esm_path):
                try:
                    self._readers.append(BA2Reader(ba2_path))
                except (ValueError, OSError):
                    pass
        return self._readers

    def list_scripts(
        self, filter_pattern: str | None = None
    ) -> list[tuple[BA2Reader, BA2FileEntry]]:
        """List .pex script files across all BA2 archives.

        Returns (reader, entry) tuples.
        filter_pattern supports substring match or glob (auto-detected by * or ?).
        """
        results: list[tuple[BA2Reader, BA2FileEntry]] = []
        is_glob = filter_pattern is not None and any(
            c in filter_pattern for c in ("*", "?")
        )

        for reader in self._get_readers():
            for entry in reader.entries:
                ext = Path(entry.name).suffix.lower()
                if ext not in _SCRIPT_EXTENSIONS:
                    continue

                if filter_pattern is not None:
                    name_lower = entry.name.lower()
                    pattern_lower = filter_pattern.lower()
                    if is_glob:
                        if not fnmatch.fnmatch(name_lower, pattern_lower):
                            continue
                    else:
                        if pattern_lower not in name_lower:
                            continue

                results.append((reader, entry))
        return results

    def extract_scripts(
        self,
        output_dir: Path,
        filter_pattern: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> ScriptExtractionResult:
        """Extract .pex script files to output_dir.

        Scripts are saved as-is (compiled .pex format).
        """
        matches = self.list_scripts(filter_pattern)
        result = ScriptExtractionResult(total_found=len(matches))

        for i, (reader, entry) in enumerate(matches):
            if progress_callback is not None:
                progress_callback(i + 1, len(matches))

            try:
                raw_data = reader.extract_file(entry)
            except Exception:
                result.errors += 1
                continue

            out_path = output_dir / entry.name
            try:
                _write_file(out_path, raw_data)
                result.extracted += 1
            except OSError:
                result.errors += 1

        return result
