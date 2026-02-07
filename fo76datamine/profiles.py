"""Config profiles for storing ESM paths."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class Profile:
    name: str
    esm: Path


@dataclass
class Config:
    default_profile: str | None = None
    profiles: dict[str, Profile] = field(default_factory=dict)


def get_config_path() -> Path:
    """Return the TOML config file path via click.get_app_dir."""
    return Path(click.get_app_dir("fo76dm")) / "config.toml"


def load_config() -> Config:
    """Read TOML config. Returns empty Config if file missing."""
    path = get_config_path()
    if not path.exists():
        return Config()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    config = Config(default_profile=data.get("default_profile"))
    for name, info in data.get("profiles", {}).items():
        config.profiles[name] = Profile(name=name, esm=Path(info["esm"]))
    return config


def save_config(config: Config) -> Path:
    """Write config to TOML using literal strings for paths."""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if config.default_profile:
        lines.append(f"default_profile = \"{config.default_profile}\"")
    lines.append("")

    for name, profile in config.profiles.items():
        lines.append(f"[profiles.{name}]")
        # Use TOML literal strings (single quotes) so backslashes aren't escapes
        lines.append(f"esm = '{profile.esm}'")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def validate_profile_name(name: str) -> bool:
    """Check that a profile name is a valid TOML bare key."""
    return bool(_PROFILE_NAME_RE.match(name))


def resolve_esm(esm: Path | None, profile_name: str | None) -> Path:
    """Resolve ESM path: --esm > --profile > default profile.

    Raises click.UsageError with a helpful message if nothing resolves.
    Validates that the resolved path actually exists.
    """
    if esm is not None:
        if not esm.exists():
            raise click.UsageError(f"ESM file not found: {esm}")
        return esm

    config = load_config()

    name = profile_name or config.default_profile
    if name is None:
        raise click.UsageError(
            "No ESM path provided. Either:\n"
            "  1. Run 'fo76dm init' to set up a profile\n"
            "  2. Pass --esm <path> explicitly\n"
            "  3. Pass --profile <name> to use a named profile"
        )

    profile = config.profiles.get(name)
    if profile is None:
        available = ", ".join(config.profiles) or "(none)"
        raise click.UsageError(
            f"Profile '{name}' not found. Available profiles: {available}"
        )

    if not profile.esm.exists():
        raise click.UsageError(
            f"ESM file not found for profile '{name}': {profile.esm}\n"
            "Run 'fo76dm init' to update the path."
        )

    return profile.esm


def resolve_profile_esm(profile_name: str) -> Path:
    """Resolve a single profile name to its ESM path (used by --vs)."""
    config = load_config()
    profile = config.profiles.get(profile_name)
    if profile is None:
        available = ", ".join(config.profiles) or "(none)"
        raise click.UsageError(
            f"Profile '{profile_name}' not found. Available profiles: {available}"
        )

    if not profile.esm.exists():
        raise click.UsageError(
            f"ESM file not found for profile '{profile_name}': {profile.esm}\n"
            "Run 'fo76dm init' to update the path."
        )

    return profile.esm
