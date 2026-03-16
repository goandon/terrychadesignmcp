# presets.py
"""Camera preset definitions for photorealistic and animation styles.

Author: Terry kim <goandonh@gmail.com>
Co-Author: Claudie
"""

from typing import Optional

PHOTOREALISTIC_STYLES = {"photorealistic"}

ANIMATION_STYLES = {
    "anime", "semi-realistic", "manga", "cel-shaded", "chibi",
    "comic book", "pixel art", "fantasy illustration", "sci-fi concept art",
}

PHOTO_PRESETS = {
    "portrait": {
        "camera": "Sony A7IV",
        "lens": "85mm f/1.8",
        "lighting": "Soft natural window light",
    },
    "fashion": {
        "camera": "Canon EOS R5",
        "lens": "70mm f/2.0",
        "lighting": "Studio strobe, beauty dish",
    },
    "street": {
        "camera": "Fujifilm X-T5",
        "lens": "35mm f/1.4",
        "lighting": "Available natural light",
    },
    "editorial": {
        "camera": "Hasselblad X2D",
        "lens": "100mm f/2.2",
        "lighting": "Dramatic directional light",
    },
    "selfie": {
        "camera": "iPhone 15 Pro",
        "lens": "24mm wide",
        "lighting": "Natural ambient light",
    },
}

ANIMATION_PRESETS = {
    "anime_standard": {
        "lighting": "Flat cel-shading",
        "detail": "Clean linework, solid colors",
    },
    "anime_dramatic": {
        "lighting": "Dramatic rim light",
        "detail": "Dynamic angle, detailed shading",
    },
    "chibi": {
        "lighting": "Soft flat lighting",
        "detail": "2-3 head ratio, simple shading",
    },
    "game_art": {
        "lighting": "RPG portrait lighting",
        "detail": "Detailed rendering, rich textures",
    },
    "webtoon": {
        "lighting": "Soft diffused",
        "detail": "Cel-shading, pastel tones",
    },
}

VALID_OVERRIDE_KEYS = {"camera", "lens", "lighting"}

ALL_PRESET_NAMES = set(PHOTO_PRESETS.keys()) | set(ANIMATION_PRESETS.keys())


def resolve_preset(
    preset_name: Optional[str],
    style: str,
    override: Optional[dict] = None,
) -> Optional[dict]:
    """Resolve camera/style preset with optional overrides.

    Args:
        preset_name: Preset name or None for auto-detection.
        style: Art style (determines which preset pool to use).
        override: Dict of keys to override in the resolved preset.

    Returns:
        Resolved preset dict, or None if style has no preset pool.

    Raises:
        ValueError: If preset_name is not found in any pool.
    """
    result = None

    if preset_name is not None:
        if preset_name in PHOTO_PRESETS:
            result = dict(PHOTO_PRESETS[preset_name])
        elif preset_name in ANIMATION_PRESETS:
            result = dict(ANIMATION_PRESETS[preset_name])
        else:
            raise ValueError(
                f"Unknown preset '{preset_name}'. "
                f"Valid presets: {sorted(ALL_PRESET_NAMES)}"
            )
    else:
        if style in PHOTOREALISTIC_STYLES:
            result = dict(PHOTO_PRESETS["portrait"])
        elif style in ANIMATION_STYLES:
            result = dict(ANIMATION_PRESETS["anime_standard"])

    if override:
        if result is None:
            result = {}
        for key, value in override.items():
            if key in VALID_OVERRIDE_KEYS:
                result[key] = value

    return result
