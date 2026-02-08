"""Sound file extraction from Fallout 76 Sound BA2 archives.

Extracts .xwm, .fuz, and .wav files from SeventySix - Sounds*.ba2 (GNRL format).
Optionally converts .xwm to .wav using ffmpeg.
"""
from __future__ import annotations

import fnmatch
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from fo76datamine.ba2.reader import BA2FileEntry, BA2Reader
from fo76datamine.config import derive_sounds_ba2_paths

_SOUND_EXTENSIONS = frozenset({".xwm", ".fuz", ".wav"})


@dataclass
class SoundExtractionResult:
    """Counters for a sound extraction run."""
    total_found: int = 0
    extracted: int = 0
    converted: int = 0
    errors: int = 0


def parse_fuz(data: bytes) -> bytes | None:
    """Strip lip-sync header from a .fuz file and return the xWMA audio portion.

    FUZ format: FUZE magic (4B) + version (4B) + lip_size (4B) + lip_data + xWMA audio.
    Returns the xWMA portion, or None if the data is invalid.
    """
    if len(data) < 12:
        return None
    magic = data[:4]
    if magic != b"FUZE":
        return None
    lip_size = struct.unpack_from("<I", data, 8)[0]
    audio_offset = 12 + lip_size
    if audio_offset > len(data):
        return None
    return data[audio_offset:]


def check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def convert_xwm_to_wav(xwm_data: bytes, output_path: Path) -> bool:
    """Convert xWMA data to WAV using ffmpeg. Returns True on success."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", "pipe:0", "-vn", str(output_path)],
            input=xwm_data,
            capture_output=True,
            timeout=30,
        )
        return proc.returncode == 0 and output_path.exists()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _replace_ext(path: str, new_ext: str) -> str:
    """Replace the file extension in a path string."""
    dot = path.rfind(".")
    if dot == -1:
        return path + new_ext
    return path[:dot] + new_ext


def _write_file(path: Path, data: bytes) -> None:
    """Write bytes to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class SoundExtractor:
    """Extracts sound files from Fallout 76 Sound BA2 archives."""

    def __init__(self, esm_path: Path):
        self._esm_path = esm_path
        self._readers: list[BA2Reader] | None = None

    def _get_readers(self) -> list[BA2Reader]:
        if self._readers is None:
            self._readers = []
            for ba2_path in derive_sounds_ba2_paths(self._esm_path):
                try:
                    self._readers.append(BA2Reader(ba2_path))
                except (ValueError, OSError):
                    pass
        return self._readers

    def list_sounds(
        self, filter_pattern: str | None = None
    ) -> list[tuple[BA2Reader, BA2FileEntry]]:
        """List sound files across all Sound BA2 archives.

        Returns (reader, entry) tuples for .xwm/.fuz/.wav files.
        filter_pattern supports substring match or glob (auto-detected by * or ? presence).
        """
        results: list[tuple[BA2Reader, BA2FileEntry]] = []
        is_glob = filter_pattern is not None and any(
            c in filter_pattern for c in ("*", "?")
        )

        for reader in self._get_readers():
            for entry in reader.entries:
                # Check extension
                ext = Path(entry.name).suffix.lower()
                if ext not in _SOUND_EXTENSIONS:
                    continue

                # Apply filter
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

    def extract_sounds(
        self,
        output_dir: Path,
        filter_pattern: str | None = None,
        convert: bool = True,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> SoundExtractionResult:
        """Extract sound files to output_dir.

        .fuz files have their lip-sync header stripped; the audio portion is
        converted to .wav (or saved as .xwm if ffmpeg is unavailable).
        .xwm files are converted to .wav (or saved raw).
        .wav files are saved as-is.
        Conversion failures fall back to saving raw .xwm (no data loss).
        """
        matches = self.list_sounds(filter_pattern)
        result = SoundExtractionResult(total_found=len(matches))

        has_ffmpeg = convert and check_ffmpeg()

        for i, (reader, entry) in enumerate(matches):
            if progress_callback is not None:
                progress_callback(i + 1, len(matches))

            try:
                raw_data = reader.extract_file(entry)
            except Exception:
                result.errors += 1
                continue

            ext = Path(entry.name).suffix.lower()

            if ext == ".fuz":
                audio_data = parse_fuz(raw_data)
                if audio_data is None:
                    result.errors += 1
                    continue
                # Audio portion is xWMA — try to convert
                if has_ffmpeg:
                    wav_path = output_dir / _replace_ext(entry.name, ".wav")
                    if convert_xwm_to_wav(audio_data, wav_path):
                        result.extracted += 1
                        result.converted += 1
                        continue
                # Fallback: save as .xwm
                xwm_path = output_dir / _replace_ext(entry.name, ".xwm")
                _write_file(xwm_path, audio_data)
                result.extracted += 1

            elif ext == ".xwm":
                if has_ffmpeg:
                    wav_path = output_dir / _replace_ext(entry.name, ".wav")
                    if convert_xwm_to_wav(raw_data, wav_path):
                        result.extracted += 1
                        result.converted += 1
                        continue
                # Fallback: save raw
                out_path = output_dir / entry.name
                _write_file(out_path, raw_data)
                result.extracted += 1

            elif ext == ".wav":
                out_path = output_dir / entry.name
                _write_file(out_path, raw_data)
                result.extracted += 1

        return result
