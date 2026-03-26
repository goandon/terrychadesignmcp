"""Image I/O, NAS path mapping, and composite sheet utilities for terrychadesignmcp.

Author: Terry.Kim <goandonh@gmail.com>
Co-Author: Claudie
"""

import os
import sys
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross-platform NAS path mapping
# ---------------------------------------------------------------------------
# Single source of truth: profiles store macOS paths.
# On Windows, auto-convert /Volumes/NAS_Data/ <-> X:/ (SMB mount).
NAS_PATH_MAP = {
    "macos": os.environ.get("NAS_MACOS_PATH", "/Volumes/NAS_Data/"),
    "windows": os.environ.get("NAS_WINDOWS_PATH", "X:/"),
    "unc": os.environ.get("NAS_UNC_PATH", "//your-nas-ip/share/"),
}


def convert_nas_path(path_str: str) -> str:
    """Convert NAS path to current platform equivalent."""
    is_windows = sys.platform == "win32"
    if is_windows:
        # macOS -> Windows
        if path_str.startswith(NAS_PATH_MAP["macos"]):
            return path_str.replace(NAS_PATH_MAP["macos"], NAS_PATH_MAP["windows"], 1)
    else:
        # Windows -> macOS
        if path_str.startswith(NAS_PATH_MAP["windows"]):
            return path_str.replace(NAS_PATH_MAP["windows"], NAS_PATH_MAP["macos"], 1)
        # UNC -> macOS
        for unc_prefix in (NAS_PATH_MAP["unc"], NAS_PATH_MAP["unc"].replace("/", "\\")):
            if path_str.startswith(unc_prefix):
                return path_str.replace(unc_prefix, NAS_PATH_MAP["macos"], 1)
    return path_str


def convert_nas_paths(paths: list[str]) -> list[str]:
    """Convert a list of NAS paths to current platform."""
    return [convert_nas_path(p) for p in paths]


# ---------------------------------------------------------------------------
# Image output defaults
# ---------------------------------------------------------------------------

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
# Pose Sheet Constants
# ---------------------------------------------------------------------------

POSE_SHEET_IMAGE_SIZE = "512px"
POSE_SHEET_ASPECT_RATIO = "1:1"
POSE_SHEET_GRID_PADDING = 12
POSE_SHEET_GRID_BORDER = 20
POSE_SHEET_HEADER_HEIGHT = 48
POSE_SHEET_LABEL_HEIGHT = 28
POSE_SHEET_BG_COLOR = (245, 245, 245)


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
    "ico": {
        "label": "ICO (Multi-size)",
        "label_ko": "아이콘",
        "size": (256, 256),
        "format": "ico",
        "max_size_kb": None,
        "notes": "Windows icon, multi-size (16+32+48+256)",
    },
}
DEFAULT_EMOJI_PLATFORM = "universal"

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
# File I/O helpers
# ---------------------------------------------------------------------------

def ensure_output_dir(output_dir: Path) -> Path:
    """Ensure the base output directory exists."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_design_dir(character_name: str, output_dir: Path) -> Path:
    """Create and return a character-specific output directory."""
    safe_name = "".join(
        c if c.isalnum() or c in ("-", "_", " ") else "_"
        for c in character_name
    ).strip().replace(" ", "_")[:50]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    char_dir = output_dir / f"{safe_name}_{timestamp}"
    char_dir.mkdir(parents=True, exist_ok=True)
    return char_dir


def save_image(
    image_data: bytes,
    prefix: str = "generated",
    output_dir: Optional[Path] = None,
) -> str:
    """Save image bytes to a file and return the absolute path.

    Args:
        image_data: Raw image bytes.
        prefix: Filename prefix.
        output_dir: Directory to save into (must be provided).

    Raises:
        ValueError: If output_dir is None.
    """
    if output_dir is None:
        raise ValueError("output_dir must be provided")
    out_dir = ensure_output_dir(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    filename = f"{prefix}_{timestamp}_{short_id}.jpg"
    filepath = out_dir / filename
    filepath.write_bytes(image_data)
    return str(filepath)


# ---------------------------------------------------------------------------
# Font Loading
# ---------------------------------------------------------------------------

def load_fonts(header_size: int = 24, label_size: int = 13):
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


# ---------------------------------------------------------------------------
# Composite Sheet Builder
# ---------------------------------------------------------------------------

def create_composite_sheet(
    shot_images: dict[str, str],
    character_name: str,
    style: str,
    output_dir: Path,
    shot_definitions: dict,
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
    font_header, font_label = load_fonts(32, 15)

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
    face_label = "\uc5bc\uad74 \uc88c / \uc815 / \uc6b0"
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
            label = shot_definitions[shot_type]["label_ko"]
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

def create_composite_row(
    shot_images: dict[str, str],
    shot_order: list[str],
    character_name: str,
    mode: str,
    output_dir: Path,
    shot_definitions: dict,
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
    font_header, font_label = load_fonts(28, 14)

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
        label = shot_definitions[shot_type]["label_ko"]
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

def create_pose_grid_sheet(
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

    font_header, font_label = load_fonts(24, 13)

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

def remove_chroma_key_background(
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


def resize_for_platform(
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


def create_emoji_grid_sheet(
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

    font_header, font_label = load_fonts(20, 11)

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


# ---------------------------------------------------------------------------
# ICO Export
# ---------------------------------------------------------------------------

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (256, 256)]


def export_ico(image: Image.Image, output_path: str) -> str:
    """Export RGBA image as multi-size ICO file.

    Pre-resizes to each target size to avoid Pillow quantize errors with
    large RGBA images.
    """
    rgba = image.convert("RGBA")
    # Pre-resize to each ICO size to avoid quantization issues
    ico_images = []
    for size in ICO_SIZES:
        resized = rgba.resize(size, Image.LANCZOS)
        ico_images.append(resized)
    # Save the largest as base, with all sizes embedded
    ico_images[0].save(
        output_path,
        format="ICO",
        sizes=ICO_SIZES,
        append_images=ico_images[1:],
    )
    return output_path


# ---------------------------------------------------------------------------
# Sheet Splitting Constants
# ---------------------------------------------------------------------------

ROW_Y_TOLERANCE_FACTOR = 0.3  # Fraction of cell_height for row grouping in contour sort


# ---------------------------------------------------------------------------
# Sheet Splitting Functions
# ---------------------------------------------------------------------------

def uniform_grid_split(image: Image.Image, cols: int, rows: int) -> list[Image.Image]:
    """Split image into equal grid cells and return them as RGBA images.

    Args:
        image: Source PIL image.
        cols: Number of columns.
        rows: Number of rows.

    Returns:
        List of RGBA cell images in row-major order (left-to-right, top-to-bottom).
    """
    w, h = image.size
    cell_w = w // cols
    cell_h = h // rows
    cells = []
    for r in range(rows):
        for c in range(cols):
            x0 = c * cell_w
            y0 = r * cell_h
            x1 = x0 + cell_w
            y1 = y0 + cell_h
            cell = image.crop((x0, y0, x1, y1)).convert("RGBA")
            cells.append(cell)
    return cells


def _group_into_rows(bboxes: list[tuple], row_tolerance: float) -> list[list[tuple]]:
    """Group bounding boxes into rows by Y-coordinate proximity.

    Args:
        bboxes: List of (x, y, w, h) bounding boxes.
        row_tolerance: Maximum Y difference to consider boxes in the same row.

    Returns:
        List of rows, each row being a list of bboxes sorted by X coordinate.
    """
    if not bboxes:
        return []

    # Sort by top-Y
    sorted_boxes = sorted(bboxes, key=lambda b: b[1])

    rows = []
    current_row = [sorted_boxes[0]]
    current_y = sorted_boxes[0][1]

    for box in sorted_boxes[1:]:
        if abs(box[1] - current_y) <= row_tolerance:
            current_row.append(box)
        else:
            # Sort current row by X and start a new row
            rows.append(sorted(current_row, key=lambda b: b[0]))
            current_row = [box]
            current_y = box[1]

    # Append the last row
    rows.append(sorted(current_row, key=lambda b: b[0]))
    return rows


def split_sheet_by_contour(
    image_path: str,
    expected_count: int,
    cols: int,
    chroma_color: tuple = (0, 255, 0),
    tolerance: int = 60,
    min_area_ratio: float = 0.002,
    padding: int = 4,
) -> list[Image.Image]:
    """Split a chroma-key sheet into individual cell images using contour detection.

    Loads the image, creates a foreground mask (pixels NOT matching the chroma key),
    then uses OpenCV contour detection to find individual cells. Uses all detected
    contours (sorted by area, top-N if more than expected) rather than requiring
    an exact count match. Falls back to uniform_grid_split only if cv2 is
    unavailable or no valid contours are found.

    Args:
        image_path: Path to the sheet image file.
        expected_count: Expected number of cells (e.g. 16 for a 4x4 grid).
        cols: Number of columns (used to derive rows for fallback and row grouping).
        chroma_color: Background chroma key color as (R, G, B).
        tolerance: Color distance tolerance for chroma key mask.
        min_area_ratio: Minimum contour area as fraction of total image area.
        padding: Extra pixels around each bounding box to avoid clipping.

    Returns:
        List of RGBA cell images in row-major order.
    """
    img_pil = Image.open(image_path).convert("RGB")
    rows = expected_count // cols
    img_w, img_h = img_pil.size

    try:
        import cv2

        img_np = np.array(img_pil)
        total_area = img_np.shape[0] * img_np.shape[1]
        min_area = total_area * min_area_ratio

        # Build foreground mask using numpy pixel distance from chroma color
        cr, cg, cb = chroma_color
        diff = img_np.astype(np.float32) - np.array([cr, cg, cb], dtype=np.float32)
        dist = np.sqrt(np.sum(diff ** 2, axis=2))
        # Foreground: pixels NOT matching chroma key
        fg_mask = (dist >= tolerance).astype(np.uint8) * 255

        # Morphological closing to merge near-adjacent fragments
        cell_h_est = img_np.shape[0] // max(rows, 1)
        cell_w_est = img_np.shape[1] // max(cols, 1)
        kernel_size = max(3, min(cell_h_est, cell_w_est) // 10)
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (kernel_size, kernel_size)
        )
        closed = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)

        # Find contours
        contours, _ = cv2.findContours(
            closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Filter by minimum area and sort by area descending
        valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area]
        valid_contours.sort(key=lambda c: cv2.contourArea(c), reverse=True)

        if not valid_contours:
            logger.warning(
                "split_sheet_by_contour: no valid contours found — "
                "falling back to uniform_grid_split"
            )
            return uniform_grid_split(img_pil, cols=cols, rows=rows)

        # Use detected contours: if more than expected, take top-N by area
        if len(valid_contours) > expected_count:
            logger.info(
                "split_sheet_by_contour: found %d contours, using top %d by area",
                len(valid_contours),
                expected_count,
            )
            valid_contours = valid_contours[:expected_count]
        elif len(valid_contours) < expected_count:
            # If detected less than half of expected, contour detection is unreliable
            # Fall back to uniform grid split
            if len(valid_contours) < expected_count // 2:
                logger.warning(
                    "split_sheet_by_contour: found only %d contours (expected %d) — "
                    "falling back to uniform_grid_split",
                    len(valid_contours),
                    expected_count,
                )
                return uniform_grid_split(img_pil, cols=cols, rows=rows)
            logger.info(
                "split_sheet_by_contour: found %d contours (expected %d), "
                "using all detected",
                len(valid_contours),
                expected_count,
            )

        # Extract bounding boxes with padding
        bboxes = []
        for c in valid_contours:
            x, y, w, h = cv2.boundingRect(c)
            # Apply padding, clamped to image bounds
            x0 = max(0, x - padding)
            y0 = max(0, y - padding)
            x1 = min(img_w, x + w + padding)
            y1 = min(img_h, y + h + padding)
            bboxes.append((x0, y0, x1 - x0, y1 - y0))

        # Compute row tolerance from estimated cell height
        row_tolerance = cell_h_est * ROW_Y_TOLERANCE_FACTOR

        grouped = _group_into_rows(bboxes, row_tolerance)

        cells = []
        for row_bboxes in grouped:
            for x, y, w, h in row_bboxes:
                cell = img_pil.crop((x, y, x + w, y + h)).convert("RGBA")
                cells.append(cell)
        return cells

    except ImportError:
        logger.warning(
            "split_sheet_by_contour: cv2 not available — "
            "falling back to uniform_grid_split"
        )
        return uniform_grid_split(img_pil, cols=cols, rows=rows)


# ---------------------------------------------------------------------------
# Animated Image Builders
# ---------------------------------------------------------------------------

def _apply_bounce(frames: list[Image.Image]) -> list[Image.Image]:
    """Apply bounce pattern: 1->2->3->2 (no duplicate at endpoints)."""
    if len(frames) <= 2:
        return frames
    return frames + frames[-2:0:-1]


def create_animated_gif(
    frames: list[Image.Image],
    output_path: str,
    delay_ms: int = 200,
    loop: int = 0,
    mode: str = "sequential",
) -> str:
    """Create animated GIF from RGBA frame images.

    Args:
        frames: List of RGBA PIL images (at least 2).
        output_path: Destination file path (must end in .gif).
        delay_ms: Frame delay in milliseconds.
        loop: Number of loops (0 = infinite).
        mode: "sequential" or "bounce" (plays forward then reverse).

    Returns:
        output_path after saving.

    Raises:
        ValueError: If fewer than 2 frames are provided.
    """
    if len(frames) < 2:
        raise ValueError("Need at least 2 frames for animation")
    if mode == "bounce":
        frames = _apply_bounce(frames)
    processed = []
    for frame in frames:
        alpha = frame.getchannel("A")
        p_frame = frame.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
        mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)
        p_frame.paste(255, mask)
        p_frame.info["transparency"] = 255
        processed.append(p_frame)
    processed[0].save(
        output_path, format="GIF", save_all=True,
        append_images=processed[1:],
        duration=delay_ms, loop=loop,
        disposal=2, optimize=True,
    )
    return output_path


def create_animated_webp(
    frames: list[Image.Image],
    output_path: str,
    delay_ms: int = 200,
    loop: int = 0,
    mode: str = "sequential",
    quality: int = 80,
) -> str:
    """Create animated WebP from RGBA frame images.

    Args:
        frames: List of RGBA PIL images (at least 2).
        output_path: Destination file path (must end in .webp).
        delay_ms: Frame delay in milliseconds.
        loop: Number of loops (0 = infinite).
        mode: "sequential" or "bounce" (plays forward then reverse).
        quality: WebP quality (0-100).

    Returns:
        output_path after saving.

    Raises:
        ValueError: If fewer than 2 frames are provided.
    """
    if len(frames) < 2:
        raise ValueError("Need at least 2 frames for animation")
    if mode == "bounce":
        frames = _apply_bounce(frames)
    frames[0].save(
        output_path, format="WEBP", save_all=True,
        append_images=frames[1:],
        duration=delay_ms, loop=loop,
        quality=quality, lossless=False,
    )
    return output_path


def save_image_png(
    image_data: bytes,
    prefix: str = "generated",
    output_dir: Optional[Path] = None,
) -> str:
    """Save image bytes as PNG (for emoji with chroma key processing).

    Args:
        image_data: Raw image bytes.
        prefix: Filename prefix.
        output_dir: Directory to save into (must be provided).

    Raises:
        ValueError: If output_dir is None.
    """
    if output_dir is None:
        raise ValueError("output_dir must be provided")
    out_dir = ensure_output_dir(output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    filename = f"{prefix}_{timestamp}_{short_id}.png"
    filepath = out_dir / filename
    filepath.write_bytes(image_data)
    return str(filepath)
