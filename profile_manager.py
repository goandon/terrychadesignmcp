"""Character profile CRUD manager (GUI-ready API).

Author: Terry kim <goandonh@gmail.com>
Co-Author: Claudie
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REQUIRED_FIELDS = ("name",)


class ProfileManager:
    """Manage character profiles as YAML files for IP management.

    Profiles are stored as ``{name.lower()}.yaml`` inside ``profiles_dir``.
    All public methods accept names case-insensitively.
    """

    def __init__(self, profiles_dir: Path | None = None) -> None:
        if profiles_dir is None:
            profiles_dir = Path(
                os.environ.get(
                    "TERRYCHA_DESIGN_PROFILES_DIR",
                    str(Path(__file__).parent / "profiles"),
                )
            )
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path_for(self, name: str) -> Path:
        return self.profiles_dir / f"{name.lower()}.yaml"

    def _load(self, path: Path) -> dict:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _save(self, path: Path, data: dict) -> None:
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _set_nested(self, data: dict, dot_path: str, value: Any) -> None:
        """Set a value in a nested dict using dot-notation path."""
        keys = dot_path.split(".")
        obj = data
        for key in keys[:-1]:
            if key not in obj or not isinstance(obj[key], dict):
                obj[key] = {}
            obj = obj[key]
        obj[keys[-1]] = value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, profile: dict) -> Path:
        """Validate required fields and save profile as ``{name.lower()}.yaml``.

        Args:
            profile: Profile dict. Must contain at least ``name``.

        Returns:
            Path to the saved YAML file.

        Raises:
            ValueError: If a required field is missing.
        """
        for field in REQUIRED_FIELDS:
            if not profile.get(field):
                raise ValueError(f"Profile is missing required field: '{field}'")

        path = self._path_for(profile["name"])
        self._save(path, profile)
        return path

    def get(self, name: str) -> dict:
        """Load and return a profile by name (case-insensitive).

        Args:
            name: Character name (case-insensitive).

        Returns:
            Profile dict.

        Raises:
            FileNotFoundError: If the profile does not exist.
        """
        path = self._path_for(name)
        if not path.exists():
            raise FileNotFoundError(f"Profile '{name}' not found in {self.profiles_dir}")
        return self._load(path)

    def update(self, name: str, updates: dict) -> dict:
        """Apply dot-notation updates to a profile and auto-increment version.

        Args:
            name: Character name (case-insensitive).
            updates: Dict of dot-notation paths → new values,
                     e.g. ``{"appearance.eyes": "blue"}``.

        Returns:
            Updated profile dict.

        Raises:
            FileNotFoundError: If the profile does not exist.
        """
        data = self.get(name)
        for dot_path, value in updates.items():
            self._set_nested(data, dot_path, value)
        data["version"] = data.get("version", 1) + 1
        path = self._path_for(name)
        self._save(path, data)
        return data

    def delete(self, name: str, confirm: bool) -> None:
        """Delete a profile file.

        Args:
            name: Character name (case-insensitive).
            confirm: Must be ``True`` to perform the deletion.

        Raises:
            ValueError: If ``confirm`` is not ``True``.
            FileNotFoundError: If the profile does not exist.
        """
        if not confirm:
            raise ValueError("Must pass confirm=True to delete a profile.")
        path = self._path_for(name)
        if not path.exists():
            raise FileNotFoundError(f"Profile '{name}' not found in {self.profiles_dir}")
        path.unlink()

    def list_profiles(self, limit: int = 50) -> list[dict]:
        """Return summary info for all profiles in ``profiles_dir``.

        Args:
            limit: Maximum number of profiles to return (default 50).

        Returns:
            List of dicts with keys ``name``, ``version``, ``style``.
        """
        results = []
        for yaml_file in sorted(self.profiles_dir.glob("*.yaml"))[:limit]:
            try:
                data = self._load(yaml_file)
                results.append(
                    {
                        "name": data.get("name", yaml_file.stem),
                        "version": data.get("version", 1),
                        "style": (data.get("generation_defaults") or {}).get("style"),
                    }
                )
            except Exception:
                # Skip corrupted files rather than crashing the listing
                pass
        return results

    def map_to_generation_params(self, name: str) -> dict:
        """Convert a profile to ``design_character`` keyword arguments.

        Mapping rules:
        - ``character_description``: composed from appearance fields
          (face, body_type, skin, eyes, distinguishing).
        - ``hair_description``: from ``appearance.hair``.
        - ``style``, ``camera_preset``, ``output_mode``, ``reference_images``:
          from ``generation_defaults``.
        - ``expression``: from ``personality`` (default ``"neutral"``).
        - ``ethereal``: from ``appearance.ethereal``.

        Args:
            name: Character name (case-insensitive).

        Returns:
            Dict of kwargs ready to pass to ``design_character``.

        Raises:
            FileNotFoundError: If the profile does not exist.
        """
        data = self.get(name)
        appearance = data.get("appearance") or {}
        personality = data.get("personality") or {}
        gen_defaults = data.get("generation_defaults") or {}

        # Build character_description from key appearance fields
        desc_parts = []
        if appearance.get("age_range"):
            desc_parts.append(appearance["age_range"])
        if appearance.get("ethnicity"):
            desc_parts.append(appearance["ethnicity"])
        if appearance.get("body_type"):
            desc_parts.append(f"{appearance['body_type']} body")
        if appearance.get("skin"):
            desc_parts.append(f"{appearance['skin']} skin")
        if appearance.get("face"):
            desc_parts.append(f"{appearance['face']} face")
        if appearance.get("eyes"):
            desc_parts.append(f"{appearance['eyes']} eyes")
        if appearance.get("distinguishing"):
            desc_parts.append(appearance["distinguishing"])

        params: dict[str, Any] = {
            "character_description": ", ".join(desc_parts) if desc_parts else "",
            "hair_description": appearance.get("hair", ""),
            "ethereal": appearance.get("ethereal", False),
            "expression": personality.get("expression", "neutral"),
        }

        # Pull generation defaults
        for key in ("style", "camera_preset", "output_mode", "reference_images"):
            if key in gen_defaults:
                params[key] = gen_defaults[key]

        return params
