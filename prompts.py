# prompts.py
"""Style-specific prompt template system for character design image generation.

Provides three template sets:
  - PHOTOREALISTIC_TEMPLATES: camera/lens/lighting placeholders, professional photo framing
  - ANIMATION_TEMPLATES: style-based placeholders, migrated from server.py SHOT_PROMPTS
  - DEFAULT_TEMPLATES: generic templates for watercolor, oil painting, digital art, etc.

Routing logic in build_prompt() selects the correct template set based on style.

Author: Terry kim <goandonh@gmail.com>
Co-Author: Claudie
"""

from presets import PHOTOREALISTIC_STYLES, ANIMATION_STYLES

# ---------------------------------------------------------------------------
# Shot type registry
# ---------------------------------------------------------------------------

ALL_SHOT_TYPES: list[str] = [
    "full_body_front",
    "full_body_left",
    "full_body_back",
    "full_body_right",
    "face_front",
    "face_left",
    "face_right",
    "upper_body",
]

# ---------------------------------------------------------------------------
# Anti-overlay instruction (migrated from server.py)
# ---------------------------------------------------------------------------

NO_OVERLAY_INSTRUCTION = (
    " IMPORTANT: Generate ONLY the character illustration. "
    "Do NOT add any text, labels, annotations, captions, arrows, "
    "color palette swatches, or detail inset boxes on the image. "
    "The output must be a clean image with no overlaid graphics or text of any kind."
)

# ---------------------------------------------------------------------------
# Ethereal modifier
# ---------------------------------------------------------------------------

ETHEREAL_MODIFIER = (
    "ethereal, otherworldly beauty, delicate elfin bone structure, "
    "luminous almost translucent fair skin, dreamlike quality while maintaining "
    "photorealistic rendering"
)

# ---------------------------------------------------------------------------
# Photorealistic templates
# Placeholders: {camera}, {lens}, {lighting}, {character}, {outfit},
#               {expression}, {background}, {color_palette}
# ---------------------------------------------------------------------------

PHOTOREALISTIC_TEMPLATES: dict[str, str] = {
    "full_body_front": (
        "Professional photograph. Full body front view of {character}. "
        "{outfit}. "
        "Standing in a relaxed neutral pose, facing the camera directly, "
        "arms slightly away from body to show full outfit details. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "High-resolution, sharp focus, cinematic quality."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_left": (
        "Professional photograph. Full body left side view of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the left side in perfect profile. "
        "Character's left arm, left leg, and left side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "Consistent character appearance, left side silhouette and profile."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_back": (
        "Professional photograph. Full body back view of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, facing directly away from the camera. "
        "Full body visible from head to feet, showing back of clothing and hair. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "Consistent character appearance, showing back details of outfit and hairstyle."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_right": (
        "Professional photograph. Full body right side view of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the right side in perfect profile. "
        "Character's right arm, right leg, and right side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "Consistent character appearance, right side silhouette and profile."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_front": (
        "Professional portrait photograph. Close-up face shot of {character}. "
        "Detailed facial features visible: eyes, nose, mouth, eyebrows, ears. "
        "Front view facing the camera directly. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "High detail, sharp focus on eyes, skin pores, and facial structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_left": (
        "Professional portrait photograph. Close-up face in left side profile of {character}. "
        "Detailed facial features visible from the left side: nose bridge, "
        "jawline, left ear, eyelashes. Full left profile view. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "High detail, showing left facial profile and structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_right": (
        "Professional portrait photograph. Close-up face in right side profile of {character}. "
        "Detailed facial features visible from the right side: nose bridge, "
        "jawline, right ear, eyelashes. Full right profile view. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "High detail, showing right facial profile and structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "upper_body": (
        "Professional photograph. Upper body close-up of {character}. "
        "{outfit}. "
        "Framed from waist up, facing the camera, showing clothing details "
        "and accessories on the upper body. "
        "Expression: {expression}. "
        "{color_palette}"
        "Background: {background}. "
        "Shot on {camera}, {lens} lens. "
        "Lighting: {lighting}. "
        "Shallow depth of field. Natural skin texture with realistic details. "
        "Consistent with full body front view, high detail on face and upper body."
        + NO_OVERLAY_INSTRUCTION
    ),
}

# ---------------------------------------------------------------------------
# Animation templates (migrated from server.py SHOT_PROMPTS)
# Placeholders: {character}, {outfit}, {expression}, {background},
#               {style}, {color_palette}
# ---------------------------------------------------------------------------

ANIMATION_TEMPLATES: dict[str, str] = {
    "full_body_front": (
        "Full body front view portrait of {character}. "
        "{outfit}. "
        "Standing in a relaxed neutral pose, facing the camera directly, "
        "arms slightly away from body to show full outfit details. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Clean illustration, high detail, consistent proportions."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_left": (
        "Full body left side view portrait of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the left side in perfect profile. "
        "Character's left arm, left leg, and left side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Consistent with the front view, showing left side silhouette and profile details."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_back": (
        "Full body back view portrait of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, facing directly away from the camera. "
        "Full body visible from head to feet, showing back of clothing and hair. "
        "Expression: not visible (back view). "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Consistent with the front view, showing back details of outfit and hairstyle."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_right": (
        "Full body right side view portrait of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the right side in perfect profile. "
        "Character's right arm, right leg, and right side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Consistent with the front view, showing right side silhouette and profile details."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_front": (
        "Close-up face portrait of {character}. "
        "Detailed facial features visible: eyes, nose, mouth, eyebrows, ears. "
        "Front view facing the camera directly. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail, showing skin texture, eye color, and facial structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_left": (
        "Close-up face portrait in left side profile of {character}. "
        "Detailed facial features visible from the left side: nose bridge, "
        "jawline, left ear, eyelashes. Full left profile view. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail, showing left facial profile and structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_right": (
        "Close-up face portrait in right side profile of {character}. "
        "Detailed facial features visible from the right side: nose bridge, "
        "jawline, right ear, eyelashes. Full right profile view. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail, showing right facial profile and structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "upper_body": (
        "Upper body close-up portrait of {character}. "
        "{outfit}. "
        "Framed from waist up, facing the camera, showing clothing details "
        "and accessories on the upper body. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Consistent with the full body front view, high detail on face and upper body."
        + NO_OVERLAY_INSTRUCTION
    ),
}

# ---------------------------------------------------------------------------
# Default templates (watercolor, oil painting, digital art, concept art, etc.)
# No camera or animation-specific modifiers.
# Placeholders: {character}, {outfit}, {expression}, {background},
#               {style}, {color_palette}
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: dict[str, str] = {
    "full_body_front": (
        "Full body front view of {character}. "
        "{outfit}. "
        "Standing in a relaxed neutral pose, facing the camera directly, "
        "arms slightly away from body to show full outfit details. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail, clean composition, consistent proportions."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_left": (
        "Full body left side view of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the left side in perfect profile. "
        "Character's left arm, left leg, and left side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Consistent with the front view, showing left side silhouette and profile details."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_back": (
        "Full body back view of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, facing directly away from the camera. "
        "Full body visible from head to feet, showing back of clothing and hair. "
        "Expression: not visible (back view). "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Consistent with the front view, showing back details of outfit and hairstyle."
        + NO_OVERLAY_INSTRUCTION
    ),
    "full_body_right": (
        "Full body right side view of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the right side in perfect profile. "
        "Character's right arm, right leg, and right side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Consistent with the front view, showing right side silhouette and profile details."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_front": (
        "Close-up face portrait of {character}. "
        "Detailed facial features visible: eyes, nose, mouth, eyebrows, ears. "
        "Front view facing the camera directly. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail, showing eye color and facial structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_left": (
        "Close-up face portrait in left side profile of {character}. "
        "Detailed facial features visible from the left side: nose bridge, "
        "jawline, left ear, eyelashes. Full left profile view. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail, showing left facial profile and structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "face_right": (
        "Close-up face portrait in right side profile of {character}. "
        "Detailed facial features visible from the right side: nose bridge, "
        "jawline, right ear, eyelashes. Full right profile view. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail, showing right facial profile and structure."
        + NO_OVERLAY_INSTRUCTION
    ),
    "upper_body": (
        "Upper body close-up of {character}. "
        "{outfit}. "
        "Framed from waist up, facing the camera, showing clothing details "
        "and accessories on the upper body. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "High detail on face and upper body."
        + NO_OVERLAY_INSTRUCTION
    ),
}

# ---------------------------------------------------------------------------
# build_prompt()
# ---------------------------------------------------------------------------


def build_prompt(
    shot_type: str,
    style: str,
    character: str,
    outfit: str,
    expression: str,
    background: str,
    color_palette: str | None,
    preset: dict | None,
    ethereal: bool = False,
) -> str:
    """Build a fully resolved prompt for a given shot type and style.

    Routes to PHOTOREALISTIC_TEMPLATES, ANIMATION_TEMPLATES, or DEFAULT_TEMPLATES
    depending on the style. Fills all placeholders from the supplied arguments
    and preset dict. Appends ETHEREAL_MODIFIER when ethereal=True.

    Args:
        shot_type:     One of ALL_SHOT_TYPES.
        style:         Art style string (determines template set).
        character:     Character description string.
        outfit:        Outfit/clothing description.
        expression:    Facial expression description.
        background:    Background / environment description.
        color_palette: Optional color palette description (or None).
        preset:        Resolved preset dict from presets.resolve_preset(),
                       or None for non-preset styles.
        ethereal:      If True, append the ethereal beauty modifier.

    Returns:
        Fully resolved prompt string.

    Raises:
        KeyError: If shot_type is not in ALL_SHOT_TYPES.
        ValueError: If a photorealistic style is requested but preset lacks
                    required camera/lens/lighting keys.
    """
    if shot_type not in ALL_SHOT_TYPES:
        raise KeyError(
            f"Unknown shot_type '{shot_type}'. Valid types: {ALL_SHOT_TYPES}"
        )

    color_palette_str = f"Use a {color_palette} color scheme. " if color_palette else ""

    if style in PHOTOREALISTIC_STYLES:
        if preset is None:
            raise ValueError(
                f"Photorealistic style '{style}' requires a preset with "
                "camera, lens, and lighting keys."
            )
        template = PHOTOREALISTIC_TEMPLATES[shot_type]
        prompt = template.format(
            character=character,
            outfit=outfit,
            expression=expression,
            background=background,
            color_palette=color_palette_str,
            camera=preset["camera"],
            lens=preset["lens"],
            lighting=preset["lighting"],
        )
    elif style in ANIMATION_STYLES:
        template = ANIMATION_TEMPLATES[shot_type]
        prompt = template.format(
            character=character,
            outfit=outfit,
            expression=expression,
            background=background,
            color_palette=color_palette_str,
            style=style,
        )
    else:
        # Default: watercolor, oil painting, digital art, concept art, etc.
        template = DEFAULT_TEMPLATES[shot_type]
        prompt = template.format(
            character=character,
            outfit=outfit,
            expression=expression,
            background=background,
            color_palette=color_palette_str,
            style=style,
        )

    if ethereal:
        prompt = prompt + " " + ETHEREAL_MODIFIER + "."

    return prompt
