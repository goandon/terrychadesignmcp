"""
Terry Character Design MCP Server - Character reference sheet generator via Vertex AI.

Generates consistent character reference image sets (6 angles/framings) using
Google's Nano Banana models. Designed for maintaining visual consistency across
video/image production pipelines.

Supported models:
  - Nano Banana 2 (Gemini 3.1 Flash Image) -- fast, cost-effective (default)
  - Nano Banana Pro (Gemini 3 Pro Image) -- highest quality

Author: Terry.Kim <goandonh@gmail.com>
Co-Author: Claudie
"""

__version__ = "0.2.0"

import os
import json
import base64
import uuid
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastmcp import FastMCP
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Configuration (reused from terrymcpnanobanana)
# ---------------------------------------------------------------------------

# Model registry
MODELS = {
    "flash": "gemini-3.1-flash-image-preview",  # Nano Banana 2 (default)
    "pro": "gemini-3-pro-image-preview",         # Nano Banana Pro
}
DEFAULT_MODEL = "flash"

# Output directory for character design sheets
OUTPUT_DIR = Path(os.environ.get(
    "TERRYCHA_DESIGN_OUTPUT_DIR",
    str(Path.home() / "terrycha_design_output"),
))

# Vertex AI settings
VERTEX_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
VERTEX_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
USE_VERTEX_AI = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true"

# Inter-shot delay to avoid rate limiting (seconds)
INTER_SHOT_DELAY = float(os.environ.get("TERRYCHA_DESIGN_DELAY", "1.0"))

# Valid option values (model-specific)
VALID_ASPECT_RATIOS_FLASH = {
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4",
    "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
}
VALID_ASPECT_RATIOS_PRO = {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}

VALID_IMAGE_SIZES_FLASH = {"512px", "1K", "2K", "4K"}
VALID_IMAGE_SIZES_PRO = {"1K", "2K", "4K"}

VALID_THINKING_LEVELS = {"minimal", "High"}

VALID_PERSON_GENERATION = {
    "DONT_ALLOW",
    "ALLOW_NONE",  # SDK alias for DONT_ALLOW
    "ALLOW_ADULT",
    "ALLOW_ALL",
}
VALID_PROMINENT_PEOPLE = {"ALLOW", "DENY"}
VALID_SAFETY_LEVELS = {
    "BLOCK_LOW_AND_ABOVE",
    "BLOCK_MEDIUM_AND_ABOVE",
    "BLOCK_ONLY_HIGH",
    "BLOCK_NONE",
}
VALID_OUTPUT_FORMATS = {"file", "base64"}

# Image output defaults
OUTPUT_MIME_TYPE = "image/jpeg"
OUTPUT_COMPRESSION_QUALITY = 85

MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# ---------------------------------------------------------------------------
# Character Design Constants
# ---------------------------------------------------------------------------

DEFAULT_BACKGROUND = "solid neutral gray background, clean studio backdrop"

# Shot definitions with rendering properties
SHOT_DEFINITIONS = {
    "full_body_front": {
        "label": "Full Body Front View",
        "label_ko": "전신 정면",
        "aspect_ratio": "3:4",
        "is_anchor": True,
        "order": 1,
    },
    "full_body_left": {
        "label": "Full Body Left Side View",
        "label_ko": "전신 좌측면",
        "aspect_ratio": "3:4",
        "is_anchor": False,
        "order": 2,
    },
    "full_body_right": {
        "label": "Full Body Right Side View",
        "label_ko": "전신 우측면",
        "aspect_ratio": "3:4",
        "is_anchor": False,
        "order": 3,
    },
    "full_body_back": {
        "label": "Full Body Back View",
        "label_ko": "전신 후면",
        "aspect_ratio": "3:4",
        "is_anchor": False,
        "order": 4,
    },
    "face_left": {
        "label": "Face Close-up Left Profile",
        "label_ko": "얼굴 좌측",
        "aspect_ratio": "1:1",
        "is_anchor": False,
        "order": 5,
    },
    "face_front": {
        "label": "Face Close-up Front",
        "label_ko": "얼굴 정면",
        "aspect_ratio": "1:1",
        "is_anchor": False,
        "order": 6,
    },
    "face_right": {
        "label": "Face Close-up Right Profile",
        "label_ko": "얼굴 우측",
        "aspect_ratio": "1:1",
        "is_anchor": False,
        "order": 7,
    },
    "upper_body": {
        "label": "Upper Body Close-up",
        "label_ko": "상체 확대",
        "aspect_ratio": "3:4",
        "is_anchor": False,
        "order": 8,
    },
}

# Prompt templates for each shot type.
# Placeholders: {character}, {outfit}, {expression}, {background}, {style}, {color_palette}
SHOT_PROMPTS = {
    "full_body_front": (
        "Full body front view character reference sheet of {character}. "
        "{outfit}. "
        "Standing in a relaxed neutral pose, facing the camera directly, "
        "arms slightly away from body to show full outfit details. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Professional character design reference sheet, clean lines, "
        "high detail, consistent proportions."
    ),
    "full_body_left": (
        "Full body left side view character reference of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the left side in perfect profile. "
        "Character's left arm, left leg, and left side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Character design reference sheet, consistent with the front view, "
        "showing left side silhouette and profile details."
    ),
    "full_body_right": (
        "Full body right side view character reference of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, viewed from the right side in perfect profile. "
        "Character's right arm, right leg, and right side of face visible. "
        "Full body visible from head to feet. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Character design reference sheet, consistent with the front view, "
        "showing right side silhouette and profile details."
    ),
    "full_body_back": (
        "Full body back view character reference of {character}. "
        "{outfit}. "
        "Standing in a neutral pose, facing directly away from the camera. "
        "Full body visible from head to feet, showing back of clothing and hair. "
        "Expression: not visible (back view). "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Character design reference sheet, consistent with the front view, "
        "showing back details of outfit and hairstyle."
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
        "Character design face reference sheet, high detail, "
        "showing left facial profile and structure."
    ),
    "face_front": (
        "Close-up face portrait character reference of {character}. "
        "Detailed facial features visible: eyes, nose, mouth, eyebrows, ears. "
        "Front view facing the camera directly. "
        "Expression: {expression}. "
        "Shoulders and neckline barely visible. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Character design face reference sheet, high detail, "
        "showing skin texture, eye color, and facial structure."
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
        "Character design face reference sheet, high detail, "
        "showing right facial profile and structure."
    ),
    "upper_body": (
        "Upper body close-up character reference of {character}. "
        "{outfit}. "
        "Framed from waist up, facing the camera, showing clothing details "
        "and accessories on the upper body. "
        "Expression: {expression}. "
        "{color_palette}"
        "{background}. "
        "{style} style. "
        "Character design reference sheet, consistent with the full body front view, "
        "high detail on face and upper body features."
    ),
}

# Consistency instruction prepended to non-anchor shots
CONSISTENCY_PREFIX = (
    "Using the provided reference image(s) as character reference, "
    "generate the SAME character with IDENTICAL appearance, features, "
    "and outfit in a different angle/framing. "
    "Maintain exact consistency in: face shape, eye color, hair color "
    "and style, skin tone, body proportions, clothing details, "
    "accessories, and makeup. "
)

# Supported art styles
SUPPORTED_STYLES = [
    "anime",
    "realistic",
    "semi-realistic",
    "3D render",
    "watercolor",
    "oil painting",
    "digital art",
    "comic book",
    "manga",
    "pixel art",
    "concept art",
    "cel-shaded",
    "chibi",
    "fantasy illustration",
    "sci-fi concept art",
    "line art",
    "pastel",
    "photorealistic",
]

VALID_SHOT_TYPES = set(SHOT_DEFINITIONS.keys())

# Default shots for reference sheet (6 shots, excludes upper_body and full_body_right)
DEFAULT_SHOTS = [
    "full_body_front",
    "full_body_left",
    "full_body_back",
    "face_left",
    "face_front",
    "face_right",
]

# ---------------------------------------------------------------------------
# Composite Sheet Constants
# ---------------------------------------------------------------------------

COMPOSITE_PADDING = 16
COMPOSITE_BORDER = 24
COMPOSITE_HEADER_HEIGHT = 60
COMPOSITE_LABEL_HEIGHT = 36
COMPOSITE_BG_COLOR = (240, 240, 240)
COMPOSITE_TEXT_COLOR = (50, 50, 50)
COMPOSITE_LABEL_COLOR = (110, 110, 110)

# Composite layout: face column (left) + body row (right)
COMPOSITE_FACE_COLUMN = ["face_left", "face_front", "face_right"]
COMPOSITE_BODY_ROW = ["full_body_front", "full_body_left", "full_body_right", "full_body_back"]

# ---------------------------------------------------------------------------
# Client initialization (reused from terrymcpnanobanana)
# ---------------------------------------------------------------------------

_client = None


def _get_client() -> genai.Client:
    """Lazy-initialize the GenAI client."""
    global _client
    if _client is None:
        if USE_VERTEX_AI:
            _client = genai.Client(
                vertexai=True,
                project=VERTEX_PROJECT,
                location=VERTEX_LOCATION,
            )
        else:
            _client = genai.Client()
    return _client


def _resolve_model(model: str) -> str:
    """Resolve a short model key ('flash'/'pro') to the full model ID."""
    key = model.lower().strip()
    if key not in MODELS:
        raise ValueError(
            f"Unknown model '{model}'. Valid options: {sorted(MODELS.keys())}"
        )
    return MODELS[key]


def _validate_params(
    model_key: str,
    aspect_ratio: str,
    image_size: str,
    output_format: str = "file",
    person_generation: Optional[str] = None,
    prominent_people: Optional[str] = None,
    safety_level: Optional[str] = None,
    thinking_level: Optional[str] = None,
    temperature: Optional[float] = None,
) -> list[str]:
    """Validate parameters against allowed values. Returns list of errors."""
    errors = []
    is_flash = model_key.lower() == "flash"
    valid_ratios = VALID_ASPECT_RATIOS_FLASH if is_flash else VALID_ASPECT_RATIOS_PRO
    valid_sizes = VALID_IMAGE_SIZES_FLASH if is_flash else VALID_IMAGE_SIZES_PRO

    if aspect_ratio not in valid_ratios:
        errors.append(
            f"Invalid aspect_ratio '{aspect_ratio}' for {model_key}. "
            f"Valid: {sorted(valid_ratios)}"
        )
    if image_size not in valid_sizes:
        errors.append(
            f"Invalid image_size '{image_size}' for {model_key}. "
            f"Valid: {sorted(valid_sizes)}"
        )
    if output_format not in VALID_OUTPUT_FORMATS:
        errors.append(
            f"Invalid output_format '{output_format}'. Valid: {sorted(VALID_OUTPUT_FORMATS)}"
        )
    if person_generation is not None and person_generation not in VALID_PERSON_GENERATION:
        errors.append(
            f"Invalid person_generation '{person_generation}'. "
            f"Valid: {sorted(VALID_PERSON_GENERATION)}"
        )
    if prominent_people is not None and prominent_people not in VALID_PROMINENT_PEOPLE:
        errors.append(
            f"Invalid prominent_people '{prominent_people}'. "
            f"Valid: {sorted(VALID_PROMINENT_PEOPLE)}"
        )
    if safety_level is not None and safety_level not in VALID_SAFETY_LEVELS:
        errors.append(
            f"Invalid safety_level '{safety_level}'. Valid: {sorted(VALID_SAFETY_LEVELS)}"
        )
    if thinking_level is not None:
        if not is_flash:
            errors.append("thinking_level is only supported with the 'flash' model.")
        elif thinking_level not in VALID_THINKING_LEVELS:
            errors.append(
                f"Invalid thinking_level '{thinking_level}'. "
                f"Valid: {sorted(VALID_THINKING_LEVELS)}"
            )
    if temperature is not None and not 0.0 <= temperature <= 2.0:
        errors.append(f"temperature must be 0.0-2.0, got {temperature}.")

    return errors


# ---------------------------------------------------------------------------
# Config builder (reused from terrymcpnanobanana)
# ---------------------------------------------------------------------------

def _build_config(
    model_key: str = DEFAULT_MODEL,
    aspect_ratio: str = "1:1",
    image_size: str = "1K",
    number_of_images: int = 1,
    person_generation: Optional[str] = None,
    prominent_people: Optional[str] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    safety_level: Optional[str] = None,
    thinking_level: Optional[str] = None,
    use_search: bool = False,
) -> types.GenerateContentConfig:
    """Build GenerateContentConfig with full ImageConfig options."""
    is_flash = model_key.lower() == "flash"

    image_cfg_kwargs = {
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
    }

    if USE_VERTEX_AI:
        image_cfg_kwargs["output_mime_type"] = OUTPUT_MIME_TYPE
        image_cfg_kwargs["output_compression_quality"] = OUTPUT_COMPRESSION_QUALITY
        if person_generation is not None:
            image_cfg_kwargs["person_generation"] = person_generation
        if prominent_people is not None:
            image_cfg_kwargs["prominent_people"] = prominent_people

    config_kwargs = {
        "response_modalities": ["TEXT", "IMAGE"],
        "image_config": types.ImageConfig(**image_cfg_kwargs),
        "candidate_count": number_of_images,
    }

    if temperature is not None:
        config_kwargs["temperature"] = temperature
    if seed is not None:
        config_kwargs["seed"] = seed

    if safety_level is not None:
        config_kwargs["safety_settings"] = [
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold=safety_level,
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold=safety_level,
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold=safety_level,
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold=safety_level,
            ),
        ]

    if is_flash and thinking_level is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=thinking_level,
            include_thoughts=True,
        )

    if is_flash and use_search:
        config_kwargs["tools"] = [types.Tool(
            google_search=types.GoogleSearch(
                search_types=types.SearchTypes(
                    web_search=types.WebSearch(),
                    image_search=types.ImageSearch(),
                )
            )
        )]

    return types.GenerateContentConfig(**config_kwargs)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _ensure_output_dir() -> Path:
    """Ensure the base output directory exists."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR


def _ensure_design_dir(character_name: str) -> Path:
    """Create and return a character-specific output directory."""
    safe_name = "".join(
        c if c.isalnum() or c in ("-", "_", " ") else "_"
        for c in character_name
    ).strip().replace(" ", "_")[:50]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    char_dir = OUTPUT_DIR / f"{safe_name}_{timestamp}"
    char_dir.mkdir(parents=True, exist_ok=True)
    return char_dir


def _save_image(
    image_data: bytes,
    prefix: str = "generated",
    output_dir: Optional[Path] = None,
) -> str:
    """Save image bytes to a file and return the absolute path."""
    out_dir = output_dir or _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    filename = f"{prefix}_{timestamp}_{short_id}.jpg"
    filepath = out_dir / filename
    filepath.write_bytes(image_data)
    return str(filepath)


def _extract_results(
    response,
    output_format: str,
    prefix: str,
    output_dir: Optional[Path] = None,
) -> dict:
    """Extract text and images from a generate_content response."""
    images = []
    text = ""
    thought = ""

    for part in response.candidates[0].content.parts:
        if hasattr(part, "thought") and part.thought:
            thought += part.text or ""
            continue
        if part.text:
            text += part.text
        elif part.inline_data:
            if output_format == "base64":
                b64 = base64.b64encode(part.inline_data.data).decode("utf-8")
                images.append({
                    "format": "base64",
                    "mime_type": part.inline_data.mime_type,
                    "data": b64,
                })
            else:
                filepath = _save_image(
                    part.inline_data.data,
                    prefix=prefix,
                    output_dir=output_dir,
                )
                images.append({
                    "format": "file",
                    "path": filepath,
                    "mime_type": part.inline_data.mime_type,
                })

    result = {"images": images, "text": text}
    if thought:
        result["thinking"] = thought
    return result


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_character_prompt(
    shot_type: str,
    character_description: str,
    outfit_description: str,
    style: str,
    hair_description: Optional[str] = None,
    accessories: Optional[str] = None,
    makeup_description: Optional[str] = None,
    distinguishing_features: Optional[str] = None,
    expression: Optional[str] = None,
    age_range: Optional[str] = None,
    body_type: Optional[str] = None,
    background_description: Optional[str] = None,
    color_palette: Optional[str] = None,
) -> str:
    """Build a complete prompt for a specific shot type from character details."""
    # Assemble character block from all detail fields
    parts = []

    if age_range:
        parts.append(age_range)

    parts.append(character_description)

    if body_type:
        parts.append(f"{body_type} body type")
    if hair_description:
        parts.append(f"Hair: {hair_description}")
    if makeup_description:
        parts.append(f"Makeup: {makeup_description}")
    if accessories:
        parts.append(f"Wearing accessories: {accessories}")
    if distinguishing_features:
        parts.append(f"Distinguishing features: {distinguishing_features}")

    character_block = ". ".join(parts)

    # Format the shot-specific template
    return SHOT_PROMPTS[shot_type].format(
        character=character_block,
        outfit=outfit_description,
        expression=expression or "neutral, calm",
        background=background_description or DEFAULT_BACKGROUND,
        style=style,
        color_palette=f"Color palette: {color_palette}. " if color_palette else "",
    )


# ---------------------------------------------------------------------------
# Composite Sheet Builder
# ---------------------------------------------------------------------------

def _create_composite_sheet(
    shot_images: dict[str, str],
    character_name: str,
    style: str,
    output_dir: Path,
) -> Optional[str]:
    """Create a composite character reference sheet from individual shot images.

    Layout:
        [face_left  ] [full_body_front] [full_body_left] [full_body_right] [full_body_back]
        [face_front ] [               ] [              ] [               ] [              ]
        [face_right ] [               ] [              ] [               ] [              ]

    Face shots stacked vertically on the left, full body shots fill the right.
    """
    # Load available images
    loaded = {}
    for shot_type in COMPOSITE_FACE_COLUMN + COMPOSITE_BODY_ROW:
        path = shot_images.get(shot_type)
        if path and Path(path).exists():
            loaded[shot_type] = Image.open(path)

    if not loaded:
        return None

    # Determine target height from the first available full body image
    body_height = None
    for s in COMPOSITE_BODY_ROW:
        if s in loaded:
            body_height = loaded[s].height
            break

    if body_height is None:
        # Fallback: derive from face images
        for s in COMPOSITE_FACE_COLUMN:
            if s in loaded:
                body_height = loaded[s].height * 3 + COMPOSITE_PADDING * 2
                break
        if body_height is None:
            return None

    pad = COMPOSITE_PADDING
    border = COMPOSITE_BORDER
    header_h = COMPOSITE_HEADER_HEIGHT
    label_h = COMPOSITE_LABEL_HEIGHT

    # Scale full body images to uniform height
    body_scaled = []
    for s in COMPOSITE_BODY_ROW:
        if s in loaded:
            img = loaded[s]
            scale = body_height / img.height
            new_w = int(img.width * scale)
            body_scaled.append((s, img.resize((new_w, body_height), Image.LANCZOS)))
        else:
            body_scaled.append((s, None))

    # Face size: 3 faces + 2 gaps = body_height
    face_size = (body_height - 2 * pad) // 3
    face_scaled = []
    for s in COMPOSITE_FACE_COLUMN:
        if s in loaded:
            face_scaled.append(
                (s, loaded[s].resize((face_size, face_size), Image.LANCZOS))
            )
        else:
            face_scaled.append((s, None))

    # Calculate canvas dimensions
    available_body = [(s, img) for s, img in body_scaled if img is not None]
    total_body_w = (
        sum(img.width for _, img in available_body)
        + pad * max(len(available_body) - 1, 0)
    ) if available_body else 0

    canvas_w = border * 2 + face_size + pad + total_body_w
    canvas_h = border * 2 + header_h + body_height + label_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), COMPOSITE_BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Load fonts: English for header, Korean for labels
    _en_font_candidates = [
        "/System/Library/Fonts/Helvetica.ttc",               # macOS
        "/System/Library/Fonts/SFNSText.ttf",                # macOS alt
        "C:/Windows/Fonts/segoeui.ttf",                      # Windows
        "C:/Windows/Fonts/arial.ttf",                        # Windows alt
    ]
    _ko_font_candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",        # macOS
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf", # macOS alt
        "C:/Windows/Fonts/malgun.ttf",                        # Windows
        "C:/Windows/Fonts/gulim.ttc",                          # Windows alt
    ]
    font_header = None
    for fp in _en_font_candidates:
        try:
            font_header = ImageFont.truetype(fp, 32)
            break
        except OSError:
            continue
    font_label = None
    for fp in _ko_font_candidates:
        try:
            font_label = ImageFont.truetype(fp, 15)
            break
        except OSError:
            continue
    if font_header is None:
        font_header = ImageFont.load_default()
    if font_label is None:
        font_label = ImageFont.load_default()

    # Draw header
    header_text = character_name
    if style:
        header_text += f"  |  {style}"
    draw.text(
        (border, border + (header_h - 36) // 2),
        header_text,
        fill=COMPOSITE_TEXT_COLOR,
        font=font_header,
    )

    y_top = border + header_h

    # Draw face column (left, stacked vertically)
    x_face = border
    for i, (shot_type, img) in enumerate(face_scaled):
        y = y_top + i * (face_size + pad)
        if img is not None:
            canvas.paste(img, (x_face, y))

    # Face column label (centered below the column)
    face_label = "얼굴 좌 / 정 / 우"
    bbox = draw.textbbox((0, 0), face_label, font=font_label)
    text_w = bbox[2] - bbox[0]
    draw.text(
        (x_face + (face_size - text_w) // 2, y_top + body_height + 6),
        face_label,
        fill=COMPOSITE_LABEL_COLOR,
        font=font_label,
    )

    # Draw body shots (right of face column)
    x = border + face_size + pad
    for shot_type, img in body_scaled:
        if img is not None:
            canvas.paste(img, (x, y_top))
            # Label centered below image
            label = SHOT_DEFINITIONS[shot_type]["label_ko"]
            bbox = draw.textbbox((0, 0), label, font=font_label)
            text_w = bbox[2] - bbox[0]
            draw.text(
                (x + (img.width - text_w) // 2, y_top + body_height + 6),
                label,
                fill=COMPOSITE_LABEL_COLOR,
                font=font_label,
            )
            x += img.width + pad

    # Save composite
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    composite_path = output_dir / f"composite_sheet_{timestamp}.jpg"
    canvas.save(composite_path, "JPEG", quality=95)

    return str(composite_path)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("terrycha-design")


@mcp.tool()
def design_character(
    character_name: str,
    character_description: str,
    style: str,
    outfit_description: str,
    hair_description: Optional[str] = None,
    accessories: Optional[str] = None,
    makeup_description: Optional[str] = None,
    distinguishing_features: Optional[str] = None,
    expression: Optional[str] = None,
    age_range: Optional[str] = None,
    body_type: Optional[str] = None,
    background_description: Optional[str] = None,
    reference_images: Optional[list[str]] = None,
    color_palette: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    image_size: str = "1K",
    person_generation: Optional[str] = "ALLOW_ALL",
    prominent_people: Optional[str] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    safety_level: Optional[str] = None,
    thinking_level: Optional[str] = None,
    output_format: str = "file",
    shots: Optional[list[str]] = None,
    both_sides: bool = False,
    composite_sheet: bool = True,
) -> str:
    """Generate a consistent character reference sheet with composite image.

    Creates a set of reference images for character consistency in video/image
    production. The first image (full body front) is generated as the "anchor,"
    then used as a reference for all subsequent shots to maintain visual consistency.

    Default shots (6):
      1. Full body front view (anchor)
      2. Full body left side view
      3. Full body back view
      4. Face close-up left profile
      5. Face close-up front
      6. Face close-up right profile

    With both_sides=True, adds full_body_right (7 shots total).
    A composite reference sheet image is auto-generated from the results.

    Args:
        character_name: Short name for the character (used for folder naming).
        character_description: Detailed physical appearance description.
        style: Art/image style. Use get_design_options() for full list.
        outfit_description: Clothing and footwear description.
        hair_description: Hairstyle details - length, style, color, bangs.
        accessories: Accessories worn by the character.
        makeup_description: Makeup details for consistent facial appearance.
        distinguishing_features: Unique visual identifiers (moles, scars, etc.).
        expression: Facial expression. Default: "neutral, calm".
        age_range: "child", "teen", "young adult", "adult", "elderly".
        body_type: "slim", "average", "athletic", "curvy", "muscular", "petite".
        background_description: Default: neutral gray studio.
        reference_images: Optional reference image paths for style guidance.
        color_palette: Overall color palette hint.
        model: "flash" (default) or "pro".
        image_size: "1K" (default), "2K", "4K". Flash also: "512px".
        person_generation: Default: "ALLOW_ALL".
        prominent_people: "ALLOW" or "DENY".
        temperature: 0.0-2.0. Recommended: 0.5-0.8 for character sheets.
        seed: Fixed seed for reproducibility.
        safety_level: Safety filter threshold.
        thinking_level: (Flash only) "minimal" or "High".
        output_format: "file" (default) or "base64".
        shots: Optional list of specific shot types to generate.
               Valid: "full_body_front", "full_body_left", "full_body_right",
               "full_body_back", "face_left", "face_front", "face_right",
               "upper_body". Default: 6 shots (no upper_body/full_body_right).
        both_sides: Add full_body_right to default shots for asymmetric
                    accessory/feature coverage. Default: False.
        composite_sheet: Auto-generate composite reference sheet image.
                         Default: True. Only works with output_format="file".

    Returns:
        JSON with character_name, output_dir, per-shot results, composite
        sheet path, summary counts, and generation settings.
    """
    # Resolve model
    try:
        model_id = _resolve_model(model)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Determine which shots to generate
    selected_shots = list(shots) if shots else list(DEFAULT_SHOTS)
    if both_sides and "full_body_right" not in selected_shots:
        # Insert after full_body_left for natural ordering
        try:
            idx = selected_shots.index("full_body_left") + 1
        except ValueError:
            idx = len(selected_shots)
        selected_shots.insert(idx, "full_body_right")
    for s in selected_shots:
        if s not in VALID_SHOT_TYPES:
            return json.dumps({
                "error": f"Unknown shot type: '{s}'. Valid: {sorted(VALID_SHOT_TYPES)}"
            })

    # Sort by defined order (anchor first)
    selected_shots.sort(key=lambda s: SHOT_DEFINITIONS[s]["order"])

    # Validate generation parameters using anchor's aspect ratio for validation
    anchor_shot = next(
        (s for s in selected_shots if SHOT_DEFINITIONS[s].get("is_anchor")),
        selected_shots[0],
    )
    errors = _validate_params(
        model_key=model,
        aspect_ratio=SHOT_DEFINITIONS[anchor_shot]["aspect_ratio"],
        image_size=image_size,
        output_format=output_format,
        person_generation=person_generation,
        prominent_people=prominent_people,
        safety_level=safety_level,
        thinking_level=thinking_level,
        temperature=temperature,
    )
    # Also validate all other shot aspect ratios
    for s in selected_shots:
        ar = SHOT_DEFINITIONS[s]["aspect_ratio"]
        valid_ratios = (
            VALID_ASPECT_RATIOS_FLASH if model.lower() == "flash"
            else VALID_ASPECT_RATIOS_PRO
        )
        if ar not in valid_ratios:
            errors.append(
                f"Shot '{s}' requires aspect_ratio '{ar}' which is not supported "
                f"by model '{model}'."
            )
    if errors:
        return json.dumps({"errors": errors})

    # Create character output directory
    char_dir = _ensure_design_dir(character_name)

    # Load user-provided reference images
    user_ref_parts = []
    if reference_images:
        max_refs = 10 if model.lower() == "flash" else 14
        # Reserve 1 slot for anchor image in subsequent shots
        allowed_user_refs = max_refs - 1
        if len(reference_images) > allowed_user_refs:
            reference_images = reference_images[:allowed_user_refs]

        for ref_path in reference_images:
            ref = Path(ref_path)
            if not ref.exists():
                return json.dumps({"error": f"Reference image not found: {ref_path}"})
            mime_type = MIME_MAP.get(ref.suffix.lower(), "image/png")
            user_ref_parts.append(
                types.Part.from_bytes(data=ref.read_bytes(), mime_type=mime_type)
            )

    client = _get_client()
    results = {}
    warnings = []
    anchor_image_path = None
    anchor_ref_part = None

    # --- Generate each shot ---
    for i, shot_type in enumerate(selected_shots):
        shot_def = SHOT_DEFINITIONS[shot_type]
        is_anchor = shot_def.get("is_anchor", False) and anchor_image_path is None

        # Build the shot prompt
        shot_prompt = _build_character_prompt(
            shot_type=shot_type,
            character_description=character_description,
            outfit_description=outfit_description,
            style=style,
            hair_description=hair_description,
            accessories=accessories,
            makeup_description=makeup_description,
            distinguishing_features=distinguishing_features,
            expression=expression,
            age_range=age_range,
            body_type=body_type,
            background_description=background_description,
            color_palette=color_palette,
        )

        # Build config with shot-specific aspect ratio
        shot_config = _build_config(
            model_key=model,
            aspect_ratio=shot_def["aspect_ratio"],
            image_size=image_size,
            number_of_images=1,
            person_generation=person_generation,
            prominent_people=prominent_people,
            temperature=temperature,
            seed=seed,
            safety_level=safety_level,
            thinking_level=thinking_level,
        )

        # Build content parts
        if is_anchor:
            # Anchor shot: text prompt only (+ user references if any)
            if user_ref_parts:
                contents = user_ref_parts + [shot_prompt]
            else:
                contents = shot_prompt
        else:
            # Subsequent shots: anchor reference + user references + consistency prompt
            content_parts = []
            if anchor_ref_part:
                content_parts.append(anchor_ref_part)
            content_parts.extend(user_ref_parts)
            content_parts.append(CONSISTENCY_PREFIX + shot_prompt)
            contents = content_parts

        try:
            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=shot_config,
            )

            extracted = _extract_results(
                response, output_format, prefix=shot_type, output_dir=char_dir,
            )

            # If this is the anchor, save reference for subsequent shots
            if is_anchor and extracted["images"]:
                first_img = extracted["images"][0]
                if first_img.get("path"):
                    anchor_image_path = first_img["path"]
                    anchor_bytes = Path(anchor_image_path).read_bytes()
                    anchor_ref_part = types.Part.from_bytes(
                        data=anchor_bytes, mime_type="image/jpeg",
                    )
                elif first_img.get("data"):
                    # base64 mode: decode for reference use
                    anchor_bytes = base64.b64decode(first_img["data"])
                    anchor_ref_part = types.Part.from_bytes(
                        data=anchor_bytes, mime_type="image/jpeg",
                    )

            results[shot_type] = {
                "status": "completed",
                "shot_type": shot_type,
                "label": shot_def["label"],
                "label_ko": shot_def["label_ko"],
                "aspect_ratio": shot_def["aspect_ratio"],
                **extracted,
            }

        except Exception as e:
            results[shot_type] = {
                "status": "failed",
                "shot_type": shot_type,
                "label": shot_def["label"],
                "label_ko": shot_def["label_ko"],
                "error": str(e),
            }
            # If anchor failed, warn about reduced consistency
            if is_anchor:
                warnings.append(
                    "Anchor image (full_body_front) failed to generate. "
                    "Remaining shots generated without character reference -- "
                    "consistency may be reduced."
                )

        # Rate limit delay between shots
        if i < len(selected_shots) - 1:
            time.sleep(INTER_SHOT_DELAY)

    # Compile final result
    completed = sum(1 for r in results.values() if r["status"] == "completed")
    failed = sum(1 for r in results.values() if r["status"] == "failed")

    final_result = {
        "character_name": character_name,
        "output_dir": str(char_dir),
        "model": model_id,
        "style": style,
        "summary": {
            "total_shots": len(selected_shots),
            "completed": completed,
            "failed": failed,
        },
        "settings": {
            "image_size": image_size,
            "person_generation": person_generation,
        },
        "shots": results,
    }

    if warnings:
        final_result["warnings"] = warnings
    if seed is not None:
        final_result["settings"]["seed"] = seed
    if temperature is not None:
        final_result["settings"]["temperature"] = temperature
    if reference_images:
        final_result["settings"]["reference_count"] = len(user_ref_parts)

    # Auto-generate composite reference sheet
    if composite_sheet and output_format == "file" and completed >= 2:
        shot_image_map = {}
        for shot_type, shot_result in results.items():
            if shot_result.get("status") == "completed" and shot_result.get("images"):
                first_img = shot_result["images"][0]
                if first_img.get("path"):
                    shot_image_map[shot_type] = first_img["path"]

        composite_path = _create_composite_sheet(
            shot_images=shot_image_map,
            character_name=character_name,
            style=style,
            output_dir=char_dir,
        )
        if composite_path:
            final_result["composite_sheet"] = composite_path

    return json.dumps(final_result, ensure_ascii=False, indent=2)


@mcp.tool()
def add_character_pose(
    prompt: str,
    reference_images: list[str],
    character_name: Optional[str] = None,
    style: Optional[str] = None,
    aspect_ratio: str = "3:4",
    model: str = DEFAULT_MODEL,
    image_size: str = "1K",
    person_generation: Optional[str] = "ALLOW_ALL",
    prominent_people: Optional[str] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    safety_level: Optional[str] = None,
    thinking_level: Optional[str] = None,
    output_format: str = "file",
) -> str:
    """Generate additional poses/angles for an existing character using references.

    Use this after design_character to create custom poses, action shots,
    expression variations, or scene-specific images while maintaining character
    consistency.

    Args:
        prompt: Description of the desired pose, expression, or scene.
                Be specific about angle, action, and framing.
                Example: "The character sitting at a desk reading a book,
                viewed from a three-quarter angle. Soft warm lighting."
        reference_images: List of existing character reference image paths.
                          Use images from the design_character output.
                          Recommended: include at least the full_body_front
                          and face_front images for best consistency.
        character_name: Character name for output folder organization.
                        If None, saves to base output directory.
        style: Art style. If None, include style in the prompt directly.
        aspect_ratio: Output aspect ratio. Default: "3:4".
        model: "flash" (default) or "pro".
        image_size: Output resolution. Default: "1K".
        person_generation: Controls people generation. Default: "ALLOW_ALL".
        prominent_people: Controls celebrity generation. "ALLOW" or "DENY".
        temperature: Randomness (0.0-2.0). Default: model default.
        seed: Fixed seed for reproducibility.
        safety_level: Safety filter threshold.
        thinking_level: (Flash only) "minimal" or "High".
        output_format: "file" (default) or "base64".

    Returns:
        JSON with generated image path (or base64 data), model response text,
        and metadata.
    """
    try:
        model_id = _resolve_model(model)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    errors = _validate_params(
        model_key=model, aspect_ratio=aspect_ratio, image_size=image_size,
        output_format=output_format, person_generation=person_generation,
        prominent_people=prominent_people, safety_level=safety_level,
        thinking_level=thinking_level, temperature=temperature,
    )
    if errors:
        return json.dumps({"errors": errors})

    max_refs = 10 if model.lower() == "flash" else 14
    if len(reference_images) > max_refs:
        return json.dumps({
            "error": f"Maximum {max_refs} reference images for model '{model}'."
        })

    # Load reference images
    content_parts = []
    for ref_path in reference_images:
        ref = Path(ref_path)
        if not ref.exists():
            return json.dumps({"error": f"Reference image not found: {ref_path}"})
        mime_type = MIME_MAP.get(ref.suffix.lower(), "image/png")
        content_parts.append(
            types.Part.from_bytes(data=ref.read_bytes(), mime_type=mime_type)
        )

    # Build prompt with consistency instruction
    full_prompt = CONSISTENCY_PREFIX
    if style:
        full_prompt += f"{style} style. "
    full_prompt += prompt
    content_parts.append(full_prompt)

    # Determine output directory
    if character_name:
        out_dir = _ensure_design_dir(character_name)
    else:
        out_dir = _ensure_output_dir()

    client = _get_client()
    config = _build_config(
        model_key=model,
        aspect_ratio=aspect_ratio,
        image_size=image_size,
        number_of_images=1,
        person_generation=person_generation,
        prominent_people=prominent_people,
        temperature=temperature,
        seed=seed,
        safety_level=safety_level,
        thinking_level=thinking_level,
    )

    response = client.models.generate_content(
        model=model_id,
        contents=content_parts,
        config=config,
    )

    extracted = _extract_results(response, output_format, prefix="pose", output_dir=out_dir)
    result = {
        "prompt": prompt,
        "reference_count": len(reference_images),
        "model": model_id,
        "output_dir": str(out_dir),
        "settings": {
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        },
        **extracted,
    }
    if style:
        result["style"] = style
    if person_generation:
        result["settings"]["person_generation"] = person_generation
    if temperature is not None:
        result["settings"]["temperature"] = temperature
    if seed is not None:
        result["settings"]["seed"] = seed

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_character_sheets(limit: int = 20) -> str:
    """List generated character reference sheets.

    Returns character sheet folders sorted by creation time (newest first),
    with image counts and file details for each character.

    Args:
        limit: Maximum number of character sheets to return (default: 20).

    Returns:
        JSON with list of character sheet folders and their contents.
    """
    out_dir = _ensure_output_dir()
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}

    # List subdirectories (character sheets)
    dirs = [
        d for d in out_dir.iterdir()
        if d.is_dir()
    ]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    dirs = dirs[:limit]

    sheets = []
    for d in dirs:
        images = [
            f for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in image_exts
        ]
        images.sort(key=lambda f: f.name)

        sheets.append({
            "name": d.name,
            "path": str(d),
            "image_count": len(images),
            "created": datetime.fromtimestamp(d.stat().st_mtime).isoformat(),
            "images": [
                {
                    "name": f.name,
                    "path": str(f),
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "shot_type": f.stem.rsplit("_", 2)[0] if "_" in f.stem else f.stem,
                }
                for f in images
            ],
        })

    # Also list any loose images in the root output dir
    loose_files = [
        f for f in out_dir.iterdir()
        if f.is_file() and f.suffix.lower() in image_exts
    ]
    loose_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    result = {
        "output_dir": str(out_dir),
        "character_sheets": sheets,
        "total_sheets": len(sheets),
    }
    if loose_files:
        result["loose_images"] = len(loose_files)

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_design_options() -> str:
    """Get all supported options for character reference sheet generation.

    Returns supported styles, shot types, model parameters, input field
    descriptions, and recommended settings for best character consistency.
    """
    options = {
        "supported_styles": SUPPORTED_STYLES,
        "default_shots": DEFAULT_SHOTS,
        "shot_types": {
            key: {
                "label": val["label"],
                "label_ko": val["label_ko"],
                "aspect_ratio": val["aspect_ratio"],
                "is_anchor": val["is_anchor"],
                "in_default": key in DEFAULT_SHOTS,
            }
            for key, val in sorted(
                SHOT_DEFINITIONS.items(), key=lambda x: x[1]["order"]
            )
        },
        "features": {
            "composite_sheet": "Auto-generates a single composite reference image",
            "both_sides": "Adds full_body_right for asymmetric accessory coverage (default: off)",
        },
        "models": {
            "flash": {
                "id": MODELS["flash"],
                "name": "Nano Banana 2 (Gemini 3.1 Flash Image)",
                "default": True,
                "aspect_ratios": sorted(VALID_ASPECT_RATIOS_FLASH),
                "image_sizes": sorted(VALID_IMAGE_SIZES_FLASH),
                "max_reference_images": 10,
                "exclusive_features": ["thinking_level"],
            },
            "pro": {
                "id": MODELS["pro"],
                "name": "Nano Banana Pro (Gemini 3 Pro Image)",
                "default": False,
                "aspect_ratios": sorted(VALID_ASPECT_RATIOS_PRO),
                "image_sizes": sorted(VALID_IMAGE_SIZES_PRO),
                "max_reference_images": 14,
                "exclusive_features": [],
            },
        },
        "input_fields": {
            "character_name": "Short name (used for folder naming)",
            "character_description": "Physical appearance: gender, skin, eyes, face, height",
            "style": "Art style (see supported_styles list)",
            "outfit_description": "Clothing: top, bottom, shoes, colors, materials",
            "hair_description": "Hair: length, style (bob/ponytail/braid), color, bangs",
            "accessories": "Accessories: glasses, earrings, necklace, hat, watch, bag",
            "makeup_description": "Makeup: lipstick, eyeshadow, eyeliner, blush, nails",
            "distinguishing_features": "Unique marks: moles, scars, freckles, tattoos, piercings",
            "expression": "Facial expression (default: neutral, calm)",
            "age_range": "Age range: child, teen, young adult, adult, elderly",
            "body_type": "Body type: slim, average, athletic, curvy, muscular, petite",
            "background_description": "Background (default: neutral gray studio)",
            "color_palette": "Overall color palette hint for the design",
            "reference_images": "List of reference image paths for style guidance",
        },
        "recommended_settings": {
            "temperature": "0.5-0.8 for consistent character sheets",
            "seed": "Use a fixed seed for maximum reproducibility",
            "image_size": "2K or 4K for production-quality reference sheets",
            "model": "pro for highest quality, flash for fast iteration",
            "background": "Use monotone/neutral backgrounds for clearest reference",
        },
        "output_dir": str(OUTPUT_DIR),
        "auth_mode": "vertex_ai" if USE_VERTEX_AI else "api_key",
        "env_vars": {
            "TERRYCHA_DESIGN_OUTPUT_DIR": "Override output directory path.",
            "TERRYCHA_DESIGN_DELAY": f"Delay between shots in seconds (default: {INTER_SHOT_DELAY}).",
            "GOOGLE_CLOUD_PROJECT": "GCP project ID (Vertex AI mode).",
            "GOOGLE_CLOUD_LOCATION": "GCP region (default: global).",
            "GOOGLE_GENAI_USE_VERTEXAI": "Set 'true' for Vertex AI, 'false' for API key.",
            "GEMINI_API_KEY": "Gemini API key (when not using Vertex AI).",
        },
    }

    return json.dumps(options, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
