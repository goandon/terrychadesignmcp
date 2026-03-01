# Terry Character Design MCP Server

An MCP server that generates consistent character reference image sets using Google's Nano Banana models (Vertex AI). Designed for maintaining visual consistency across video/image production pipelines.

## Features

- **7-angle reference sheet**: Full body (front, left, right, back) + Face close-up (left, front, right)
- **Composite sheet**: Auto-generates a single combined reference image from all shots
- **Anchor-based consistency**: First image serves as visual reference for all subsequent shots
- **Rich character inputs**: Description, outfit, hair, accessories, makeup, distinguishing features
- **Multiple art styles**: Anime, realistic, 3D render, watercolor, concept art, and more
- **Additional poses**: Generate custom poses/scenes using existing character references

## Installation

```bash
pip install -r requirements.txt
```

### Requirements

- Python 3.10+
- Google Cloud project with Vertex AI enabled (or Gemini API key)
- `fastmcp>=2.0.0`, `google-genai>=1.0.0`, `Pillow>=10.0.0`

## Configuration

### Claude Code (`~/.claude/settings.json`)

```json
{
  "mcpServers": {
    "terrycha-design": {
      "command": "python3",
      "args": ["/path/to/terrychadesignmcp/server.py"],
      "env": {
        "GOOGLE_CLOUD_PROJECT": "your-project-id",
        "GOOGLE_CLOUD_LOCATION": "global",
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "TERRYCHA_DESIGN_OUTPUT_DIR": "/path/to/output"
      }
    }
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "terrycha-design": {
      "command": "python3",
      "args": ["/path/to/terrychadesignmcp/server.py"],
      "env": {
        "GOOGLE_CLOUD_PROJECT": "your-project-id",
        "GOOGLE_GENAI_USE_VERTEXAI": "true"
      }
    }
  }
}
```

### Gemini API Key Mode

Set `GOOGLE_GENAI_USE_VERTEXAI=false` and provide `GEMINI_API_KEY` instead.

## Tools

### `design_character`

Generate a complete character reference sheet (6 shots default, 7 with `both_sides=True`).

**Core inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `character_name` | str | Yes | Character name (folder naming) |
| `character_description` | str | Yes | Physical appearance details |
| `style` | str | Yes | Art style (anime, realistic, etc.) |
| `outfit_description` | str | Yes | Clothing and footwear |

**Extended inputs:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `hair_description` | str | Hair length, style, color, bangs |
| `accessories` | str | Glasses, earrings, necklace, hat, watch |
| `makeup_description` | str | Lipstick, eyeshadow, eyeliner, blush |
| `distinguishing_features` | str | Moles, scars, freckles, tattoos |
| `expression` | str | Facial expression (default: neutral) |
| `age_range` | str | child, teen, young adult, adult, elderly |
| `body_type` | str | slim, average, athletic, curvy, muscular |
| `background_description` | str | Background (default: neutral gray) |
| `reference_images` | list | Reference image paths for guidance |
| `color_palette` | str | Overall color palette hint |

**Generation options:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `model` | "flash" | "flash" or "pro" |
| `image_size` | "1K" | "512px", "1K", "2K", "4K" |
| `temperature` | None | 0.0-2.0 (recommend 0.5-0.8) |
| `seed` | None | Fixed seed for reproducibility |
| `shots` | 6 default | List of specific shot types |
| `both_sides` | False | Add full_body_right for asymmetric features |
| `composite_sheet` | True | Auto-generate composite reference image |

**Example:**
```
design_character(
    character_name="Luna",
    character_description="A young East Asian woman with fair skin, almond-shaped brown eyes, high cheekbones",
    style="anime",
    outfit_description="White sailor uniform with navy blue collar, pleated navy skirt, brown loafers",
    hair_description="Long straight black hair reaching mid-back, blunt bangs across forehead",
    accessories="Small silver stud earrings, thin red ribbon tied in hair",
    makeup_description="Natural look with soft pink lip gloss, subtle mascara",
    distinguishing_features="Small beauty mark under left eye",
    expression="gentle smile",
    age_range="teen",
    body_type="slim",
    temperature=0.6,
    seed=42,
    image_size="2K"
)
```

### `add_character_pose`

Generate additional poses using existing reference images.

```
add_character_pose(
    prompt="The character sitting at a cafe table drinking tea, three-quarter angle, warm lighting",
    reference_images=[
        "/path/to/Luna_20260302/full_body_front_....jpg",
        "/path/to/Luna_20260302/face_front_....jpg"
    ],
    character_name="Luna",
    style="anime",
    aspect_ratio="16:9"
)
```

### `list_character_sheets`

List generated character reference sheets with image counts.

### `get_design_options`

Get all supported styles, shot types, model parameters, and recommended settings.

## Shot Types

### Default Shots (6)

| Shot | Aspect Ratio | Description |
|------|-------------|-------------|
| `full_body_front` | 3:4 | **Anchor image** - generated first |
| `full_body_left` | 3:4 | Left profile, full body |
| `full_body_back` | 3:4 | Back of outfit and hair |
| `face_left` | 1:1 | Face close-up, left profile |
| `face_front` | 1:1 | Face close-up, front |
| `face_right` | 1:1 | Face close-up, right profile |

### Optional Shots

| Shot | Aspect Ratio | Description |
|------|-------------|-------------|
| `full_body_right` | 3:4 | Right profile, full body (`both_sides=True`) |
| `upper_body` | 3:4 | Waist-up framing |

## Composite Sheet Layout

A single reference sheet image is auto-generated after all shots complete:

```
+------------+----------------+----------------+----------------+
| face_left  |                |                |                |
+------------+ full_body_front| full_body_left | full_body_back |
| face_front |    (3:4)       |    (3:4)       |    (3:4)       |
+------------+                |                |                |
| face_right |                |                |                |
+------------+----------------+----------------+----------------+
  labels         labels           labels           labels
```

With `both_sides=True`, `full_body_right` is added as a 4th body column.

## Output Structure

```
~/terrycha_design_output/
+-- Luna_20260302_143052/
    +-- full_body_front_20260302_143052_a1b2c3.jpg
    +-- full_body_left_20260302_143058_d4e5f6.jpg
    +-- full_body_back_20260302_143101_g7h8i9.jpg
    +-- face_left_20260302_143104_j0k1l2.jpg
    +-- face_front_20260302_143107_m3n4o5.jpg
    +-- face_right_20260302_143110_p6q7r8.jpg
    +-- composite_sheet_20260302_143112.jpg      <-- combined sheet
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TERRYCHA_DESIGN_OUTPUT_DIR` | `~/terrycha_design_output` | Output directory |
| `TERRYCHA_DESIGN_DELAY` | `1.0` | Delay between shots (seconds) |
| `GOOGLE_CLOUD_PROJECT` | | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | `global` | GCP region |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` | Use Vertex AI auth |
| `GEMINI_API_KEY` | | API key (non-Vertex mode) |

## Tips for Best Consistency

1. **Use a fixed seed** across all shots for maximum reproducibility
2. **Lower temperature** (0.5-0.8) produces more consistent results
3. **Monotone backgrounds** yield cleaner reference sheets
4. **Be specific** in descriptions -- include colors, materials, patterns
5. **Separate hair/accessories/makeup** into dedicated fields rather than stuffing everything into character_description
6. **Use "pro" model** for production-quality sheets, "flash" for rapid iteration
7. **Use `both_sides=True`** when accessories or features are asymmetric (e.g., earring on one ear)

## License

MIT

## Author

Terry.Kim <goandonh@gmail.com>
Co-Author: Claudie
