"""Generation orchestration for terrychadesignmcp — Gemini API interaction, safety retry, prompt assembly.

Author: Terry.Kim <goandonh@gmail.com>
Co-Author: Claudie
"""

import base64
import json
import logging
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from google import genai
from google.genai import types

from image_io import save_image


# ---------------------------------------------------------------------------
# Text model registry (for text-only Gemini calls)
# ---------------------------------------------------------------------------

TEXT_MODELS = {
    "flash": "gemini-2.0-flash",
}


# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client = None


def get_client(
    use_vertex_ai: bool,
    project: str = "",
    location: str = "global",
) -> genai.Client:
    """Lazy-initialize the GenAI client."""
    global _client
    if _client is None:
        if use_vertex_ai:
            _client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
        else:
            _client = genai.Client()
    return _client


def resolve_model(model_key: str, models: dict) -> str:
    """Resolve a short model key ('flash'/'pro') to the full model ID."""
    key = model_key.lower().strip()
    if key not in models:
        raise ValueError(
            f"Unknown model '{model_key}'. Valid options: {sorted(models.keys())}"
        )
    return models[key]


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------

def validate_params(
    model_key: str,
    aspect_ratio: str,
    image_size: str,
    output_format: str = "file",
    person_generation: Optional[str] = None,
    prominent_people: Optional[str] = None,
    safety_level: Optional[str] = None,
    thinking_level: Optional[str] = None,
    temperature: Optional[float] = None,
    *,
    valid_ratios_flash: set,
    valid_ratios_pro: set,
    valid_sizes_flash: set,
    valid_sizes_pro: set,
    valid_formats: set,
    valid_person_gen: set,
    valid_prominent: set,
    valid_safety: set,
    valid_thinking: set,
) -> list[str]:
    """Validate parameters against allowed values. Returns list of errors."""
    errors = []
    is_flash = model_key.lower() == "flash"
    valid_ratios = valid_ratios_flash if is_flash else valid_ratios_pro
    valid_sizes = valid_sizes_flash if is_flash else valid_sizes_pro

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
    if output_format not in valid_formats:
        errors.append(
            f"Invalid output_format '{output_format}'. Valid: {sorted(valid_formats)}"
        )
    if person_generation is not None and person_generation not in valid_person_gen:
        errors.append(
            f"Invalid person_generation '{person_generation}'. "
            f"Valid: {sorted(valid_person_gen)}"
        )
    if prominent_people is not None and prominent_people not in valid_prominent:
        errors.append(
            f"Invalid prominent_people '{prominent_people}'. "
            f"Valid: {sorted(valid_prominent)}"
        )
    if safety_level is not None and safety_level not in valid_safety:
        errors.append(
            f"Invalid safety_level '{safety_level}'. Valid: {sorted(valid_safety)}"
        )
    if thinking_level is not None:
        if not is_flash:
            errors.append("thinking_level is only supported with the 'flash' model.")
        elif thinking_level not in valid_thinking:
            errors.append(
                f"Invalid thinking_level '{thinking_level}'. "
                f"Valid: {sorted(valid_thinking)}"
            )
    if temperature is not None and not 0.0 <= temperature <= 2.0:
        errors.append(f"temperature must be 0.0-2.0, got {temperature}.")

    return errors


# ---------------------------------------------------------------------------
# Config builder
# ---------------------------------------------------------------------------

def build_config(
    model_key: str = "flash",
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
    *,
    use_vertex_ai: bool,
    output_mime_type: str = "image/jpeg",
    output_compression_quality: int = 85,
) -> types.GenerateContentConfig:
    """Build GenerateContentConfig with full ImageConfig options."""
    is_flash = model_key.lower() == "flash"

    image_cfg_kwargs = {
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
    }

    if use_vertex_ai:
        image_cfg_kwargs["output_mime_type"] = output_mime_type
        image_cfg_kwargs["output_compression_quality"] = output_compression_quality
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
# Result extraction
# ---------------------------------------------------------------------------

def extract_results(
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
                filepath = save_image(
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
# Safety filter retry helpers
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES = 3
DEFAULT_ON_BLOCK = "retry"  # "retry" = auto-retry with softened prompt, "stop" = fail immediately
VALID_ON_BLOCK = {"retry", "stop"}

SOFTENING_SUFFIXES = [
    " Ensure the image is appropriate, tasteful, and suitable for professional character design.",
    " Create a clean, safe, professional artistic rendering. Family-friendly character design reference.",
    " Professional character design illustration. Clean, appropriate, high-quality artistic reference.",
]

_SAFETY_KEYWORDS = frozenset([
    "safety", "blocked", "responsible ai", "policy", "harm",
    "content filtered", "violated", "not allowed",
])


def _is_safety_block_error(exc: Exception) -> bool:
    """Check if an exception indicates a safety filter block."""
    msg = str(exc).lower()
    return any(kw in msg for kw in _SAFETY_KEYWORDS)


def _is_safety_block_response(response) -> bool:
    """Check if a generate_content response was safety-filtered (no images)."""
    try:
        if hasattr(response, "prompt_feedback"):
            pf = response.prompt_feedback
            if pf and hasattr(pf, "block_reason") and pf.block_reason:
                return True
        if hasattr(response, "candidates") and response.candidates:
            c = response.candidates[0]
            if hasattr(c, "finish_reason"):
                fr = str(c.finish_reason).upper()
                if "SAFETY" in fr or "BLOCKED" in fr:
                    return True
            # Response came back but has no image content
            if hasattr(c, "content") and c.content and hasattr(c.content, "parts"):
                has_image = any(
                    hasattr(p, "inline_data") and p.inline_data
                    for p in c.content.parts
                )
                if not has_image:
                    return False  # No image but not necessarily safety block
            elif not hasattr(c, "content") or not c.content:
                return True  # Empty content likely safety block
        elif hasattr(response, "candidates") and not response.candidates:
            return True  # No candidates at all
    except (IndexError, AttributeError):
        pass
    return False


def _soften_prompt(contents, attempt: int):
    """Append a softening suffix to the text portion of contents for retry."""
    idx = min(attempt - 1, len(SOFTENING_SUFFIXES) - 1)
    suffix = SOFTENING_SUFFIXES[idx]

    if isinstance(contents, str):
        return contents + suffix

    if isinstance(contents, list):
        new_contents = list(contents)
        # Find the last string element and append suffix
        for i in range(len(new_contents) - 1, -1, -1):
            if isinstance(new_contents[i], str):
                new_contents[i] = new_contents[i] + suffix
                return new_contents
        # No string found -- append as new element
        new_contents.append(suffix.strip())
        return new_contents

    return contents


def generate_with_retry(
    client,
    model_id: str,
    contents,
    config: types.GenerateContentConfig,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_block: str = DEFAULT_ON_BLOCK,
):
    """Generate content with automatic retry on safety filter blocks.

    Returns the response object from generate_content.
    Raises RuntimeError if all retries exhausted or on_block="stop".
    """
    for attempt in range(max_retries + 1):
        current_contents = contents if attempt == 0 else _soften_prompt(contents, attempt)

        try:
            response = client.models.generate_content(
                model=model_id,
                contents=current_contents,
                config=config,
            )

            # Check response-level safety block
            if _is_safety_block_response(response):
                if on_block == "stop":
                    raise RuntimeError(
                        "Safety filter blocked generation. "
                        "on_block='stop' -- not retrying. "
                        "Try adjusting the character description or style."
                    )
                if attempt < max_retries:
                    time.sleep(1)  # Brief delay before retry
                    continue
                raise RuntimeError(
                    f"Safety filter blocked generation after {max_retries} retries. "
                    "Consider adjusting the character description or style."
                )

            return response

        except RuntimeError:
            raise  # Re-raise our own RuntimeError
        except Exception as e:
            if _is_safety_block_error(e):
                if on_block == "stop":
                    raise RuntimeError(
                        f"Safety filter blocked: {e}. "
                        "on_block='stop' -- not retrying."
                    ) from e
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                raise RuntimeError(
                    f"Safety filter blocked after {max_retries} retries: {e}. "
                    "Consider adjusting the character description or style."
                ) from e
            raise  # Non-safety error, raise immediately

    raise RuntimeError("Generation failed after all retry attempts.")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_character_prompt(
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
    *,
    shot_prompts: dict,
    default_background: str,
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
        parts.append(distinguishing_features)

    character_block = ". ".join(parts)

    # Format the shot-specific template
    return shot_prompts[shot_type].format(
        character=character_block,
        outfit=outfit_description,
        expression=expression or "neutral, calm",
        background=background_description or default_background,
        style=style,
        color_palette=f"Use a {color_palette} color scheme. " if color_palette else "",
    )


# ---------------------------------------------------------------------------
# Special expression generation (text-only Gemini call)
# ---------------------------------------------------------------------------

def generate_special_expressions(
    client,
    character_profile: dict,
    concept: str,
    count: int = 4,
    text_model_key: str = "flash",
) -> list[dict]:
    """Generate special expressions via text-only Gemini call.

    Returns list of expression dicts with category="special" added.
    Raises on failure — caller decides whether to skip specials.
    """
    model_id = TEXT_MODELS[text_model_key]
    prompt = (
        f"You are a character designer. Given a character profile and concept, "
        f"suggest {count} unique SD/chibi emoji expressions.\n\n"
        f"Character: {json.dumps(character_profile, ensure_ascii=False)}\n"
        f"Concept: {concept}\n\n"
        f"Return a JSON array of exactly {count} objects, each with:\n"
        f'- "key": snake_case identifier (e.g., "cat_hug")\n'
        f'- "label": English label\n'
        f'- "label_ko": Korean label\n'
        f'- "prompt": detailed visual description for image generation\n\n'
        f"Rules:\n"
        f"- Main character must be the visual center\n"
        f"- Sub-characters (pets, mascots) limited to 1 per expression\n"
        f"- Props limited to 2 per expression\n"
        f"- No background elements (green screen will be used)\n"
        f"Return ONLY the JSON array, no other text."
    )
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    expressions = json.loads(response.text)
    valid = []
    for expr in expressions:
        if all(k in expr for k in ("key", "label", "label_ko", "prompt")):
            expr["category"] = "special"
            valid.append(expr)
            if len(valid) >= count:
                break
    return valid


# ---------------------------------------------------------------------------
# Sheet Analysis via Vision (detect emoji positions)
# ---------------------------------------------------------------------------

SHEET_ANALYSIS_PROMPT = """Analyze this character emoji sheet image.
This is a grid sheet containing multiple individual chibi/SD character emojis arranged in rows and columns on a green chroma key background.

Your task: Find EVERY INDIVIDUAL character emoji and return its bounding box.

CRITICAL RULES:
- Each character is a SEPARATE emoji — do NOT merge adjacent characters into one box
- Each emoji contains exactly ONE full character (head to toe)
- If two characters are stacked vertically or side by side, they are TWO separate emojis
- Only include COMPLETE characters (skip any that are cut off at the image edge)
- Add 5% padding around each character to avoid clipping
- Bounding boxes must NOT overlap with each other

Coordinates: (x, y) from top-left corner of the image in pixels.

Return a JSON object (no other text):
{{
  "image_width": <int>,
  "image_height": <int>,
  "emoji_count": <int>,
  "emojis": [
    {{"x": <int>, "y": <int>, "width": <int>, "height": <int>}}
  ]
}}

Sort emojis in reading order: left-to-right, top-to-bottom (row by row)."""


def analyze_sheet_layout(
    client,
    model_id: str,
    image_path: str,
) -> dict:
    """Use Vision AI to detect individual emoji positions in a sheet image.

    Args:
        client: Google GenAI client.
        model_id: Model ID for vision (e.g. gemini-2.0-flash).
        image_path: Path to the sheet image file.

    Returns:
        Dict with "emoji_count" (int), "emojis" (list of {x, y, width, height}),
        "image_width", "image_height".
    """
    from PIL import Image as PILImage

    try:
        img = PILImage.open(image_path)
        img_w, img_h = img.size

        response = client.models.generate_content(
            model=model_id,
            contents=[SHEET_ANALYSIS_PROMPT, img],
            config={"response_mime_type": "application/json"},
        )

        result = json.loads(response.text)

        # Validate and clamp bounding boxes to image bounds
        validated = []
        for e in result.get("emojis", []):
            x = max(0, int(e.get("x", 0)))
            y = max(0, int(e.get("y", 0)))
            w = min(int(e.get("width", 100)), img_w - x)
            h = min(int(e.get("height", 100)), img_h - y)
            if w > 10 and h > 10:  # Skip tiny noise
                validated.append({"x": x, "y": y, "width": w, "height": h})

        return {
            "emoji_count": len(validated),
            "emojis": validated,
            "image_width": img_w,
            "image_height": img_h,
        }
    except Exception as e:
        logger.warning("analyze_sheet_layout failed: %s", e)
        return {"emoji_count": 0, "emojis": [], "image_width": 0, "image_height": 0}


# ---------------------------------------------------------------------------
# Emoji QC (Quality Check) via Vision
# ---------------------------------------------------------------------------

QC_PASS_THRESHOLD = 3  # Score >= 3 passes, < 3 triggers regen

QC_PROMPT = """You are a quality inspector for chibi/SD emoji stickers.
Evaluate this emoji image on these criteria:
1. Expression match: Does the character's expression match "{expression}"?
2. Anatomical correctness: Are hands, fingers, eyes, limbs drawn correctly?
3. Character integrity: No clipping, overlapping parts, or deformations?
4. Background cleanliness: Is the background transparent/clean (no chroma residue)?

Return a JSON object (no other text):
{{
  "score": <1-5 integer>,
  "pass": <true if score >= 3, false otherwise>,
  "issues": ["list of issues found, empty if none"]
}}

Scoring guide:
5 = Perfect, no issues
4 = Minor imperfections, fully usable
3 = Acceptable, small visual issues
2 = Noticeable problems (wrong expression, anatomical errors)
1 = Unusable (severely broken, wrong character)"""


def qc_emoji(
    client,
    model_id: str,
    image_path: str,
    expression_key: str,
) -> dict:
    """Run vision-based quality check on a single emoji image.

    Args:
        client: Google GenAI client.
        model_id: Model ID for vision (e.g. gemini-2.0-flash).
        image_path: Path to the emoji PNG file.
        expression_key: Expected expression (e.g. "happy", "angry").

    Returns:
        Dict with "score" (int 1-5), "pass" (bool), "issues" (list[str]).
    """
    from PIL import Image as PILImage

    try:
        img = PILImage.open(image_path)
        prompt = QC_PROMPT.format(expression=expression_key)

        response = client.models.generate_content(
            model=model_id,
            contents=[prompt, img],
            config={"response_mime_type": "application/json"},
        )

        result = json.loads(response.text)
        # Ensure required fields
        score = int(result.get("score", 1))
        return {
            "score": score,
            "pass": score >= QC_PASS_THRESHOLD,
            "issues": result.get("issues", []),
        }
    except Exception as e:
        logger.warning("qc_emoji failed for %s: %s — defaulting to pass", image_path, e)
        return {"score": 3, "pass": True, "issues": [f"QC error: {e}"]}
