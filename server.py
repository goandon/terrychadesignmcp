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

__version__ = "0.4.0"

import os
import sys
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

from presets import (
    resolve_preset, PHOTOREALISTIC_STYLES, ANIMATION_STYLES,
    PHOTO_PRESETS, ANIMATION_PRESETS,
)
from prompts import build_prompt
from profile_manager import ProfileManager
from design_db import DesignDB

_UNSET = object()  # Sentinel for distinguishing "not provided" from None

_profile_manager = None
def _get_profile_manager() -> ProfileManager:
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager


# --- Cross-platform NAS path mapping ---
# Single source of truth: profiles store macOS paths.
# On Windows, auto-convert /Volumes/NAS_Data/ <-> X:/ (SMB mount).
_NAS_PATH_MAP = {
    "macos": "/Volumes/NAS_Data/",
    "windows": "X:/",
    "unc": "//192.168.0.2/Data_Vol1/",
}


def _convert_nas_path(path_str: str) -> str:
    """Convert NAS path to current platform equivalent."""
    is_windows = sys.platform == "win32"
    if is_windows:
        # macOS -> Windows
        if path_str.startswith(_NAS_PATH_MAP["macos"]):
            return path_str.replace(_NAS_PATH_MAP["macos"], _NAS_PATH_MAP["windows"], 1)
    else:
        # Windows -> macOS
        if path_str.startswith(_NAS_PATH_MAP["windows"]):
            return path_str.replace(_NAS_PATH_MAP["windows"], _NAS_PATH_MAP["macos"], 1)
        # UNC -> macOS
        for unc_prefix in (_NAS_PATH_MAP["unc"], _NAS_PATH_MAP["unc"].replace("/", "\\")):
            if path_str.startswith(unc_prefix):
                return path_str.replace(unc_prefix, _NAS_PATH_MAP["macos"], 1)
    return path_str


def _convert_nas_paths(paths: list[str]) -> list[str]:
    """Convert a list of NAS paths to current platform."""
    return [_convert_nas_path(p) for p in paths]


def _resolve_product_input(product_ids=None, product_id=None, product_query=None):
    """Resolve product input by priority: product_ids > product_id > product_query."""
    if product_ids is not None:
        return ("product_ids", product_ids)
    elif product_id is not None:
        return ("product_id", product_id)
    elif product_query is not None:
        return ("product_query", product_query)
    else:
        raise ValueError(
            "At least one product selection method must be provided: "
            "product_ids, product_id, or product_query"
        )


_design_db = None
def _get_design_db() -> DesignDB:
    """Lazy-initialize the DesignDB singleton."""
    global _design_db
    if _design_db is None:
        _design_db = DesignDB()
    return _design_db

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

# Anti-overlay instruction — prevents model from rendering text, labels, or swatches
NO_OVERLAY_INSTRUCTION = (
    " IMPORTANT: Generate ONLY the character illustration. "
    "Do NOT add any text, labels, annotations, captions, arrows, "
    "color palette swatches, or detail inset boxes on the image. "
    "The output must be a clean image with no overlaid graphics or text of any kind."
)

# ---------------------------------------------------------------------------
# Safety Filter Retry Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES = 3
DEFAULT_ON_BLOCK = "retry"  # "retry" = auto-retry with softened prompt, "stop" = fail immediately
VALID_ON_BLOCK = {"retry", "stop"}

SOFTENING_SUFFIXES = [
    " Ensure the image is appropriate, tasteful, and suitable for professional character design.",
    " Create a clean, safe, professional artistic rendering. Family-friendly character design reference.",
    " Professional character design illustration. Clean, appropriate, high-quality artistic reference.",
]

# ---------------------------------------------------------------------------
# Generation Cost Estimation (USD per image, approximate)
# ---------------------------------------------------------------------------

GENERATION_PRICING_USD = {
    "flash": {
        "512px": 0.039,
        "1K": 0.039,
        "2K": 0.039,
        "4K": 0.039,
    },
    "pro": {
        "1K": 0.134,
        "2K": 0.134,
        "4K": 0.240,
    },
}

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

# Output mode presets — shortcuts for common shot configurations
OUTPUT_MODE_SHOTS = {
    "basic": ["face_front", "face_left", "full_body_front"],
    "face_angles": ["face_front", "face_left", "face_right"],
    "full_sheet": [
        "face_front",
        "face_left",
        "face_right",
        "full_body_front",
        "full_body_left",
        "full_body_back",
    ],
}
VALID_OUTPUT_MODES = set(OUTPUT_MODE_SHOTS.keys())

# ---------------------------------------------------------------------------
# Pose Sample Sheet Constants
# ---------------------------------------------------------------------------

POSE_CATEGORIES = {
    "daily_life": {
        "label": "Daily Life",
        "label_ko": "일상",
        "poses": {
            "sitting": {
                "label": "Sitting",
                "label_ko": "앉아있기",
                "prompt": "sitting on a chair with relaxed posture, hands resting on lap",
            },
            "walking": {
                "label": "Walking",
                "label_ko": "걷기",
                "prompt": "walking forward naturally, mid-stride, one foot ahead",
            },
            "waving": {
                "label": "Waving",
                "label_ko": "손 흔들기",
                "prompt": "waving hello with right hand raised, friendly gesture",
            },
            "reading": {
                "label": "Reading",
                "label_ko": "독서",
                "prompt": "holding a book with both hands, looking down at the pages",
            },
            "drinking": {
                "label": "Drinking",
                "label_ko": "음료 마시기",
                "prompt": "holding a cup or mug with both hands, bringing it toward lips",
            },
            "phone": {
                "label": "Using Phone",
                "label_ko": "스마트폰 사용",
                "prompt": "looking at a smartphone held in one hand, slightly tilted head",
            },
        },
    },
    "action": {
        "label": "Action",
        "label_ko": "액션",
        "poses": {
            "running": {
                "label": "Running",
                "label_ko": "달리기",
                "prompt": "running at full speed, dynamic pose, arms pumping",
            },
            "jumping": {
                "label": "Jumping",
                "label_ko": "점프",
                "prompt": "jumping in the air with both feet off the ground, arms spread",
            },
            "fighting_stance": {
                "label": "Fighting Stance",
                "label_ko": "전투 자세",
                "prompt": "combat ready stance, fists raised, weight on back foot",
            },
            "kicking": {
                "label": "Kicking",
                "label_ko": "킥",
                "prompt": "executing a high kick, one leg extended, dynamic action pose",
            },
            "reaching": {
                "label": "Reaching Up",
                "label_ko": "손 뻗기",
                "prompt": "reaching up with one arm extended overhead, stretching",
            },
            "crouching": {
                "label": "Crouching",
                "label_ko": "웅크리기",
                "prompt": "crouching low to the ground, one knee down, alert posture",
            },
        },
    },
    "emotion": {
        "label": "Emotion",
        "label_ko": "감정",
        "poses": {
            "laughing": {
                "label": "Laughing",
                "label_ko": "웃음",
                "prompt": "laughing joyfully, eyes closed, mouth open, head tilted back slightly",
            },
            "crying": {
                "label": "Crying",
                "label_ko": "울음",
                "prompt": "crying with tears streaming down cheeks, hands near face",
            },
            "thinking": {
                "label": "Thinking",
                "label_ko": "생각",
                "prompt": "thinking pose with one hand on chin, looking upward contemplatively",
            },
            "surprised": {
                "label": "Surprised",
                "label_ko": "놀람",
                "prompt": "surprised expression, hands raised near face, wide eyes, open mouth",
            },
            "angry": {
                "label": "Angry",
                "label_ko": "화남",
                "prompt": "angry pose with clenched fists, furrowed brows, tense shoulders",
            },
            "shy": {
                "label": "Shy",
                "label_ko": "수줍음",
                "prompt": "shy pose looking down, hands behind back, slightly turned away",
            },
        },
    },
    "social": {
        "label": "Social",
        "label_ko": "소셜",
        "poses": {
            "peace_sign": {
                "label": "Peace Sign",
                "label_ko": "브이",
                "prompt": "making a peace sign with right hand near face, cheerful expression",
            },
            "thumbs_up": {
                "label": "Thumbs Up",
                "label_ko": "엄지 척",
                "prompt": "giving a thumbs up with right hand, confident smile",
            },
            "arms_crossed": {
                "label": "Arms Crossed",
                "label_ko": "팔짱",
                "prompt": "standing with arms crossed over chest, confident cool pose",
            },
            "blowing_kiss": {
                "label": "Blowing Kiss",
                "label_ko": "키스",
                "prompt": "blowing a kiss with one hand near lips, playful wink",
            },
            "salute": {
                "label": "Salute",
                "label_ko": "경례",
                "prompt": "military-style salute with right hand to forehead, upright posture",
            },
            "fist_pump": {
                "label": "Fist Pump",
                "label_ko": "주먹 쥐기",
                "prompt": "raising a fist in the air triumphantly, excited expression",
            },
        },
    },
}

DEFAULT_POSE_CATEGORIES = ["daily_life", "emotion"]

# Pose sheet generation defaults
POSE_SHEET_IMAGE_SIZE = "512px"
POSE_SHEET_ASPECT_RATIO = "1:1"
POSE_SHEET_GRID_PADDING = 12
POSE_SHEET_GRID_BORDER = 20
POSE_SHEET_HEADER_HEIGHT = 48
POSE_SHEET_LABEL_HEIGHT = 28
POSE_SHEET_BG_COLOR = (245, 245, 245)

# Pose prompt template
POSE_PROMPT_TEMPLATE = (
    "Full body view of {character}. "
    "{pose_prompt}. "
    "Full body visible from head to feet. "
    "{color_palette}"
    "{background}. "
    "{style} style. "
    "Clean illustration, consistent proportions."
    + NO_OVERLAY_INSTRUCTION
)

# ---------------------------------------------------------------------------
# Chat Emoji / Sticker Constants
# ---------------------------------------------------------------------------

EMOJI_PLATFORMS = {
    "telegram": {
        "label": "Telegram",
        "label_ko": "텔레그램",
        "size": (512, 512),
        "format": "png",
        "max_size_kb": 512,
        "notes": "Sticker format, transparent background",
    },
    "discord": {
        "label": "Discord",
        "label_ko": "디스코드",
        "size": (128, 128),
        "format": "png",
        "max_size_kb": 256,
        "notes": "Server emoji, transparent background",
    },
    "line": {
        "label": "LINE",
        "label_ko": "라인",
        "size": (370, 320),
        "format": "png",
        "max_size_kb": 1024,
        "notes": "Static sticker, transparent background",
    },
    "kakaotalk": {
        "label": "KakaoTalk",
        "label_ko": "카카오톡",
        "size": (360, 360),
        "format": "png",
        "max_size_kb": 1024,
        "notes": "Emoticon sticker",
    },
    "slack": {
        "label": "Slack",
        "label_ko": "슬랙",
        "size": (128, 128),
        "format": "png",
        "max_size_kb": 128,
        "notes": "Custom emoji, transparent background",
    },
    "whatsapp": {
        "label": "WhatsApp",
        "label_ko": "왓츠앱",
        "size": (512, 512),
        "format": "webp",
        "max_size_kb": 100,
        "notes": "WebP sticker pack format",
    },
    "universal": {
        "label": "Universal (512x512 PNG)",
        "label_ko": "범용",
        "size": (512, 512),
        "format": "png",
        "max_size_kb": None,
        "notes": "High-quality source, resize for any platform",
    },
}
DEFAULT_EMOJI_PLATFORM = "universal"

EMOJI_EXPRESSION_SETS = {
    "basic_16": {
        "label": "Basic 16",
        "label_ko": "기본 16종",
        "expressions": {
            "happy": {
                "label": "Happy",
                "label_ko": "기쁨",
                "prompt": "bright happy smiling face, eyes sparkling with joy, wide cheerful grin",
            },
            "sad": {
                "label": "Sad",
                "label_ko": "슬픔",
                "prompt": "sad face with downturned mouth, teary eyes, drooping expression",
            },
            "angry": {
                "label": "Angry",
                "label_ko": "화남",
                "prompt": "angry scowling face, furrowed eyebrows, gritted teeth, red-faced",
            },
            "surprised": {
                "label": "Surprised",
                "label_ko": "놀람",
                "prompt": "shocked surprised face, wide open eyes and mouth, hands on cheeks",
            },
            "love": {
                "label": "Love",
                "label_ko": "사랑",
                "prompt": "love-struck face with heart-shaped eyes, blushing cheeks, dreamy smile",
            },
            "thumbs_up": {
                "label": "Thumbs Up",
                "label_ko": "엄지 척",
                "prompt": "giving enthusiastic thumbs up, winking, confident grin",
            },
            "thinking": {
                "label": "Thinking",
                "label_ko": "생각 중",
                "prompt": "thinking pose, hand on chin, one eyebrow raised, puzzled look",
            },
            "sleeping": {
                "label": "Sleeping",
                "label_ko": "잠자기",
                "prompt": "sleeping peacefully, eyes closed, ZZZ floating, relaxed face",
            },
            "crying": {
                "label": "Crying",
                "label_ko": "울음",
                "prompt": "crying with streams of tears, sobbing expression, watery eyes",
            },
            "laughing": {
                "label": "Laughing",
                "label_ko": "빵 터짐",
                "prompt": "laughing hysterically, tears of joy, mouth wide open, holding stomach",
            },
            "wink": {
                "label": "Wink",
                "label_ko": "윙크",
                "prompt": "playful wink with one eye closed, tongue sticking out slightly, cute",
            },
            "embarrassed": {
                "label": "Embarrassed",
                "label_ko": "당황",
                "prompt": "embarrassed blushing face, sweat drop, awkward nervous smile",
            },
            "cool": {
                "label": "Cool",
                "label_ko": "쿨",
                "prompt": "cool confident pose with sunglasses, smirking, finger guns",
            },
            "confused": {
                "label": "Confused",
                "label_ko": "혼란",
                "prompt": "confused face with question marks, tilted head, squinting eyes",
            },
            "excited": {
                "label": "Excited",
                "label_ko": "신남",
                "prompt": "super excited with sparkle eyes, fists clenched in excitement, bouncing",
            },
            "tired": {
                "label": "Tired",
                "label_ko": "피곤",
                "prompt": "exhausted droopy face, half-closed eyes, yawning, slouched posture",
            },
        },
    },
    "reaction_8": {
        "label": "Reaction 8",
        "label_ko": "리액션 8종",
        "expressions": {
            "ok": {
                "label": "OK",
                "label_ko": "오케이",
                "prompt": "making OK hand gesture with thumb and index finger circle, approving nod",
            },
            "no": {
                "label": "No",
                "label_ko": "노",
                "prompt": "shaking head no with X arms crossed, disapproving frown",
            },
            "please": {
                "label": "Please",
                "label_ko": "부탁",
                "prompt": "begging with hands clasped together, puppy eyes, pleading expression",
            },
            "cheers": {
                "label": "Cheers",
                "label_ko": "건배",
                "prompt": "raising a cup or glass in a toast, celebratory smile",
            },
            "sorry": {
                "label": "Sorry",
                "label_ko": "미안",
                "prompt": "apologetic bow with hands pressed together, guilty expression",
            },
            "thank_you": {
                "label": "Thank You",
                "label_ko": "감사",
                "prompt": "grateful bow with hands on chest, warm appreciative smile",
            },
            "fighting": {
                "label": "Fighting!",
                "label_ko": "화이팅",
                "prompt": "fist pump in the air, determined fierce expression, motivational pose",
            },
            "heart": {
                "label": "Heart",
                "label_ko": "하트",
                "prompt": "making a heart shape with both hands above head, cute loving expression",
            },
        },
    },
}
DEFAULT_EMOJI_SET = "basic_16"

# SD/chibi style conversion prompt prefix
CHIBI_STYLE_PREFIX = (
    "Super-deformed (SD) chibi character emoji sticker. "
    "2-3 head-to-body ratio, oversized head, large expressive eyes, "
    "small body, simplified hands and feet, cute exaggerated proportions. "
    "Single character centered on frame. "
    "Clean bold outlines, flat vibrant colors, sticker-ready design."
    + NO_OVERLAY_INSTRUCTION
    + " "
)

# Consistency prefix adapted for chibi transformation
EMOJI_CONSISTENCY_PREFIX = (
    "Using the provided reference image(s), create an SD/chibi version of "
    "the SAME character maintaining the same hair color, hair style, eye color, "
    "skin tone, and key outfit elements (simplified for chibi proportions). "
)

# Chroma key background instruction for transparent emoji output
EMOJI_CHROMA_BG = "on a solid bright green (#00FF00) chroma key background"
EMOJI_CHROMA_COLOR = (0, 255, 0)
EMOJI_CHROMA_TOLERANCE = 60

# Emoji grid layout constants
EMOJI_GRID_PADDING = 8
EMOJI_GRID_BORDER = 16
EMOJI_GRID_HEADER_HEIGHT = 40
EMOJI_GRID_LABEL_HEIGHT = 24
EMOJI_GRID_BG_COLOR = (255, 255, 255)

# ---------------------------------------------------------------------------
# Prompt Dictionary Data
# ---------------------------------------------------------------------------

PROMPT_DICTIONARY = {
    "body_types": {
        "label": "Body Types",
        "label_ko": "체형",
        "description": "Standard body type and build descriptors",
        "entries": {
            "Slim": "slim, slender, lean, willowy, lithe, svelte",
            "Athletic": "athletic, toned, fit, muscular-lean, defined, sporty",
            "Curvy": "curvy, voluptuous, hourglass, full-figured",
            "Muscular": "muscular, buff, heavily-built, broad-shouldered, powerful",
            "Petite": "petite, small-framed, delicate, compact, dainty",
            "Average": "average build, medium build, proportional, standard",
            "Tall": "tall, statuesque, long-limbed, towering",
        },
    },
    "facial_features": {
        "label": "Facial Features",
        "label_ko": "얼굴 특징",
        "description": "Face shapes, eye types, nose, lips, and jawline descriptors",
        "entries": {
            "Face - Oval": "oval face shape, balanced proportions, gently curved jawline",
            "Face - Round": "round face, soft cheeks, curved chin, youthful fullness",
            "Face - Square": "square jawline, strong angular jaw, broad forehead",
            "Face - Heart": "heart-shaped face, wide forehead, pointed chin, high cheekbones",
            "Face - Diamond": "diamond-shaped face, wide cheekbones, narrow forehead and chin",
            "Eyes - Almond": "almond-shaped eyes, gently tapered corners",
            "Eyes - Round": "large round eyes, wide and open, doll-like",
            "Eyes - Monolid": "monolid eyes, smooth eyelid, East Asian feature",
            "Eyes - Hooded": "hooded eyes, partially covered by crease",
            "Eyes - Upturned": "upturned cat-eye shape, outer corners lifted",
            "Eye Color - Brown": "warm brown, dark brown, chocolate, amber, hazel",
            "Eye Color - Blue": "sky blue, deep blue, ice blue, cerulean, navy",
            "Eye Color - Green": "emerald green, sage green, olive, jade, forest green",
            "Eye Color - Gray": "steel gray, silver, light gray, storm gray",
            "Eye Color - Fantasy": "violet, golden, heterochromatic, red",
            "Nose - Straight": "straight nose bridge, well-defined",
            "Nose - Button": "small button nose, cute, slightly upturned tip",
            "Nose - Aquiline": "aquiline nose, prominent bridge, slight curve",
            "Lips - Full": "full plump lips, well-defined cupid's bow",
            "Lips - Thin": "thin delicate lips, understated",
            "Lips - Heart": "heart-shaped lips, prominent upper lip",
            "Jawline - Angular": "angular jawline, strong, defined",
            "Jawline - Rounded": "rounded jawline, soft, gentle",
        },
    },
    "hair_styles": {
        "label": "Hair Styles",
        "label_ko": "헤어 스타일",
        "description": "Hair length, texture, specific styles, and colors",
        "entries": {
            "Length - Buzz/Shaved": "buzz cut, shaved head, closely cropped",
            "Length - Short": "short hair above ears, cropped, pixie-length",
            "Length - Medium": "medium-length hair to shoulders, collar-length",
            "Length - Long": "long hair past shoulders, mid-back length",
            "Length - Very Long": "very long hair reaching waist, floor-length",
            "Texture - Straight": "pin-straight smooth hair, sleek",
            "Texture - Wavy": "soft gentle waves, beachy waves, loose waves",
            "Texture - Curly": "defined curls, springy curls, ringlets",
            "Texture - Coily": "tight coils, natural afro texture, kinky curls",
            "Style - Pixie": "pixie cut, short textured layers, side-swept",
            "Style - Bob": "chin-length bob, blunt bob, asymmetric bob, lob",
            "Style - Ponytail": "high ponytail, low ponytail, side ponytail",
            "Style - Twin tails": "twin tails, pigtails, twin braids",
            "Style - Braids": "single braid, French braid, Dutch braid, fishtail braid",
            "Style - Bun": "messy bun, tight bun, low chignon, space buns, top knot",
            "Style - Updo": "elegant updo, pinned-up curls, French twist",
            "Bangs": "blunt bangs, side-swept bangs, curtain bangs, wispy bangs, no bangs",
            "Color - Natural": "jet black, dark brown, chestnut, auburn, honey blonde, platinum blonde, ginger, silver/white",
            "Color - Fantasy": "pastel pink, lavender, mint green, sky blue, coral, electric blue",
            "Color - Multi": "ombre gradient, balayage, highlights, two-tone, split dye",
        },
    },
    "clothing": {
        "label": "Clothing & Fashion",
        "label_ko": "의상 및 패션",
        "description": "Outfit categories, fabric types, and style genres",
        "entries": {
            "Casual": "t-shirt and jeans, hoodie, sneakers, casual dress",
            "Formal": "suit and tie, evening gown, cocktail dress, blazer",
            "School": "sailor uniform, blazer uniform, gym uniform, school cardigan",
            "Fantasy": "armor, robes, cloak, medieval dress, enchanted outfit",
            "Sci-Fi": "spacesuit, cyberpunk outfit, neon-accented bodysuit, mech pilot suit",
            "Athletic": "sports jersey, track suit, yoga outfit, tennis skirt",
            "Traditional": "hanbok, kimono, qipao/cheongsam, sari, dirndl",
            "Streetwear": "oversized hoodie, cargo pants, bucket hat, chunky sneakers",
            "Military": "military uniform, camouflage, tactical vest, combat boots",
            "Fabric - Cotton": "soft cotton, breathable, matte finish",
            "Fabric - Silk": "smooth silk, glossy sheen, flowing drape",
            "Fabric - Leather": "polished leather, matte leather, distressed leather",
            "Fabric - Denim": "dark denim, light wash, acid wash, raw denim",
            "Fabric - Wool": "knitted wool, tweed, cashmere, cable-knit",
            "Fabric - Lace": "delicate lace, sheer lace overlay, crochet",
            "Fabric - Velvet": "rich velvet, crushed velvet, deep pile",
        },
    },
    "expressions": {
        "label": "Expressions & Emotions",
        "label_ko": "표정 및 감정",
        "description": "Basic expressions, intensity modifiers, and compound expressions",
        "entries": {
            "Neutral": "neutral calm expression, relaxed face, resting expression",
            "Happy": "bright smile, cheerful expression, eyes crinkling with joy",
            "Sad": "downcast eyes, slight frown, melancholy expression",
            "Angry": "furrowed brows, clenched jaw, intense glare",
            "Surprised": "wide eyes, raised eyebrows, open mouth",
            "Disgusted": "wrinkled nose, turned-down lips, squinting",
            "Fearful": "wide frightened eyes, pale face, trembling lip",
            "Bittersweet": "smiling with teary eyes, happy-sad expression",
            "Mischievous": "sly grin, raised eyebrow, playful smirk",
            "Determined": "firm jaw, focused intense eyes, confident set mouth",
            "Serene": "peaceful closed eyes, gentle Mona Lisa smile",
            "Smug": "self-satisfied smirk, half-lidded eyes, chin slightly raised",
            "Intensity - Subtle": "slight, faint, barely visible, hint of, subtle",
            "Intensity - Moderate": "clear, visible, noticeable, defined",
            "Intensity - Intense": "extreme, exaggerated, dramatic, overwhelming",
        },
    },
    "poses": {
        "label": "Poses",
        "label_ko": "포즈",
        "description": "Base positions and arm/hand modifiers for character posing",
        "entries": {
            "Standing": "standing upright, neutral relaxed stance",
            "Sitting": "seated on chair/floor, legs position varies",
            "Kneeling": "kneeling on one or both knees",
            "Lying": "lying down/reclining, prone or supine",
            "Crouching": "crouched low, knees bent",
            "Leaning": "leaning against wall/surface",
            "Arms at sides": "arms relaxed at sides",
            "Arms crossed": "arms crossed over chest",
            "Hands on hips": "hands placed on hips, confident stance",
            "Hands behind back": "hands clasped behind back",
            "One hand raised": "one hand raised in greeting/gesture",
            "Holding object": "holding [object] in hand(s)",
            "Pointing": "pointing forward/upward with index finger",
        },
    },
    "art_styles": {
        "label": "Art Styles",
        "label_ko": "아트 스타일",
        "description": "Supported art styles with descriptive keywords",
        "entries": {
            "Anime": "anime style, cel-shaded, vibrant colors, large expressive eyes",
            "Realistic": "photorealistic, lifelike, natural proportions, detailed skin texture",
            "Semi-realistic": "semi-realistic, stylized realism, slightly idealized features",
            "3D Render": "3D rendered, CGI quality, Pixar-style, smooth surfaces",
            "Watercolor": "watercolor painting, soft edges, bleeding colors, wet media",
            "Oil Painting": "oil painting style, rich textures, visible brushstrokes, classical",
            "Digital Art": "digital art, clean rendering, vibrant palette, modern illustration",
            "Comic Book": "comic book style, bold ink lines, halftone dots, dynamic",
            "Manga": "manga style, screen tones, dramatic linework, Japanese comic",
            "Pixel Art": "pixel art, retro 8-bit/16-bit, blocky, limited palette",
            "Concept Art": "concept art, professional design sheet, industry standard",
            "Cel-Shaded": "cel-shaded, flat color blocks, clear shadow edges, toon shader",
            "Chibi": "chibi style, super-deformed, oversized head, tiny body, cute",
            "Fantasy Illustration": "fantasy illustration, epic, detailed, painterly, DnD style",
            "Sci-Fi Concept": "sci-fi concept art, futuristic, sleek, technological details",
            "Line Art": "clean line art, ink drawing, no fill, varying line weight",
            "Pastel": "pastel colors, soft muted palette, gentle dreamy atmosphere",
            "Photorealistic": "photorealistic render, hyper-detailed, studio photography quality",
        },
    },
    "lighting": {
        "label": "Lighting",
        "label_ko": "조명",
        "description": "Lighting types, time-of-day, and mood descriptors",
        "entries": {
            "Studio": "clean studio lighting, even illumination, minimal shadows",
            "Dramatic": "dramatic chiaroscuro, strong contrast, deep shadows",
            "Rim": "rim lighting, bright edge glow, silhouette emphasis",
            "Soft": "soft diffused lighting, gentle shadows, flattering",
            "Hard": "hard directional light, sharp defined shadows",
            "Backlit": "backlit, halo effect, glowing edges, silhouette",
            "Volumetric": "volumetric light rays, god rays, atmospheric scattering",
            "Dawn": "warm golden dawn light, pink-orange sky tones",
            "Midday": "bright overhead sunlight, minimal shadows",
            "Golden Hour": "warm golden hour glow, long soft shadows, amber tones",
            "Twilight": "cool blue-purple twilight, fading sky gradient",
            "Night": "moonlit, cool blue tones, dramatic contrast",
        },
    },
    "camera_angles": {
        "label": "Camera Angles",
        "label_ko": "카메라 앵글",
        "description": "Standard camera angles and framing types",
        "entries": {
            "Front": "front view, facing camera directly",
            "Three-quarter": "three-quarter angle, 45-degree turn",
            "Side profile": "side view, perfect profile",
            "Back": "rear view, facing away",
            "Low angle": "low angle looking up, heroic/powerful feel",
            "High angle": "high angle looking down, overview perspective",
            "Bird's eye": "top-down view, directly overhead",
            "Dutch angle": "tilted/canted frame, dynamic tension",
            "Close-up": "face/detail close-up, tight framing",
            "Medium shot": "waist-up framing, conversational distance",
            "Full body": "full body visible, head to feet",
        },
    },
    "color_palettes": {
        "label": "Color Palettes",
        "label_ko": "컬러 팔레트",
        "description": "Color families and mood-based palette descriptors",
        "entries": {
            "Warm Reds": "crimson, scarlet, ruby, burgundy, wine, cherry, rose, coral",
            "Cool Blues": "navy, cobalt, cerulean, sapphire, teal, ice blue, periwinkle, slate",
            "Greens": "emerald, sage, olive, forest, mint, jade, chartreuse, hunter",
            "Purples": "violet, plum, lavender, mauve, amethyst, indigo, lilac, magenta",
            "Earth Tones": "sienna, umber, ochre, terracotta, tan, khaki, rust, sepia",
            "Neutrals": "ivory, cream, beige, taupe, charcoal, slate, ash",
            "Metallics": "gold, silver, bronze, copper, rose gold, platinum, chrome",
            "Mood - Energetic": "bright reds, oranges, yellows; high saturation, warm dominant",
            "Mood - Calm": "soft blues, greens, lavender; low saturation, cool dominant",
            "Mood - Romantic": "pinks, roses, burgundy, gold accents; warm muted tones",
            "Mood - Dark/Gothic": "deep purples, blacks, dark reds; low value, high contrast",
            "Mood - Pastel": "pastel pink, baby blue, mint, lilac; low saturation, high value",
            "Mood - Natural": "earth tones, forest greens, sky blue; organic unsaturated palette",
        },
    },
    "accessories": {
        "label": "Accessories",
        "label_ko": "액세서리",
        "description": "Jewelry, headwear, props, and material descriptors",
        "entries": {
            "Earrings": "stud earrings, hoop earrings, drop earrings, ear cuffs",
            "Necklace": "choker, pendant necklace, pearl necklace, chain necklace",
            "Rings": "simple band, gemstone ring, multiple rings, statement ring",
            "Bracelet": "bangle, charm bracelet, cuff bracelet, beaded bracelet",
            "Hats": "baseball cap, beret, beanie, sun hat, fedora, witch hat",
            "Hair accessories": "hair ribbon, headband, hair clips, flower crown, scrunchie",
            "Headwear": "crown, tiara, veil, helmet, hood",
            "Melee weapons": "sword, katana, staff, spear, daggers, hammer",
            "Ranged weapons": "bow and arrows, crossbow, gun, throwing stars",
            "Magic props": "wand, spell book, crystal orb, magical staff",
            "Everyday props": "umbrella, briefcase, backpack, guitar, camera",
            "Material - Gold": "polished gold, antique gold, rose gold",
            "Material - Silver": "gleaming silver, tarnished silver, sterling silver",
            "Material - Crystal": "sparkling crystal, translucent, prismatic",
        },
    },
    "age_descriptors": {
        "label": "Age Descriptors",
        "label_ko": "나이 묘사",
        "description": "Age ranges with visual indicators for character rendering",
        "entries": {
            "Child (6-12)": "round face, small stature, large eyes relative to face, soft features",
            "Teen (13-17)": "youthful features, developing proportions, energetic posture",
            "Young Adult (18-25)": "mature features, defined jawline, peak proportions",
            "Adult (26-40)": "fully mature features, confident bearing, subtle expression lines",
            "Middle-aged (41-55)": "some fine lines, distinguished features, slight graying optional",
            "Elderly (60+)": "wrinkles, silver/white hair, weathered features, kind eyes",
        },
    },
    "backgrounds": {
        "label": "Backgrounds",
        "label_ko": "배경",
        "description": "Studio, outdoor, fantasy, and interior background descriptions",
        "entries": {
            "Solid neutral": "solid neutral gray background, clean studio backdrop",
            "White": "pure white background, clean, isolated subject",
            "Gradient": "gradient background from [color] to [color]",
            "Park": "lush green park, trees, sunlight filtering through leaves",
            "Beach": "sandy beach, ocean waves, clear sky, sunset",
            "Mountains": "mountain landscape, dramatic peaks, clouds",
            "Forest": "deep forest, tall trees, dappled light, foliage",
            "City street": "urban street scene, buildings, pavement, city lights",
            "Castle": "grand castle interior, stone walls, tapestries, candlelight",
            "Enchanted forest": "magical glowing forest, floating particles, ethereal",
            "Sky/clouds": "floating among clouds, vast sky, divine atmosphere",
            "Ruins": "ancient ruins, crumbling stone, overgrown ivy, mysterious",
            "Cafe": "cozy cafe interior, warm lighting, coffee shop ambiance",
            "Library": "book-lined shelves, reading room, warm wooden tones",
            "Bedroom": "modern bedroom, soft lighting, personal space",
            "Classroom": "school classroom, desks, blackboard, windows",
        },
    },
}

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
# Safety filter retry helpers
# ---------------------------------------------------------------------------

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


def _generate_with_retry(
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
        parts.append(distinguishing_features)

    character_block = ". ".join(parts)

    # Format the shot-specific template
    return SHOT_PROMPTS[shot_type].format(
        character=character_block,
        outfit=outfit_description,
        expression=expression or "neutral, calm",
        background=background_description or DEFAULT_BACKGROUND,
        style=style,
        color_palette=f"Use a {color_palette} color scheme. " if color_palette else "",
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
    font_header, font_label = _load_fonts(32, 15)

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
# Composite Row Builder (basic / face_angles modes)
# ---------------------------------------------------------------------------

def _create_composite_row(
    shot_images: dict[str, str],
    shot_order: list[str],
    character_name: str,
    mode: str,
    output_dir: Path,
) -> Optional[str]:
    """Create a horizontal row composite from a small set of shot images.

    Used for output_mode='basic' and output_mode='face_angles'.
    Layout: images arranged side-by-side with 8px gap, scaled to uniform height.
    Header "{character_name} — {mode}" above, Korean labels below each image.
    """
    # Load available images in shot_order
    loaded = []
    for shot_type in shot_order:
        path = shot_images.get(shot_type)
        if path and Path(path).exists():
            loaded.append((shot_type, Image.open(path)))

    if not loaded:
        return None

    gap = 8
    border = 20
    header_h = 44
    label_h = 28

    # Determine target height: tallest image height
    target_h = max(img.height for _, img in loaded)

    # Scale all images to target_h (proportional)
    scaled = []
    for shot_type, img in loaded:
        scale = target_h / img.height
        new_w = int(img.width * scale)
        scaled.append((shot_type, img.resize((new_w, target_h), Image.LANCZOS)))

    # Canvas dimensions
    total_w = sum(img.width for _, img in scaled) + gap * max(len(scaled) - 1, 0)
    canvas_w = border * 2 + total_w
    canvas_h = border * 2 + header_h + target_h + label_h

    canvas = Image.new("RGB", (canvas_w, canvas_h), COMPOSITE_BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Load fonts
    font_header, font_label = _load_fonts(28, 14)

    # Draw header
    header_text = f"{character_name} \u2014 {mode}"
    draw.text(
        (border, border + (header_h - 32) // 2),
        header_text,
        fill=COMPOSITE_TEXT_COLOR,
        font=font_header,
    )

    y_top = border + header_h

    # Draw images and labels
    x = border
    for shot_type, img in scaled:
        canvas.paste(img, (x, y_top))
        label = SHOT_DEFINITIONS[shot_type]["label_ko"]
        bbox = draw.textbbox((0, 0), label, font=font_label)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (x + (img.width - text_w) // 2, y_top + target_h + 6),
            label,
            fill=COMPOSITE_LABEL_COLOR,
            font=font_label,
        )
        x += img.width + gap

    # Save composite
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    composite_path = output_dir / f"composite_row_{mode}_{timestamp}.jpg"
    canvas.save(composite_path, "JPEG", quality=95)

    return str(composite_path)


# ---------------------------------------------------------------------------
# Pose Grid Sheet Builder
# ---------------------------------------------------------------------------

def _load_fonts(header_size: int = 24, label_size: int = 13):
    """Load cross-platform fonts for EN header and KO labels."""
    _en_candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    _ko_candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/gulim.ttc",
    ]
    font_header = None
    for fp in _en_candidates:
        try:
            font_header = ImageFont.truetype(fp, header_size)
            break
        except OSError:
            continue
    font_label = None
    for fp in _ko_candidates:
        try:
            font_label = ImageFont.truetype(fp, label_size)
            break
        except OSError:
            continue
    if font_header is None:
        font_header = ImageFont.load_default()
    if font_label is None:
        font_label = ImageFont.load_default()
    return font_header, font_label


def _create_pose_grid_sheet(
    pose_images: dict,
    pose_labels: dict,
    character_name: str,
    style: str,
    output_dir: Path,
    columns: int = 4,
) -> Optional[str]:
    """Create a composite grid sheet from pose images.

    Args:
        pose_images: {pose_key: file_path}
        pose_labels: {pose_key: label_ko}
        character_name: For header title.
        style: Art style for header.
        output_dir: Output directory.
        columns: Grid columns (default 4).

    Returns:
        Path to composite sheet or None.
    """
    if not pose_images:
        return None

    # Determine ordered keys (preserve insertion order)
    keys = [k for k in pose_images if Path(pose_images[k]).exists()]
    if not keys:
        return None

    # Load and resize all images to uniform size
    cell_size = None
    loaded = {}
    for k in keys:
        img = Image.open(pose_images[k])
        if cell_size is None:
            cell_size = min(img.width, img.height)
        loaded[k] = img

    # Resize all to square cells
    for k in loaded:
        img = loaded[k]
        scale = cell_size / max(img.width, img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        loaded[k] = img.resize((new_w, new_h), Image.LANCZOS)

    pad = POSE_SHEET_GRID_PADDING
    border = POSE_SHEET_GRID_BORDER
    header_h = POSE_SHEET_HEADER_HEIGHT
    label_h = POSE_SHEET_LABEL_HEIGHT

    cols = min(columns, len(keys))
    rows = (len(keys) + cols - 1) // cols

    canvas_w = border * 2 + cols * cell_size + (cols - 1) * pad
    canvas_h = border * 2 + header_h + rows * (cell_size + label_h + pad) - pad

    canvas = Image.new("RGB", (canvas_w, canvas_h), POSE_SHEET_BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    font_header, font_label = _load_fonts(24, 13)

    # Header
    header_text = f"{character_name}  |  Pose Sheet  |  {style}"
    draw.text(
        (border, border + (header_h - 28) // 2),
        header_text,
        fill=COMPOSITE_TEXT_COLOR,
        font=font_header,
    )

    # Place images in grid
    for idx, key in enumerate(keys):
        row = idx // cols
        col = idx % cols
        x = border + col * (cell_size + pad)
        y = border + header_h + row * (cell_size + label_h + pad)

        img = loaded[key]
        # Center image in cell
        x_offset = (cell_size - img.width) // 2
        y_offset = (cell_size - img.height) // 2
        canvas.paste(img, (x + x_offset, y + y_offset))

        # Label below
        label = pose_labels.get(key, key)
        bbox = draw.textbbox((0, 0), label, font=font_label)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (x + (cell_size - text_w) // 2, y + cell_size + 4),
            label,
            fill=COMPOSITE_LABEL_COLOR,
            font=font_label,
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sheet_path = output_dir / f"pose_sheet_{timestamp}.jpg"
    canvas.save(sheet_path, "JPEG", quality=95)
    return str(sheet_path)


# ---------------------------------------------------------------------------
# Emoji Helpers
# ---------------------------------------------------------------------------

def _remove_chroma_key_background(
    image_path: str,
    chroma_color: tuple = EMOJI_CHROMA_COLOR,
    tolerance: int = EMOJI_CHROMA_TOLERANCE,
) -> Image.Image:
    """Remove chroma key background and return RGBA image with transparency.

    Converts green-screen pixels to transparent based on color distance.
    """
    img = Image.open(image_path).convert("RGBA")
    data = img.getdata()
    new_data = []
    cr, cg, cb = chroma_color
    for r, g, b, a in data:
        dist = ((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2) ** 0.5
        if dist < tolerance:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    return img


def _resize_for_platform(
    image: Image.Image,
    platform_key: str,
    output_dir: Path,
    prefix: str,
) -> str:
    """Resize image to platform-specific dimensions and format.

    Handles dimension resize, format conversion, and file size optimization.
    Returns path to the platform-optimized file.
    """
    spec = EMOJI_PLATFORMS[platform_key]
    target_w, target_h = spec["size"]
    fmt = spec["format"]
    max_kb = spec["max_size_kb"]

    # Resize with LANCZOS
    resized = image.resize((target_w, target_h), Image.LANCZOS)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]

    if fmt == "webp":
        filename = f"{prefix}_{timestamp}_{short_id}.webp"
        filepath = output_dir / filename

        # Quality reduction loop for file size limit
        quality = 90
        while quality >= 20:
            resized.save(filepath, "WEBP", quality=quality)
            if max_kb is None or filepath.stat().st_size / 1024 <= max_kb:
                break
            quality -= 10
    else:
        # PNG (lossless, supports transparency)
        filename = f"{prefix}_{timestamp}_{short_id}.png"
        filepath = output_dir / filename
        resized.save(filepath, "PNG")

        # If file too large, try reducing by palette quantization
        if max_kb is not None and filepath.stat().st_size / 1024 > max_kb:
            quantized = resized.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
            quantized = quantized.convert("RGBA")
            quantized.save(filepath, "PNG")

    return str(filepath)


def _create_emoji_grid_sheet(
    emoji_images: dict,
    emoji_labels: dict,
    character_name: str,
    platform: str,
    output_dir: Path,
    columns: int = 4,
) -> Optional[str]:
    """Create a composite preview grid of all generated emoji.

    Args:
        emoji_images: {expression_key: file_path}
        emoji_labels: {expression_key: label_ko}
        character_name: For header title.
        platform: Platform name for header.
        output_dir: Output directory.
        columns: Grid columns (default 4).

    Returns:
        Path to composite preview sheet or None.
    """
    if not emoji_images:
        return None

    keys = [k for k in emoji_images if Path(emoji_images[k]).exists()]
    if not keys:
        return None

    # Load images (use originals, not platform-resized, for readable preview)
    loaded = {}
    preview_size = 128  # Preview cell size for grid
    for k in keys:
        img = Image.open(emoji_images[k]).convert("RGBA")
        img = img.resize((preview_size, preview_size), Image.LANCZOS)
        loaded[k] = img

    pad = EMOJI_GRID_PADDING
    border = EMOJI_GRID_BORDER
    header_h = EMOJI_GRID_HEADER_HEIGHT
    label_h = EMOJI_GRID_LABEL_HEIGHT

    cols = min(columns, len(keys))
    rows = (len(keys) + cols - 1) // cols

    canvas_w = border * 2 + cols * preview_size + (cols - 1) * pad
    canvas_h = border * 2 + header_h + rows * (preview_size + label_h + pad) - pad

    canvas = Image.new("RGB", (canvas_w, canvas_h), EMOJI_GRID_BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    font_header, font_label = _load_fonts(20, 11)

    # Header
    platform_label = EMOJI_PLATFORMS.get(platform, {}).get("label", platform)
    header_text = f"{character_name}  |  Emoji  |  {platform_label}"
    draw.text(
        (border, border + (header_h - 24) // 2),
        header_text,
        fill=COMPOSITE_TEXT_COLOR,
        font=font_header,
    )

    # Place emoji in grid
    for idx, key in enumerate(keys):
        row = idx // cols
        col = idx % cols
        x = border + col * (preview_size + pad)
        y = border + header_h + row * (preview_size + label_h + pad)

        img = loaded[key]
        # Paste with transparency handling
        bg = Image.new("RGB", (preview_size, preview_size), EMOJI_GRID_BG_COLOR)
        bg.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
        canvas.paste(bg, (x, y))

        # Label
        label = emoji_labels.get(key, key)
        bbox = draw.textbbox((0, 0), label, font=font_label)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (x + (preview_size - text_w) // 2, y + preview_size + 3),
            label,
            fill=COMPOSITE_LABEL_COLOR,
            font=font_label,
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sheet_path = output_dir / f"emoji_preview_sheet_{timestamp}.jpg"
    canvas.save(sheet_path, "JPEG", quality=95)
    return str(sheet_path)


def _save_image_png(
    image_data: bytes,
    prefix: str = "generated",
    output_dir: Optional[Path] = None,
) -> str:
    """Save image bytes as PNG (for emoji with chroma key processing)."""
    out_dir = output_dir or _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    filename = f"{prefix}_{timestamp}_{short_id}_raw.jpg"
    filepath = out_dir / filename
    filepath.write_bytes(image_data)
    return str(filepath)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("terrycha-design")


@mcp.tool()
def design_character(
    character_name: str,
    character_description: str = None,
    style: str = None,
    outfit_description: str = None,
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
    safety_level: Optional[str] = "BLOCK_NONE",
    thinking_level: Optional[str] = None,
    output_format: str = "file",
    shots: Optional[list[str]] = None,
    output_mode: str = "full_sheet",
    both_sides: bool = False,
    composite_sheet: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_block: str = DEFAULT_ON_BLOCK,
    profile: Optional[str] = None,
    camera_preset: Optional[str] = None,
    camera_override: Optional[dict] = None,
    concept: Optional[str] = None,
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
               "upper_body". If provided, overrides output_mode.
        output_mode: Preset shot selection. Valid: "full_sheet" (default,
                     6 shots), "basic" (3 shots: face_front, face_left,
                     full_body_front), "face_angles" (3 shots: face_front,
                     face_left, face_right). Ignored when shots is provided.
                     Composite layout: full_sheet → composite_sheet,
                     basic/face_angles → composite_row.
        both_sides: Add full_body_right to default shots for asymmetric
                    accessory/feature coverage. Default: False.
        composite_sheet: Auto-generate composite reference sheet image.
                         Default: True. Only works with output_format="file".
        max_retries: Max retry attempts on safety filter block (0=no retry).
                     Default: 3.
        on_block: Behavior when safety filter blocks. "retry" = auto-retry
                  with softened prompt, "stop" = fail immediately. Default: "retry".

        profile: Character profile name to load (e.g. "siwol", "claudie").
                 Provides defaults for appearance, style, and generation params.
                 Explicitly provided parameters always override profile values.
        camera_preset: Camera/style preset name (e.g. "portrait", "fashion", "street").
        camera_override: Dict to override specific preset keys (camera, lens, lighting).
        concept: Optional concept name for design history tracking.

    Returns:
        JSON with character_name, output_dir, per-shot results, composite
        sheet path, summary counts, and generation settings.
    """
    # --- Profile loading ---
    # When a profile is specified, load its defaults for any parameter not
    # explicitly provided by the caller. This is additive: when no profile
    # is given, behavior is identical to before.
    if profile is not None:
        try:
            pm = _get_profile_manager()
            profile_params = pm.map_to_generation_params(profile)
        except FileNotFoundError as e:
            return json.dumps({"error": str(e)})

        # Apply profile defaults for parameters that were not explicitly provided
        if character_description is None:
            character_description = profile_params.get("character_description", "")
        if hair_description is None:
            hair_description = profile_params.get("hair_description")
        if expression is None:
            expression = profile_params.get("expression")
        if style is None:
            style = profile_params.get("style")
        if camera_preset is None:
            camera_preset = profile_params.get("camera_preset")
        if output_mode == "full_sheet":  # only override if caller used default
            profile_output_mode = profile_params.get("output_mode")
            if profile_output_mode is not None:
                output_mode = profile_output_mode
        if reference_images is None:
            reference_images = profile_params.get("reference_images")

    # Convert NAS paths for cross-platform compatibility
    if reference_images:
        reference_images = _convert_nas_paths(reference_images)

    # Ensure required parameters have values after profile loading
    if not character_description:
        return json.dumps({"error": "character_description is required (provide directly or via profile)"})
    if not style:
        return json.dumps({"error": "style is required (provide directly or via profile)"})
    if not outfit_description:
        outfit_description = ""  # Allow empty outfit when using profile

    # --- Resolve camera preset ---
    resolved_preset = None
    if camera_preset is not None or camera_override is not None:
        try:
            resolved_preset = resolve_preset(camera_preset, style, override=camera_override)
        except ValueError as e:
            return json.dumps({"error": str(e)})
    elif style in PHOTOREALISTIC_STYLES:
        resolved_preset = resolve_preset(None, style)  # auto-detect default
    elif style in ANIMATION_STYLES:
        resolved_preset = resolve_preset(None, style)

    # Validate retry parameters
    if on_block not in VALID_ON_BLOCK:
        return json.dumps({"error": f"Invalid on_block: {on_block}. Valid: {sorted(VALID_ON_BLOCK)}"})

    # Validate output_mode
    if output_mode not in VALID_OUTPUT_MODES:
        return json.dumps({
            "error": f"Invalid output_mode: '{output_mode}'. Valid: {sorted(VALID_OUTPUT_MODES)}"
        })

    # Resolve model
    try:
        model_id = _resolve_model(model)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Determine which shots to generate
    # shots parameter overrides output_mode when explicitly provided
    if shots is not None:
        selected_shots = list(shots)
    else:
        selected_shots = list(OUTPUT_MODE_SHOTS[output_mode])
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
        # Use build_prompt() from prompts.py when a camera/style preset is
        # resolved (photorealistic or animation styles).  Fall back to the
        # legacy _build_character_prompt() for other styles so that existing
        # behaviour is preserved.
        if resolved_preset is not None or style in PHOTOREALISTIC_STYLES or style in ANIMATION_STYLES:
            # Assemble a character description block (same logic as
            # _build_character_prompt) so build_prompt() gets a rich string.
            _char_parts = []
            if age_range:
                _char_parts.append(age_range)
            _char_parts.append(character_description)
            if body_type:
                _char_parts.append(f"{body_type} body type")
            if hair_description:
                _char_parts.append(f"Hair: {hair_description}")
            if makeup_description:
                _char_parts.append(f"Makeup: {makeup_description}")
            if accessories:
                _char_parts.append(f"Wearing accessories: {accessories}")
            if distinguishing_features:
                _char_parts.append(distinguishing_features)
            _char_block = ". ".join(_char_parts)

            # Determine ethereal flag from profile
            _is_ethereal = False
            if profile is not None:
                try:
                    _prof = _get_profile_manager().get(profile)
                    _is_ethereal = (_prof.get("appearance") or {}).get("ethereal", False)
                except FileNotFoundError:
                    pass

            shot_prompt = build_prompt(
                shot_type=shot_type,
                style=style,
                character=_char_block,
                outfit=outfit_description,
                expression=expression or "neutral, calm",
                background=background_description or "clean white studio background",
                color_palette=color_palette,
                preset=resolved_preset,
                ethereal=_is_ethereal,
            )
        else:
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
            response = _generate_with_retry(
                client, model_id, contents, shot_config,
                max_retries=max_retries, on_block=on_block,
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

            # Auto-record to design history
            try:
                _db = _get_design_db()
                _concept_id = None
                if concept:
                    _concept_id = _db.resolve_concept(concept, character_name)
                _saved_path = ""
                if extracted.get("images"):
                    _first = extracted["images"][0]
                    _saved_path = _first.get("path", "")
                if _saved_path:
                    _db.record_generation(
                        character_name=character_name,
                        profile_name=profile,
                        concept_id=_concept_id,
                        tool="design_character",
                        style=style,
                        camera_preset=camera_preset,
                        output_mode=output_mode,
                        prompt=shot_prompt,
                        model=model,
                        image_size=image_size,
                        shot_type=shot_type,
                        image_path=_saved_path,
                    )
            except Exception:
                pass  # Don't fail generation if DB recording fails

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

        # Choose composite layout based on output_mode
        # full_sheet (or custom shots) → full composite sheet
        # basic / face_angles → simpler horizontal row
        effective_mode = output_mode if shots is None else "full_sheet"
        if effective_mode == "full_sheet":
            composite_path = _create_composite_sheet(
                shot_images=shot_image_map,
                character_name=character_name,
                style=style,
                output_dir=char_dir,
            )
        else:
            composite_path = _create_composite_row(
                shot_images=shot_image_map,
                shot_order=selected_shots,
                character_name=character_name,
                mode=effective_mode,
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
    safety_level: Optional[str] = "BLOCK_NONE",
    thinking_level: Optional[str] = None,
    output_format: str = "file",
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_block: str = DEFAULT_ON_BLOCK,
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
        max_retries: Max retry attempts on safety filter block. Default: 3.
        on_block: "retry" or "stop". Default: "retry".

    Returns:
        JSON with generated image path (or base64 data), model response text,
        and metadata.
    """
    # Validate retry parameters
    if on_block not in VALID_ON_BLOCK:
        return json.dumps({"error": f"Invalid on_block: {on_block}. Valid: {sorted(VALID_ON_BLOCK)}"})

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

    reference_images = _convert_nas_paths(reference_images)

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

    response = _generate_with_retry(
        client, model_id, content_parts, config,
        max_retries=max_retries, on_block=on_block,
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

    # Auto-record to design history
    try:
        _db = _get_design_db()
        _saved_path = ""
        if extracted.get("images"):
            _first = extracted["images"][0]
            _saved_path = _first.get("path", "")
        if _saved_path:
            _db.record_generation(
                character_name=character_name or "unknown",
                tool="add_character_pose",
                style=style,
                prompt=prompt,
                model=model,
                image_size=image_size,
                shot_type="custom_pose",
                image_path=_saved_path,
            )
    except Exception:
        pass  # Don't fail generation if DB recording fails

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def generate_pose_sheet(
    reference_images: list[str],
    character_name: str,
    style: str,
    categories: Optional[list[str]] = None,
    poses: Optional[list[str]] = None,
    character_description: Optional[str] = None,
    outfit_description: Optional[str] = None,
    background_description: Optional[str] = None,
    color_palette: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    image_size: str = "512px",
    person_generation: Optional[str] = "ALLOW_ALL",
    prominent_people: Optional[str] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    safety_level: Optional[str] = "BLOCK_NONE",
    output_format: str = "file",
    composite_sheet: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_block: str = DEFAULT_ON_BLOCK,
) -> str:
    """Generate a pose sample sheet with pre-defined or custom poses.

    Creates a set of character pose images using existing reference images
    for consistency. Generates at smaller size (512px default) for speed.
    Pre-defined pose categories: daily_life, action, emotion, social.

    Args:
        reference_images: 1-3 reference image paths from design_character output.
                          Recommended: full_body_front + face_front for best results.
        character_name: Character name for folder naming and sheet title.
        style: Art style for consistency (e.g., "anime", "realistic").
        categories: List of pose category keys to generate.
                    Valid: "daily_life", "action", "emotion", "social".
                    Default: ["daily_life", "emotion"] (12 poses).
        poses: Explicit list of individual pose keys to generate.
               Overrides categories if provided. Cherry-pick from any category.
               Valid: "sitting", "walking", "running", "laughing", etc.
               Use get_design_options() for full list.
        character_description: Physical appearance details for better prompts.
        outfit_description: Clothing details for consistency.
        background_description: Default: neutral gray studio.
        color_palette: Overall color palette hint.
        model: "flash" (default) or "pro". Flash recommended for 512px.
        image_size: "512px" (default) for speed, "1K" for higher quality.
        person_generation: Default: "ALLOW_ALL".
        prominent_people: "ALLOW" or "DENY" for celebrity generation.
        temperature: 0.0-2.0. Recommended: 0.5-0.8.
        seed: Fixed seed for reproducibility.
        safety_level: Safety filter threshold.
        output_format: "file" (default) or "base64".
        composite_sheet: Auto-generate grid preview. Default: True.
        max_retries: Max retry attempts on safety filter block. Default: 3.
        on_block: "retry" or "stop". Default: "retry".

    Returns:
        JSON with per-pose results, composite sheet path, and summary.
    """
    # Validate retry parameters
    if on_block not in VALID_ON_BLOCK:
        return json.dumps({"error": f"Invalid on_block: {on_block}. Valid: {sorted(VALID_ON_BLOCK)}"})

    # Resolve model
    try:
        model_id = _resolve_model(model)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Validate parameters
    errors = _validate_params(
        model_key=model,
        aspect_ratio=POSE_SHEET_ASPECT_RATIO,
        image_size=image_size,
        output_format=output_format,
        person_generation=person_generation,
        safety_level=safety_level,
        temperature=temperature,
    )
    if errors:
        return json.dumps({"errors": errors})

    # Resolve selected poses
    selected_poses = {}
    if poses:
        # Cherry-pick individual poses across all categories
        all_poses = {}
        for cat in POSE_CATEGORIES.values():
            all_poses.update(cat["poses"])
        for p in poses:
            if p not in all_poses:
                return json.dumps({
                    "error": f"Unknown pose '{p}'. Use get_design_options() for valid poses."
                })
            selected_poses[p] = all_poses[p]
    else:
        # Use categories
        cat_keys = categories or DEFAULT_POSE_CATEGORIES
        for ck in cat_keys:
            if ck not in POSE_CATEGORIES:
                return json.dumps({
                    "error": f"Unknown category '{ck}'. "
                    f"Valid: {sorted(POSE_CATEGORIES.keys())}"
                })
            selected_poses.update(POSE_CATEGORIES[ck]["poses"])

    if not selected_poses:
        return json.dumps({"error": "No poses selected."})

    # Validate reference images
    if not reference_images:
        return json.dumps({"error": "At least one reference image is required."})

    reference_images = _convert_nas_paths(reference_images)

    max_refs = 10 if model.lower() == "flash" else 14
    if len(reference_images) > max_refs:
        reference_images = reference_images[:max_refs]

    # Load reference images
    ref_parts = []
    for ref_path in reference_images:
        ref = Path(ref_path)
        if not ref.exists():
            return json.dumps({"error": f"Reference image not found: {ref_path}"})
        mime_type = MIME_MAP.get(ref.suffix.lower(), "image/png")
        ref_parts.append(
            types.Part.from_bytes(data=ref.read_bytes(), mime_type=mime_type)
        )

    # Create output directory
    char_dir = _ensure_design_dir(f"{character_name}_poses")

    # Build character block for prompts
    char_parts = []
    if character_description:
        char_parts.append(character_description)
    if outfit_description:
        char_parts.append(outfit_description)
    character_block = ". ".join(char_parts) if char_parts else "the character"

    client = _get_client()
    results = {}
    warnings = []

    pose_keys = list(selected_poses.keys())
    for i, pose_key in enumerate(pose_keys):
        pose_def = selected_poses[pose_key]

        # Build pose prompt
        pose_prompt = POSE_PROMPT_TEMPLATE.format(
            character=character_block,
            pose_prompt=pose_def["prompt"],
            style=style,
            background=background_description or DEFAULT_BACKGROUND,
            color_palette=f"Use a {color_palette} color scheme. " if color_palette else "",
        )

        full_prompt = CONSISTENCY_PREFIX + pose_prompt

        # Build content parts
        content_parts = list(ref_parts) + [full_prompt]

        # Build config
        pose_config = _build_config(
            model_key=model,
            aspect_ratio=POSE_SHEET_ASPECT_RATIO,
            image_size=image_size,
            number_of_images=1,
            person_generation=person_generation,
            prominent_people=prominent_people,
            temperature=temperature,
            seed=seed,
            safety_level=safety_level,
        )

        try:
            response = _generate_with_retry(
                client, model_id, content_parts, pose_config,
                max_retries=max_retries, on_block=on_block,
            )

            extracted = _extract_results(
                response, output_format, prefix=f"pose_{pose_key}", output_dir=char_dir,
            )

            results[pose_key] = {
                "status": "completed",
                "pose_key": pose_key,
                "label": pose_def["label"],
                "label_ko": pose_def["label_ko"],
                **extracted,
            }

        except Exception as e:
            results[pose_key] = {
                "status": "failed",
                "pose_key": pose_key,
                "label": pose_def["label"],
                "label_ko": pose_def["label_ko"],
                "error": str(e),
            }

        # Rate limit delay
        if i < len(pose_keys) - 1:
            time.sleep(INTER_SHOT_DELAY)

    # Summary
    completed = sum(1 for r in results.values() if r["status"] == "completed")
    failed = sum(1 for r in results.values() if r["status"] == "failed")

    final_result = {
        "character_name": character_name,
        "output_dir": str(char_dir),
        "model": model_id,
        "style": style,
        "summary": {
            "total_poses": len(pose_keys),
            "completed": completed,
            "failed": failed,
        },
        "settings": {
            "image_size": image_size,
            "person_generation": person_generation,
        },
        "poses": results,
    }
    if warnings:
        final_result["warnings"] = warnings
    if seed is not None:
        final_result["settings"]["seed"] = seed
    if temperature is not None:
        final_result["settings"]["temperature"] = temperature

    # Auto-generate composite grid sheet
    if composite_sheet and output_format == "file" and completed >= 2:
        pose_image_map = {}
        pose_label_map = {}
        for pk, pr in results.items():
            if pr.get("status") == "completed" and pr.get("images"):
                first_img = pr["images"][0]
                if first_img.get("path"):
                    pose_image_map[pk] = first_img["path"]
                    pose_label_map[pk] = pr.get("label_ko", pk)

        grid_path = _create_pose_grid_sheet(
            pose_images=pose_image_map,
            pose_labels=pose_label_map,
            character_name=character_name,
            style=style,
            output_dir=char_dir,
        )
        if grid_path:
            final_result["pose_sheet"] = grid_path

    return json.dumps(final_result, ensure_ascii=False, indent=2)


@mcp.tool()
def generate_chat_emoji(
    reference_images: list[str],
    character_name: str,
    expression_set: Optional[str] = None,
    expressions: Optional[list[str]] = None,
    platform: str = "universal",
    style: Optional[str] = None,
    model: str = DEFAULT_MODEL,
    image_size: str = "512px",
    person_generation: Optional[str] = "ALLOW_ALL",
    prominent_people: Optional[str] = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    safety_level: Optional[str] = "BLOCK_NONE",
    output_format: str = "file",
    composite_sheet: bool = True,
    max_retries: int = DEFAULT_MAX_RETRIES,
    on_block: str = DEFAULT_ON_BLOCK,
) -> str:
    """Generate SD/chibi character chat emoji stickers.

    Creates cute super-deformed (SD) chibi emoji/stickers from character
    references. Supports multiple messaging platforms with automatic
    resizing and format conversion.

    The chibi transformation is applied automatically -- the character's
    key features (hair, eyes, outfit) are preserved in a 2-3 head-to-body
    ratio SD style with exaggerated expressions.

    Args:
        reference_images: 1-3 reference image paths from design_character output.
        character_name: Character name for folder naming.
        expression_set: Predefined set key. "basic_16" (16 emojis) or
                        "reaction_8" (8 emojis). Default: "basic_16".
        expressions: Explicit list of expression keys to generate.
                     Overrides expression_set. Cherry-pick across sets.
                     Valid: "happy", "sad", "angry", "thumbs_up", etc.
                     Use get_design_options() for full list.
        platform: Target platform for output sizing and format.
                  Valid: "telegram", "discord", "line", "kakaotalk",
                  "slack", "whatsapp", "universal". Default: "universal".
        style: Optional original art style hint (e.g., "anime").
               Chibi transformation is always applied regardless.
        model: "flash" (default) or "pro".
        image_size: Generation size. Default: "512px".
        person_generation: Default: "ALLOW_ALL".
        prominent_people: "ALLOW" or "DENY" for celebrity generation.
        temperature: 0.0-2.0. Recommended: 0.5-0.8.
        seed: Fixed seed for reproducibility.
        safety_level: Safety filter threshold.
        output_format: "file" (default) or "base64".
        composite_sheet: Auto-generate preview grid. Default: True.
        max_retries: Max retry attempts on safety filter block. Default: 3.
        on_block: "retry" or "stop". Default: "retry".

    Returns:
        JSON with per-emoji results, platform info, composite path, summary.
    """
    # Validate retry parameters
    if on_block not in VALID_ON_BLOCK:
        return json.dumps({"error": f"Invalid on_block: {on_block}. Valid: {sorted(VALID_ON_BLOCK)}"})

    # Resolve model
    try:
        model_id = _resolve_model(model)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Validate platform
    if platform not in EMOJI_PLATFORMS:
        return json.dumps({
            "error": f"Unknown platform '{platform}'. "
            f"Valid: {sorted(EMOJI_PLATFORMS.keys())}"
        })

    # Validate parameters
    errors = _validate_params(
        model_key=model,
        aspect_ratio="1:1",
        image_size=image_size,
        output_format=output_format,
        person_generation=person_generation,
        safety_level=safety_level,
        temperature=temperature,
    )
    if errors:
        return json.dumps({"errors": errors})

    # Resolve selected expressions
    selected_exprs = {}
    if expressions:
        # Cherry-pick across all sets
        all_exprs = {}
        for s in EMOJI_EXPRESSION_SETS.values():
            all_exprs.update(s["expressions"])
        for ek in expressions:
            if ek not in all_exprs:
                return json.dumps({
                    "error": f"Unknown expression '{ek}'. "
                    "Use get_design_options() for valid expressions."
                })
            selected_exprs[ek] = all_exprs[ek]
    else:
        set_key = expression_set or DEFAULT_EMOJI_SET
        if set_key not in EMOJI_EXPRESSION_SETS:
            return json.dumps({
                "error": f"Unknown expression_set '{set_key}'. "
                f"Valid: {sorted(EMOJI_EXPRESSION_SETS.keys())}"
            })
        selected_exprs = dict(EMOJI_EXPRESSION_SETS[set_key]["expressions"])

    if not selected_exprs:
        return json.dumps({"error": "No expressions selected."})

    # Validate reference images
    if not reference_images:
        return json.dumps({"error": "At least one reference image is required."})

    reference_images = _convert_nas_paths(reference_images)

    max_refs = 10 if model.lower() == "flash" else 14
    if len(reference_images) > max_refs:
        reference_images = reference_images[:max_refs]

    # Load reference images
    ref_parts = []
    for ref_path in reference_images:
        ref = Path(ref_path)
        if not ref.exists():
            return json.dumps({"error": f"Reference image not found: {ref_path}"})
        mime_type = MIME_MAP.get(ref.suffix.lower(), "image/png")
        ref_parts.append(
            types.Part.from_bytes(data=ref.read_bytes(), mime_type=mime_type)
        )

    # Create output directory
    char_dir = _ensure_design_dir(f"{character_name}_emoji")

    platform_spec = EMOJI_PLATFORMS[platform]

    client = _get_client()
    results = {}
    raw_images = {}  # Store pre-chroma-key paths for grid sheet

    expr_keys = list(selected_exprs.keys())
    for i, expr_key in enumerate(expr_keys):
        expr_def = selected_exprs[expr_key]

        # Build emoji prompt with chibi + chroma key
        emoji_prompt = EMOJI_CONSISTENCY_PREFIX + CHIBI_STYLE_PREFIX
        if style:
            emoji_prompt += f"{style} inspired color palette and aesthetics. "
        emoji_prompt += f"{expr_def['prompt']}. "
        emoji_prompt += f"{EMOJI_CHROMA_BG}. "

        # Build content parts
        content_parts = list(ref_parts) + [emoji_prompt]

        # Build config (always 1:1 at 512px)
        emoji_config = _build_config(
            model_key=model,
            aspect_ratio="1:1",
            image_size=image_size,
            number_of_images=1,
            person_generation=person_generation,
            prominent_people=prominent_people,
            temperature=temperature,
            seed=seed,
            safety_level=safety_level,
        )

        try:
            response = _generate_with_retry(
                client, model_id, content_parts, emoji_config,
                max_retries=max_retries, on_block=on_block,
            )

            extracted = _extract_results(
                response, output_format,
                prefix=f"emoji_{expr_key}", output_dir=char_dir,
            )

            emoji_result = {
                "status": "completed",
                "expression_key": expr_key,
                "label": expr_def["label"],
                "label_ko": expr_def["label_ko"],
            }

            # Post-process: chroma key removal + platform resize
            if output_format == "file" and extracted["images"]:
                first_img = extracted["images"][0]
                raw_path = first_img.get("path")
                if raw_path:
                    # Remove chroma key background
                    rgba_img = _remove_chroma_key_background(raw_path)

                    # Resize for target platform
                    platform_path = _resize_for_platform(
                        rgba_img, platform, char_dir, f"emoji_{expr_key}",
                    )

                    raw_images[expr_key] = raw_path
                    emoji_result["images"] = [{
                        "format": "file",
                        "path": platform_path,
                        "mime_type": f"image/{platform_spec['format']}",
                        "platform": platform,
                        "size": f"{platform_spec['size'][0]}x{platform_spec['size'][1]}",
                    }]
                    emoji_result["raw_image"] = raw_path
                else:
                    emoji_result.update(extracted)
            else:
                emoji_result.update(extracted)

            results[expr_key] = emoji_result

        except Exception as e:
            results[expr_key] = {
                "status": "failed",
                "expression_key": expr_key,
                "label": expr_def["label"],
                "label_ko": expr_def["label_ko"],
                "error": str(e),
            }

        # Rate limit delay
        if i < len(expr_keys) - 1:
            time.sleep(INTER_SHOT_DELAY)

    # Summary
    completed = sum(1 for r in results.values() if r["status"] == "completed")
    failed = sum(1 for r in results.values() if r["status"] == "failed")

    final_result = {
        "character_name": character_name,
        "output_dir": str(char_dir),
        "model": model_id,
        "platform": {
            "key": platform,
            "label": platform_spec["label"],
            "size": f"{platform_spec['size'][0]}x{platform_spec['size'][1]}",
            "format": platform_spec["format"],
        },
        "summary": {
            "total_emojis": len(expr_keys),
            "completed": completed,
            "failed": failed,
        },
        "settings": {
            "image_size": image_size,
            "person_generation": person_generation,
        },
        "expressions": results,
    }
    if style:
        final_result["style"] = style
    if seed is not None:
        final_result["settings"]["seed"] = seed
    if temperature is not None:
        final_result["settings"]["temperature"] = temperature

    # Auto-generate composite preview grid
    if composite_sheet and output_format == "file" and completed >= 2:
        emoji_image_map = {}
        emoji_label_map = {}
        for ek, er in results.items():
            if er.get("status") == "completed":
                # Use raw image (before chroma key) for more readable preview
                raw = er.get("raw_image") or (
                    er.get("images", [{}])[0].get("path") if er.get("images") else None
                )
                if raw:
                    emoji_image_map[ek] = raw
                    emoji_label_map[ek] = er.get("label_ko", ek)

        grid_path = _create_emoji_grid_sheet(
            emoji_images=emoji_image_map,
            emoji_labels=emoji_label_map,
            character_name=character_name,
            platform=platform,
            output_dir=char_dir,
        )
        if grid_path:
            final_result["emoji_preview_sheet"] = grid_path

    return json.dumps(final_result, ensure_ascii=False, indent=2)


@mcp.tool()
def estimate_generation_cost(
    tool: str,
    model: str = DEFAULT_MODEL,
    image_size: str = "1K",
    shots: Optional[list[str]] = None,
    output_mode: str = "full_sheet",
    both_sides: bool = False,
    categories: Optional[list[str]] = None,
    poses: Optional[list[str]] = None,
    expression_set: Optional[str] = None,
    expressions: Optional[list[str]] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """Estimate generation cost before running a tool.

    Calculates the number of images and approximate USD cost for a given
    tool configuration. Use this for budgeting before running expensive
    generation operations.

    Args:
        tool: Tool name to estimate. Valid: "design_character",
              "add_character_pose", "generate_pose_sheet", "generate_chat_emoji".
        model: "flash" or "pro". Default: "flash".
        image_size: Target image size. Default: "1K".
        shots: (design_character) Custom shot list. Overrides output_mode.
        output_mode: (design_character) Preset: "full_sheet" (6), "basic" (3),
                     "face_angles" (3). Default: "full_sheet".
        both_sides: (design_character) Include full_body_right. Default: False.
        categories: (generate_pose_sheet) Pose categories.
        poses: (generate_pose_sheet) Individual pose keys.
        expression_set: (generate_chat_emoji) Expression set key.
        expressions: (generate_chat_emoji) Individual expression keys.
        max_retries: Max retries per image for worst-case estimate.

    Returns:
        JSON with image_count, cost_per_image, estimated_cost,
        worst_case_cost (all retries used), and breakdown.
    """
    valid_tools = {
        "design_character", "add_character_pose",
        "generate_pose_sheet", "generate_chat_emoji",
    }
    if tool not in valid_tools:
        return json.dumps({"error": f"Unknown tool '{tool}'. Valid: {sorted(valid_tools)}"})

    # Determine cost per image
    model_key = model.lower()
    if model_key not in GENERATION_PRICING_USD:
        return json.dumps({"error": f"Unknown model '{model}'. Valid: {sorted(GENERATION_PRICING_USD.keys())}"})

    pricing = GENERATION_PRICING_USD[model_key]
    size_key = image_size if image_size in pricing else "1K"
    cost_per_image = pricing.get(size_key, pricing.get("1K", 0.039))

    # Calculate image count based on tool
    image_count = 0
    breakdown = {}

    if tool == "design_character":
        if shots:
            image_count = len(shots)
            breakdown["custom_shots"] = shots
        else:
            # Validate output_mode
            if output_mode not in VALID_OUTPUT_MODES:
                return json.dumps({
                    "error": f"Invalid output_mode: '{output_mode}'. Valid: {sorted(VALID_OUTPUT_MODES)}"
                })
            base_shots = list(OUTPUT_MODE_SHOTS[output_mode])
            if both_sides and "full_body_right" not in base_shots:
                base_shots.append("full_body_right")
            image_count = len(base_shots)
            breakdown["output_mode"] = output_mode
            breakdown["shots"] = base_shots
            breakdown["both_sides"] = both_sides

    elif tool == "add_character_pose":
        image_count = 1
        breakdown["single_pose"] = 1

    elif tool == "generate_pose_sheet":
        if poses:
            image_count = len(poses)
            breakdown["custom_poses"] = len(poses)
        else:
            selected_cats = categories or DEFAULT_POSE_CATEGORIES
            for cat_key in selected_cats:
                if cat_key in POSE_CATEGORIES:
                    cat_count = len(POSE_CATEGORIES[cat_key]["poses"])
                    breakdown[cat_key] = cat_count
                    image_count += cat_count
            if not breakdown:
                return json.dumps({"error": f"No valid categories found. Valid: {sorted(POSE_CATEGORIES.keys())}"})

    elif tool == "generate_chat_emoji":
        if expressions:
            image_count = len(expressions)
            breakdown["custom_expressions"] = len(expressions)
        else:
            set_key = expression_set or DEFAULT_EMOJI_SET
            if set_key in EMOJI_EXPRESSION_SETS:
                image_count = len(EMOJI_EXPRESSION_SETS[set_key]["expressions"])
                breakdown[set_key] = image_count
            else:
                return json.dumps({
                    "error": f"Unknown expression_set '{set_key}'. "
                    f"Valid: {sorted(EMOJI_EXPRESSION_SETS.keys())}"
                })

    estimated_cost = image_count * cost_per_image
    worst_case_cost = image_count * cost_per_image * (max_retries + 1)

    result = {
        "tool": tool,
        "model": model_key,
        "image_size": image_size,
        "image_count": image_count,
        "cost_per_image_usd": round(cost_per_image, 4),
        "estimated_cost_usd": round(estimated_cost, 4),
        "worst_case_cost_usd": round(worst_case_cost, 4),
        "worst_case_note": f"If all {image_count} images hit safety filter and retry {max_retries} times each",
        "max_retries": max_retries,
        "breakdown": breakdown,
        "pricing_note": "Approximate costs based on Gemini API pricing. Actual costs may vary.",
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_prompt_dictionary(
    category: Optional[str] = None,
) -> str:
    """Get the character design prompt dictionary reference.

    Returns curated descriptive phrases organized by category for building
    character design prompts. Use these terms in character_description,
    outfit_description, hair_description, and other detail fields.

    Args:
        category: Optional specific category to retrieve. If None, returns
                  list of available categories with summaries.
                  Valid categories: "body_types", "facial_features",
                  "hair_styles", "clothing", "expressions", "poses",
                  "art_styles", "lighting", "camera_angles",
                  "color_palettes", "accessories", "age_descriptors",
                  "backgrounds"

    Returns:
        JSON with category content or category index.
    """
    if category is None:
        # Return index of all categories
        index = {}
        for key, data in PROMPT_DICTIONARY.items():
            index[key] = {
                "label": data["label"],
                "label_ko": data["label_ko"],
                "description": data["description"],
                "term_count": len(data["entries"]),
            }
        return json.dumps({
            "total_categories": len(PROMPT_DICTIONARY),
            "categories": index,
            "usage": "Call get_prompt_dictionary(category='<key>') for full details.",
        }, ensure_ascii=False, indent=2)

    if category not in PROMPT_DICTIONARY:
        return json.dumps({
            "error": f"Unknown category '{category}'. "
            f"Valid: {sorted(PROMPT_DICTIONARY.keys())}"
        })

    data = PROMPT_DICTIONARY[category]
    return json.dumps({
        "category": category,
        "label": data["label"],
        "label_ko": data["label_ko"],
        "description": data["description"],
        "entries": data["entries"],
        "term_count": len(data["entries"]),
    }, ensure_ascii=False, indent=2)


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
        "output_modes": {
            key: {
                "shots": shots,
                "shot_count": len(shots),
                "composite_layout": "composite_sheet" if key == "full_sheet" else "composite_row",
            }
            for key, shots in OUTPUT_MODE_SHOTS.items()
        },
        "features": {
            "composite_sheet": "Auto-generates a single composite reference image",
            "both_sides": "Adds full_body_right for asymmetric accessory coverage (default: off)",
            "output_mode": "Preset shot selection: 'full_sheet' (6 shots), 'basic' (3 shots), 'face_angles' (3 shots)",
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
        "pose_sheet": {
            "description": "Generate pose sample sheets with pre-defined poses (generate_pose_sheet)",
            "categories": {
                key: {
                    "label": cat["label"],
                    "label_ko": cat["label_ko"],
                    "pose_count": len(cat["poses"]),
                    "poses": list(cat["poses"].keys()),
                }
                for key, cat in POSE_CATEGORIES.items()
            },
            "defaults": {
                "categories": DEFAULT_POSE_CATEGORIES,
                "image_size": POSE_SHEET_IMAGE_SIZE,
            },
        },
        "chat_emoji": {
            "description": "Generate SD/chibi chat emoji stickers (generate_chat_emoji)",
            "expression_sets": {
                key: {
                    "label": s["label"],
                    "label_ko": s["label_ko"],
                    "count": len(s["expressions"]),
                    "expressions": list(s["expressions"].keys()),
                }
                for key, s in EMOJI_EXPRESSION_SETS.items()
            },
            "platforms": {
                key: {
                    "label": p["label"],
                    "label_ko": p["label_ko"],
                    "size": f"{p['size'][0]}x{p['size'][1]}",
                    "format": p["format"],
                    "max_size_kb": p["max_size_kb"],
                }
                for key, p in EMOJI_PLATFORMS.items()
            },
            "defaults": {
                "expression_set": DEFAULT_EMOJI_SET,
                "platform": DEFAULT_EMOJI_PLATFORM,
            },
        },
        "prompt_dictionary": {
            "description": "Curated prompt reference phrases (get_prompt_dictionary)",
            "categories": list(PROMPT_DICTIONARY.keys()),
            "total_categories": len(PROMPT_DICTIONARY),
        },
        "safety_retry": {
            "description": "Automatic retry on safety filter blocks with prompt softening",
            "defaults": {
                "max_retries": DEFAULT_MAX_RETRIES,
                "on_block": DEFAULT_ON_BLOCK,
            },
            "on_block_options": sorted(VALID_ON_BLOCK),
            "note": "Set on_block='stop' to fail immediately instead of retrying",
        },
        "cost_estimation": {
            "description": "Pre-generation cost estimation (estimate_generation_cost)",
            "pricing_usd_per_image": GENERATION_PRICING_USD,
            "note": "Approximate costs. Use estimate_generation_cost tool for detailed breakdown.",
        },
        "camera_presets": {
            "photorealistic": sorted(PHOTO_PRESETS.keys()),
            "animation": sorted(ANIMATION_PRESETS.keys()),
            "note": "Use camera_preset param in design_character or pass camera_override dict",
        },
        "profiles": {
            "description": "Character profiles for IP management (create/get/update/delete/list_character_profiles)",
            "available": [p["name"] for p in _get_profile_manager().list_profiles()],
            "note": "Pass profile='name' to design_character to auto-fill appearance/style defaults",
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


@mcp.tool()
def create_character_profile(
    name: str,
    appearance: dict,
    personality: dict = None,
    style_preferences: dict = None,
    background: dict = None,
    branding: dict = None,
    generation_defaults: dict = None,
) -> str:
    """Create a new character profile for IP management.

    Profiles store appearance, personality, style preferences, and generation
    defaults.  Once created, pass the profile name to design_character() to
    auto-fill character parameters.

    Args:
        name: Character name (case-insensitive, used as filename).
        appearance: Dict with appearance fields (age_range, ethnicity, body_type,
                    skin, face, eyes, hair, distinguishing, ethereal).
        personality: Optional personality dict (mbti, keywords, expression).
        style_preferences: Optional style preferences dict.
        background: Optional background/backstory dict.
        branding: Optional branding dict (catchphrase, signature_poses).
        generation_defaults: Optional generation defaults dict
                             (style, camera_preset, output_mode, reference_images).

    Returns:
        JSON with status, path, and name.
    """
    pm = _get_profile_manager()
    profile_data = {"name": name, "version": 1, "appearance": appearance}
    if personality:
        profile_data["personality"] = personality
    if style_preferences:
        profile_data["style_preferences"] = style_preferences
    if background:
        profile_data["background"] = background
    if branding:
        profile_data["branding"] = branding
    if generation_defaults:
        profile_data["generation_defaults"] = generation_defaults
    path = pm.create(profile_data)
    return json.dumps({"status": "created", "path": str(path), "name": name})


@mcp.tool()
def get_character_profile(name: str) -> str:
    """Get a character profile by name.

    Args:
        name: Character name (case-insensitive).

    Returns:
        JSON with full profile data.
    """
    pm = _get_profile_manager()
    prof = pm.get(name)
    return json.dumps(prof, indent=2, default=str)


@mcp.tool()
def update_character_profile(name: str, updates: dict) -> str:
    """Update character profile fields using dot-notation paths.

    Args:
        name: Character name (case-insensitive).
        updates: Dict of dot-notation paths to new values,
                 e.g. {"appearance.eyes": "blue", "generation_defaults.style": "anime"}.

    Returns:
        JSON with status, version, and name.
    """
    pm = _get_profile_manager()
    updated = pm.update(name, updates)
    return json.dumps({"status": "updated", "version": updated["version"], "name": name})


@mcp.tool()
def delete_character_profile(name: str, confirm: bool = False) -> str:
    """Delete a character profile.  Set confirm=True to proceed.

    Args:
        name: Character name (case-insensitive).
        confirm: Must be True to perform deletion.

    Returns:
        JSON with status and name.
    """
    pm = _get_profile_manager()
    pm.delete(name, confirm=confirm)
    return json.dumps({"status": "deleted", "name": name})


@mcp.tool()
def list_character_profiles(limit: int = 50) -> str:
    """List all available character profiles.

    Args:
        limit: Maximum number of profiles to return (default 50).

    Returns:
        JSON with profiles list and count.
    """
    pm = _get_profile_manager()
    profiles = pm.list_profiles(limit=limit)
    return json.dumps({"profiles": profiles, "count": len(profiles)}, indent=2)


@mcp.tool()
def suggest_outfits(
    profile: str,
    concept: str,
) -> str:
    """Suggest 3 coordinated outfits based on character profile and styling concept.

    Args:
        profile: Character profile name (e.g., "siwol", "claudie").
        concept: Styling concept - one of: casual, street, formal, sporty, date, minimal, cozy.
    """
    import sqlite3
    import random

    VALID_CONCEPTS = {"casual", "street", "formal", "sporty", "date", "minimal", "cozy"}
    if concept not in VALID_CONCEPTS:
        return json.dumps({"error": f"Invalid concept '{concept}'. Valid: {sorted(VALID_CONCEPTS)}"})

    # Load profile
    pm = _get_profile_manager()
    try:
        prof = pm.get(profile)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    style_prefs = prof.get("style_preferences", {})
    theme_colors = style_prefs.get("theme_colors", [])
    brand_vibe = style_prefs.get("brand_vibe", [])

    # Connect to catalog.db (env var > platform default)
    db_path = os.environ.get("PRODUCT_CATALOG_DB")
    if not db_path:
        # Auto-detect platform default
        _catalog_defaults = [
            _NAS_PATH_MAP["macos"] + "Claudie/product_catalog/catalog.db",
            _NAS_PATH_MAP["windows"] + "Claudie/product_catalog/catalog.db",
            _NAS_PATH_MAP["unc"] + "Claudie/product_catalog/catalog.db",
        ]
        for candidate in _catalog_defaults:
            if Path(candidate).exists():
                db_path = candidate
                break
    if not db_path or not Path(db_path).exists():
        return json.dumps({"error": f"Product catalog database not found. Set PRODUCT_CATALOG_DB environment variable. Searched: {_catalog_defaults if not db_path else db_path}"})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Category slots for outfit assembly
    CONCEPT_CATEGORIES = {
        "casual": ["top", "bottom", "shoes"],
        "street": ["top", "bottom", "outerwear", "shoes"],
        "formal": ["top", "bottom", "shoes", "accessories"],
        "sporty": ["top", "bottom", "shoes"],
        "date": ["top", "bottom", "shoes", "accessories"],
        "minimal": ["top", "bottom", "shoes"],
        "cozy": ["top", "outerwear", "bottom", "shoes"],
    }

    categories = CONCEPT_CATEGORIES.get(concept, ["top", "bottom", "shoes"])

    # Query products per category
    proposals = []

    for option_idx, option_label in enumerate(["A", "B", "C"]):
        items = []
        for cat in categories:
            # Build query with brand affinity
            query = "SELECT product_id, brand, name, price, colors, fit, local_image_path FROM products WHERE 1=1"
            params = []

            # Category filter (loose match on name/category fields)
            if cat in ("top", "bottom", "outerwear", "shoes", "accessories"):
                query += " AND (category LIKE ? OR sub_category LIKE ?)"
                params.extend([f"%{cat}%", f"%{cat}%"])

            # Brand affinity (prefer profile brands but don't require)
            if brand_vibe:
                brand_clause = " OR ".join(["brand LIKE ?" for _ in brand_vibe])
                query += f" AND ({brand_clause} OR 1=1)"
                params.extend([f"%{b}%" for b in brand_vibe])

            query += " ORDER BY RANDOM() LIMIT 5"

            try:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
                if rows:
                    # Pick one (with some randomness per proposal)
                    row = rows[min(option_idx, len(rows) - 1)]
                    items.append({
                        "product_id": row["product_id"],
                        "brand": row["brand"],
                        "name": row["name"],
                        "category": cat,
                        "price": str(row["price"]) if row["price"] else "",
                        "color": row["colors"] if row["colors"] else "",
                    })
            except Exception:
                continue

        if len(items) >= 2:  # minimum: top + bottom
            proposals.append({
                "option": option_label,
                "description": f"{concept.capitalize()} look for {profile}",
                "items": items,
                "rationale": f"Matches {profile}'s style preferences with {concept} concept",
            })

    conn.close()

    return json.dumps({
        "character": profile,
        "concept": concept,
        "proposals": proposals,
    }, indent=2, default=str)


@mcp.tool()
def try_on_product(
    profile: str,
    product_id: str = None,
    product_query: str = None,
    product_ids: list = None,
    camera_preset: str = "fashion",
    output_mode: str = "basic",
    background: str = None,
    pose: str = None,
    concept: str = None,
    model: str = "flash",
    image_size: str = "1K",
) -> str:
    """Generate character wearing real products from catalog.

    Args:
        profile: Character profile name.
        product_id: Single product ID from catalog.db.
        product_query: Natural language product search.
        product_ids: List of product IDs for full outfit.
        camera_preset: Camera preset (default: fashion).
        output_mode: Output mode (default: basic).
        background: Custom background description.
        pose: Pose description.
        concept: Concept name for design history.
        model: Generation model (flash or pro).
        image_size: Image size.
    """
    import sqlite3

    # Resolve product input
    try:
        input_type, input_value = _resolve_product_input(product_ids, product_id, product_query)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Load profile
    pm = _get_profile_manager()
    try:
        prof = pm.get(profile)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)})

    # Connect to catalog.db
    db_path = os.environ.get("PRODUCT_CATALOG_DB")
    if not db_path or not Path(db_path).exists():
        return json.dumps({"error": "Product catalog database not found. Set PRODUCT_CATALOG_DB environment variable."})

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Resolve products
    products = []
    reference_product_images = []

    if input_type == "product_ids":
        for pid in input_value:
            row = conn.execute("SELECT * FROM products WHERE product_id = ?", (pid,)).fetchone()
            if row:
                products.append(dict(row))
                if row["local_image_path"] and Path(row["local_image_path"]).exists():
                    reference_product_images.append(row["local_image_path"])
    elif input_type == "product_id":
        row = conn.execute("SELECT * FROM products WHERE product_id = ?", (input_value,)).fetchone()
        if row:
            products.append(dict(row))
            if row["local_image_path"] and Path(row["local_image_path"]).exists():
                reference_product_images.append(row["local_image_path"])
    elif input_type == "product_query":
        rows = conn.execute(
            "SELECT * FROM products WHERE name LIKE ? OR brand LIKE ? LIMIT 1",
            (f"%{input_value}%", f"%{input_value}%")
        ).fetchall()
        for row in rows:
            products.append(dict(row))
            if row["local_image_path"] and Path(row["local_image_path"]).exists():
                reference_product_images.append(row["local_image_path"])

    conn.close()

    if not products:
        return json.dumps({"error": "No products found matching the selection criteria."})

    # Build outfit description from products
    outfit_parts = []
    for p in products:
        part = f"{p.get('brand', '')} {p.get('name', '')}"
        if p.get('fit'):
            part += f", {p['fit']} fit"
        if p.get('materials'):
            part += f", {p['materials']}"
        if p.get('colors'):
            part += f", in {p['colors']}"
        outfit_parts.append(part.strip())

    outfit_description = "Wearing " + " with ".join(outfit_parts)
    if pose:
        outfit_description += f". {pose}"

    # Build reference images list from profile + product images
    profile_params = pm.map_to_generation_params(profile)
    ref_images = list(profile_params.get("reference_images", []) or [])
    ref_images.extend(reference_product_images)

    # Call design_character internally (access underlying fn from FunctionTool)
    _design_fn = design_character.fn if hasattr(design_character, "fn") else design_character
    result = _design_fn(
        profile=profile,
        outfit_description=outfit_description,
        camera_preset=camera_preset,
        output_mode=output_mode,
        background_description=background or "clean studio background, soft lighting",
        reference_images=ref_images if ref_images else None,
        concept=concept,
        model=model,
        image_size=image_size,
    )

    # Parse result and add product metadata
    try:
        result_data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        result_data = {"raw_result": str(result)}

    # Add product info
    product_info = []
    for p in products:
        product_info.append({
            "product_id": p.get("product_id", ""),
            "brand": p.get("brand", ""),
            "name": p.get("name", ""),
            "price": str(p.get("price", "")),
            "url": p.get("url", ""),
        })

    result_data["products"] = product_info
    result_data["outfit_description"] = outfit_description

    # Auto-record try_on_product to design history with product_ids
    try:
        _db = _get_design_db()
        _concept_id = None
        _char_name = result_data.get("character_name", profile)
        if concept:
            _concept_id = _db.resolve_concept(concept, _char_name)
        # Find the first generated image path from the nested result
        _img_path = ""
        for _shot_data in (result_data.get("shots") or {}).values():
            if _shot_data.get("status") == "completed" and _shot_data.get("images"):
                _img_path = _shot_data["images"][0].get("path", "")
                if _img_path:
                    break
        _pid_list = [p.get("product_id", "") for p in products]
        if _img_path:
            _db.record_generation(
                character_name=_char_name,
                profile_name=profile,
                concept_id=_concept_id,
                tool="try_on_product",
                style=result_data.get("style"),
                camera_preset=camera_preset,
                output_mode=output_mode,
                prompt=outfit_description,
                model=model,
                image_size=image_size,
                image_path=_img_path,
                product_ids=json.dumps(_pid_list),
            )
    except Exception:
        pass  # Don't fail generation if DB recording fails

    return json.dumps(result_data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Design DB MCP Tools — Concept & History Management
# ---------------------------------------------------------------------------

@mcp.tool()
def create_concept(
    name: str,
    character_name: str,
    description: str = None,
    tags: list = None,
) -> str:
    """Create a themed concept/series for organizing character designs.

    Args:
        name: Concept name (must be unique per character).
        character_name: Character this concept belongs to.
        description: Optional description of the concept.
        tags: Optional list of tags for categorization.
    """
    db = _get_design_db()
    cid = db.create_concept(name, character_name, description=description, tags=tags)
    return json.dumps({"status": "created", "concept_id": cid, "name": name})


@mcp.tool()
def list_concepts(
    character: str = None,
    status: str = None,
    limit: int = 50,
) -> str:
    """List design concepts/series with optional filters.

    Args:
        character: Filter by character name.
        status: Filter by status (e.g., "active", "completed").
        limit: Maximum number of concepts to return (default 50).
    """
    db = _get_design_db()
    concepts = db.list_concepts(character=character, status=status, limit=limit)
    return json.dumps({"concepts": concepts, "count": len(concepts)}, indent=2, default=str)


@mcp.tool()
def search_generations(
    character: str = None,
    concept: str = None,
    style: str = None,
    rating_min: int = None,
    date_from: str = None,
    date_to: str = None,
    favorite_only: bool = False,
    limit: int = 100,
) -> str:
    """Search design generation history with filters.

    Args:
        character: Filter by character name.
        concept: Filter by concept name.
        style: Filter by art style.
        rating_min: Minimum rating (1-5).
        date_from: Start date (ISO format, e.g., "2026-01-01").
        date_to: End date (ISO format).
        favorite_only: Only return favorited generations.
        limit: Maximum results (default 100).
    """
    db = _get_design_db()
    results = db.search_generations(
        character=character, concept=concept, style=style,
        rating_min=rating_min, date_from=date_from, date_to=date_to,
        favorite_only=favorite_only, limit=limit,
    )
    return json.dumps({"generations": results, "count": len(results)}, indent=2, default=str)


@mcp.tool()
def rate_generation(
    generation_id: int,
    rating: int = None,
    favorite: bool = None,
    tags: list = None,
    notes: str = None,
) -> str:
    """Rate, favorite, or annotate a generated image.

    Args:
        generation_id: ID of the generation record.
        rating: Rating score (1-5).
        favorite: Mark as favorite.
        tags: List of tags to apply.
        notes: Free-text notes.
    """
    db = _get_design_db()
    db.rate_generation(generation_id, rating=rating, favorite=favorite, tags=tags, notes=notes)
    return json.dumps({"status": "updated", "generation_id": generation_id})


if __name__ == "__main__":
    mcp.run(transport="stdio")
