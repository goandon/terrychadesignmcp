# Terry Character Design MCP Server

An MCP server that generates consistent character reference image sets using Google's Nano Banana models (Vertex AI). Designed for maintaining visual consistency across video/image production pipelines.

## What's New in v0.4.0

- **Output modes**: `basic` (3-shot) and `face_angles` (3-shot) presets for faster generation
- **Camera presets**: Photorealistic (portrait, fashion, street, editorial, selfie) and animation (anime_standard, anime_dramatic, chibi, game_art, webtoon) presets
- **Character profiles**: YAML-based IP management with 5 CRUD tools and built-in Siwol/Claudie profiles
- **Product try-on**: `suggest_outfits` + `try_on_product` tools for fashion catalog integration
- **Design history DB**: Auto-recording of all generations with concept/series organization, ratings, search
- **19 total tools** (up from 8 in v0.3.1)

## Features

- **Output modes**: Preset shot selections (`full_sheet`, `basic`, `face_angles`) for flexible generation scope
- **Camera presets**: 10 presets covering photorealistic and animation styles
- **Character profiles**: YAML-based profiles for IP management and design consistency
- **Product try-on**: Generate character images wearing real products from a catalog
- **Design history**: Auto-recording of all generations with search, ratings, and concept grouping
- **7-angle reference sheet**: Full body (front, left, right, back) + Face close-up (left, front, right)
- **Composite sheet**: Auto-generates a single combined reference image from all shots
- **Anchor-based consistency**: First image serves as visual reference for all subsequent shots
- **Rich character inputs**: Description, outfit, hair, accessories, makeup, distinguishing features
- **Multiple art styles**: Anime, realistic, 3D render, watercolor, concept art, and more
- **Additional poses**: Generate custom poses/scenes using existing character references
- **Pose sample sheet**: Pre-defined pose categories (daily life, action, emotion, social) with auto grid composite
- **SD chat emoji**: Generate chibi/SD character emoji stickers for Telegram, Discord, LINE, KakaoTalk, Slack, WhatsApp
- **Prompt dictionary**: Curated reference vocabulary for character design prompts (13 categories)
- **Clean image output**: Anti-overlay prompting prevents text labels, color swatches, and annotation insets
- **Safety filter retry**: Automatic retry with softened prompts when safety filters block generation
- **Cost estimation**: Pre-generation cost calculator for budgeting API expenses

## Installation

```bash
pip install -r requirements.txt
```

### Requirements

- Python 3.10+
- Google Cloud project with Vertex AI enabled (or Gemini API key)
- `fastmcp>=2.0.0`, `google-genai>=1.0.0`, `Pillow>=10.0.0`, `PyYAML>=6.0`

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
        "TERRYCHA_DESIGN_OUTPUT_DIR": "/path/to/output",
        "TERRYCHA_DESIGN_PROFILES_DIR": "/path/to/profiles",
        "TERRYCHA_DESIGN_DB": "/path/to/design_history.db",
        "PRODUCT_CATALOG_DB": "/path/to/catalog.db"
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

## Tools (19 total)

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
| `output_mode` | "full_sheet" | Shot preset: "full_sheet", "basic", "face_angles" |
| `shots` | None | List of specific shot types (overrides output_mode) |
| `both_sides` | False | Add full_body_right for asymmetric features |
| `composite_sheet` | True | Auto-generate composite reference image |
| `max_retries` | 3 | Max retry attempts on safety filter block (0=no retry) |
| `on_block` | "retry" | Safety block behavior: "retry" (auto-retry) or "stop" (fail immediately) |
| `profile` | None | Character profile name to load (e.g. "siwol", "claudie") |
| `camera_preset` | None | Camera/style preset (e.g. "portrait", "fashion", "anime_standard") |
| `camera_override` | None | Dict to override specific preset keys (camera, lens, lighting) |
| `concept` | None | Concept name for design history tracking |

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

**Profile-driven generation:**
```
design_character(
    character_name="Siwol",
    profile="siwol",
    outfit_description="White oversized hoodie and denim shorts",
    concept="casual_spring"
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

### `generate_pose_sheet`

Generate a pose sample sheet with pre-defined poses at smaller size (512px default).

**Core inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reference_images` | list | Yes | 1-3 reference image paths from `design_character` output |
| `character_name` | str | Yes | Character name for folder naming |
| `style` | str | Yes | Art style for consistency |

**Pose selection:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `categories` | list | Pose categories: `"daily_life"`, `"action"`, `"emotion"`, `"social"` |
| `poses` | list | Cherry-pick individual poses (overrides categories) |

**Pose Categories:**
| Category | Poses (6 each) |
|----------|---------------|
| `daily_life` | sitting, walking, waving, reading, drinking, phone |
| `action` | running, jumping, fighting_stance, kicking, reaching, crouching |
| `emotion` | laughing, crying, thinking, surprised, angry, shy |
| `social` | peace_sign, thumbs_up, arms_crossed, blowing_kiss, salute, fist_pump |

Default: `["daily_life", "emotion"]` (12 poses).

**Example:**
```
generate_pose_sheet(
    reference_images=[
        "/path/to/Luna_20260302/full_body_front_....jpg",
        "/path/to/Luna_20260302/face_front_....jpg"
    ],
    character_name="Luna",
    style="anime",
    categories=["daily_life", "social"],
    temperature=0.6,
    seed=42
)
```

**Pose Grid Layout:**
```
+----------+----------+----------+----------+
| sitting  | walking  | waving   | reading  |
+----------+----------+----------+----------+
| drinking | phone    | peace    | thumbs   |
+----------+----------+----------+----------+
| arms_x   | kiss     | salute   | fist     |
+----------+----------+----------+----------+
  labels     labels     labels     labels
```

### `generate_chat_emoji`

Generate SD/chibi character chat emoji stickers with platform-specific output.

**Core inputs:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `reference_images` | list | Yes | 1-3 reference image paths from `design_character` output |
| `character_name` | str | Yes | Character name for folder naming |

**Expression selection:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `expression_set` | str | `"basic_16"` (default) or `"reaction_8"` |
| `expressions` | list | Cherry-pick individual expressions (overrides set) |

**Expression Sets:**
| Set | Count | Expressions |
|-----|-------|-------------|
| `basic_16` | 16 | happy, sad, angry, surprised, love, thumbs_up, thinking, sleeping, crying, laughing, wink, embarrassed, cool, confused, excited, tired |
| `reaction_8` | 8 | ok, no, please, cheers, sorry, thank_you, fighting, heart |

**Platform options:**
| Platform | Size | Format | Max Size |
|----------|------|--------|----------|
| `telegram` | 512x512 | PNG | 512 KB |
| `discord` | 128x128 | PNG | 256 KB |
| `line` | 370x320 | PNG | 1 MB |
| `kakaotalk` | 360x360 | PNG | 1 MB |
| `slack` | 128x128 | PNG | 128 KB |
| `whatsapp` | 512x512 | WebP | 100 KB |
| `universal` | 512x512 | PNG | None |

**Example:**
```
generate_chat_emoji(
    reference_images=[
        "/path/to/Luna_20260302/full_body_front_....jpg",
        "/path/to/Luna_20260302/face_front_....jpg"
    ],
    character_name="Luna",
    expression_set="basic_16",
    platform="telegram",
    style="anime",
    temperature=0.6,
    seed=42
)
```

### `get_prompt_dictionary`

Get curated descriptive phrases organized by category for building character design prompts.

**Categories (13):** body_types, facial_features, hair_styles, clothing, expressions, poses, art_styles, lighting, camera_angles, color_palettes, accessories, age_descriptors, backgrounds

```
# Get category index
get_prompt_dictionary()

# Get specific category
get_prompt_dictionary(category="hair_styles")
```

See [prompt_dictionary.md](prompt_dictionary.md) for the full human-readable reference.

### `estimate_generation_cost`

Estimate generation cost before running a tool. Calculates image count, cost per image, and worst-case cost (if all retries are used).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tool` | str | Yes | Tool name: "design_character", "add_character_pose", "generate_pose_sheet", "generate_chat_emoji" |
| `model` | str | No | "flash" (default) or "pro" |
| `image_size` | str | No | Target image size (default: "1K") |
| `shots` | list | No | (design_character) Custom shot list |
| `both_sides` | bool | No | (design_character) Include full_body_right |
| `categories` | list | No | (generate_pose_sheet) Pose categories |
| `poses` | list | No | (generate_pose_sheet) Individual pose keys |
| `expression_set` | str | No | (generate_chat_emoji) Expression set key |
| `expressions` | list | No | (generate_chat_emoji) Individual expression keys |
| `max_retries` | int | No | Max retries for worst-case estimate (default: 3) |

**Example:**
```
estimate_generation_cost(
    tool="generate_chat_emoji",
    model="pro",
    expression_set="basic_16"
)
# Returns: 16 images, ~$2.14, worst case ~$8.58
```

**Approximate pricing (USD per image):**

| Model | 512px | 1K | 2K | 4K |
|-------|-------|-----|-----|-----|
| Flash | $0.039 | $0.039 | $0.039 | $0.039 |
| Pro | - | $0.134 | $0.134 | $0.240 |

### `list_character_sheets`

List generated character reference sheets with image counts.

### `get_design_options`

Get all supported styles, shot types, output modes, camera presets, model parameters, pose categories, emoji expression sets, platform specs, and recommended settings.

---

## Output Modes

The `output_mode` parameter in `design_character` selects a preset shot group:

| Mode | Shots | Description |
|------|-------|-------------|
| `full_sheet` | 6 | Default. face_front + face_left + face_right + full_body_front + full_body_left + full_body_back. Produces full composite sheet. |
| `basic` | 3 | face_front + face_left + full_body_front. Faster/cheaper for quick drafts. Produces composite row. |
| `face_angles` | 3 | face_front + face_left + face_right. Face-only coverage. Produces composite row. |

When `shots` is explicitly provided, it overrides `output_mode`.

**Example (quick draft):**
```
design_character(
    character_name="Luna",
    ...,
    output_mode="basic",
    image_size="1K"
)
```

---

## Camera Presets

Use the `camera_preset` parameter in `design_character` to apply a photographic or animation-style camera configuration. Use `camera_override` to adjust individual keys.

### Photorealistic Presets

| Preset | Style |
|--------|-------|
| `portrait` | Classic headshot/beauty portrait lighting |
| `fashion` | Editorial fashion photography |
| `street` | Natural light street photography |
| `editorial` | Magazine editorial style |
| `selfie` | Casual smartphone self-portrait |

### Animation Presets

| Preset | Style |
|--------|-------|
| `anime_standard` | Standard anime visual style |
| `anime_dramatic` | High-contrast dramatic anime framing |
| `chibi` | Super-deformed chibi style |
| `game_art` | RPG/game portrait style |
| `webtoon` | Korean webtoon visual style |

**Example:**
```
design_character(
    character_name="Luna",
    ...,
    camera_preset="fashion",
    camera_override={"lighting": "golden hour backlight"}
)
```

Call `get_design_options()` to see the full preset configuration for each key.

---

## Character Profiles

Profiles store complete character definitions in YAML files. Once created, pass the profile name to `design_character(profile="name")` to auto-fill appearance, style, and generation defaults. Explicit parameters always override profile values.

### Profile CRUD Tools

| Tool | Description |
|------|-------------|
| `create_character_profile` | Create a new YAML profile |
| `get_character_profile` | Load and display a profile by name |
| `update_character_profile` | Patch specific fields in an existing profile |
| `delete_character_profile` | Remove a profile (requires `confirm=True`) |
| `list_character_profiles` | List all available profiles |

### Built-in Profiles

| Profile | Description |
|---------|-------------|
| `siwol` | Black wavy hair, blue eyes, beauty mark, semi-realistic anime style |
| `claudie` | Blonde ponytail, blue eyes, freckles, semi-realistic anime style |

### Profile YAML Structure

```yaml
name: luna
appearance:
  character_description: "Young East Asian woman, fair skin, almond-shaped brown eyes"
  hair_description: "Long straight black hair, blunt bangs"
  distinguishing_features: "Small beauty mark under left eye"
style_preferences:
  default_style: "anime"
  camera_preset: "anime_standard"
generation_defaults:
  temperature: 0.6
  seed: 42
  image_size: "2K"
  output_mode: "full_sheet"
```

### Profile-based generation

```
# Auto-fill all appearance/style defaults from profile
design_character(
    character_name="Siwol",
    profile="siwol",
    outfit_description="White tank top and denim mini skirt",
    concept="summer_casual"
)
```

Profiles directory defaults to `profiles/` inside the output directory. Override with `TERRYCHA_DESIGN_PROFILES_DIR`.

---

## Product Try-On

Requires a product catalog SQLite database (set via `PRODUCT_CATALOG_DB` env var, compatible with the Atelier fashion commerce pipeline).

### `suggest_outfits`

Propose 3 outfit combinations from the catalog based on style direction and character profile.

| Parameter | Type | Description |
|-----------|------|-------------|
| `style_direction` | str | Styling direction (e.g. "casual summer", "office chic") |
| `character_name` | str | Character name for context |
| `profile` | str | Character profile to match styling to |
| `product_ids` | list | Pre-select specific product IDs |
| `product_query` | str | Free-text search across catalog |

**Example:**
```
suggest_outfits(
    style_direction="casual summer street style",
    character_name="Siwol",
    profile="siwol"
)
# Returns: 3 outfit proposals with product IDs, names, and descriptions
```

### `try_on_product`

Generate a character image wearing a specific product from the catalog using reference images.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `character_name` | str | Yes | Character name |
| `reference_images` | list | Yes | Character reference images |
| `product_id` | str | Yes* | Product ID from catalog |
| `product_ids` | list | No | Multiple products for an outfit |
| `product_query` | str | No | Text search to auto-select product |
| `style` | str | No | Override art style |
| `camera_preset` | str | No | Camera/style preset |
| `concept` | str | No | Concept name for history tracking |

*At least one of `product_id`, `product_ids`, or `product_query` is required.

**Example:**
```
try_on_product(
    character_name="Siwol",
    reference_images=["/path/to/Siwol_20260316/face_front_....jpg"],
    product_id="MUS-12345",
    camera_preset="street"
)
```

---

## Design History DB

All generations are automatically recorded in a SQLite database when `TERRYCHA_DESIGN_DB` is set. Records include character name, prompt snapshot, output paths, model settings, and optional ratings.

### Concepts

Concepts group related generations into named series (e.g. "summer_lookbook", "seasonal_emoji_set").

### History Tools

| Tool | Description |
|------|-------------|
| `create_concept` | Create a named concept/series for organizing generations |
| `list_concepts` | List all concepts with generation counts |
| `search_generations` | Search history by character, concept, date range, or rating |
| `rate_generation` | Assign a 1-5 star rating and optional notes to a generation |

**Example workflow:**
```
# 1. Create a concept for a campaign
create_concept(name="spring_2026", description="Spring collection lookbook")

# 2. Generate with concept tracking
design_character(
    character_name="Siwol",
    profile="siwol",
    outfit_description="Floral sundress",
    concept="spring_2026"
)

# 3. Search and rate
search_generations(character="Siwol", concept="spring_2026")
rate_generation(generation_id="...", rating=5, notes="Hero shot for campaign")
```

---

## Shot Types

### Output Mode: `full_sheet` (default, 6 shots)

| Shot | Aspect Ratio | Description |
|------|-------------|-------------|
| `full_body_front` | 3:4 | **Anchor image** - generated first |
| `full_body_left` | 3:4 | Left profile, full body |
| `full_body_back` | 3:4 | Back of outfit and hair |
| `face_left` | 1:1 | Face close-up, left profile |
| `face_front` | 1:1 | Face close-up, front |
| `face_right` | 1:1 | Face close-up, right profile |

### Output Mode: `basic` (3 shots)

| Shot | Description |
|------|-------------|
| `face_front` | Face close-up, front |
| `face_left` | Face close-up, left profile |
| `full_body_front` | Full body front view (anchor) |

### Output Mode: `face_angles` (3 shots)

| Shot | Description |
|------|-------------|
| `face_front` | Face close-up, front |
| `face_left` | Face close-up, left profile |
| `face_right` | Face close-up, right profile |

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

`basic` and `face_angles` modes produce a horizontal composite row instead.

## Output Structure

```
~/terrycha_design_output/
+-- Luna_20260302_143052/                       <-- design_character
|   +-- full_body_front_20260302_143052_a1b2c3.jpg
|   +-- full_body_left_20260302_143058_d4e5f6.jpg
|   +-- full_body_back_20260302_143101_g7h8i9.jpg
|   +-- face_left_20260302_143104_j0k1l2.jpg
|   +-- face_front_20260302_143107_m3n4o5.jpg
|   +-- face_right_20260302_143110_p6q7r8.jpg
|   +-- composite_sheet_20260302_143112.jpg
+-- Luna_poses_20260302_150000/                 <-- generate_pose_sheet
|   +-- pose_sitting_20260302_150001_a1b2c3.jpg
|   +-- pose_walking_20260302_150005_d4e5f6.jpg
|   +-- ...
|   +-- pose_sheet_20260302_150030.jpg          <-- grid composite
+-- Luna_emoji_20260302_160000/                 <-- generate_chat_emoji
|   +-- emoji_happy_20260302_160001_a1b2c3_raw.jpg
|   +-- emoji_happy_20260302_160001_d4e5f6.png  <-- platform-sized
|   +-- ...
|   +-- emoji_preview_sheet_20260302_160100.jpg  <-- preview grid
+-- profiles/                                   <-- character profiles
|   +-- siwol.yaml
|   +-- claudie.yaml
+-- design_history.db                           <-- design history DB
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TERRYCHA_DESIGN_OUTPUT_DIR` | `~/terrycha_design_output` | Output directory |
| `TERRYCHA_DESIGN_DELAY` | `1.0` | Delay between shots (seconds) |
| `TERRYCHA_DESIGN_PROFILES_DIR` | `<output_dir>/profiles` | Character profiles directory |
| `TERRYCHA_DESIGN_DB` | (disabled) | Path to design history SQLite database |
| `PRODUCT_CATALOG_DB` | (disabled) | Path to product catalog SQLite database |
| `GOOGLE_CLOUD_PROJECT` | | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | `global` | GCP region |
| `GOOGLE_GENAI_USE_VERTEXAI` | `true` | Use Vertex AI auth |
| `GEMINI_API_KEY` | | API key (non-Vertex mode) |

## Clean Image Output (Anti-Overlay)

All prompt templates include `NO_OVERLAY_INSTRUCTION` to prevent AI models from rendering unwanted visual elements on generated images:

- Text labels and annotations (e.g., "Normal human ears", "Wavy hair")
- Color palette swatches
- Detail inset/zoom boxes
- Arrows or callout graphics

This is applied automatically to all generation tools (`design_character`, `add_character_pose`, `generate_pose_sheet`, `generate_chat_emoji`). No user configuration needed.

## Safety Filter Retry

All generation tools include automatic retry on safety filter blocks:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_retries` | 3 | Max retry attempts per image (0 = no retry) |
| `on_block` | "retry" | `"retry"` = auto-retry with softened prompt, `"stop"` = fail immediately |

When a safety filter blocks generation:
- **retry mode**: Automatically appends softening phrases to the prompt and retries (up to `max_retries`)
- **stop mode**: Fails immediately with a clear error message

Use `estimate_generation_cost` to check worst-case costs (all retries used) before running.

## Tips for Best Consistency

1. **Use a fixed seed** across all shots for maximum reproducibility
2. **Lower temperature** (0.5-0.8) produces more consistent results
3. **Monotone backgrounds** yield cleaner reference sheets
4. **Be specific** in descriptions -- include colors, materials, patterns
5. **Separate hair/accessories/makeup** into dedicated fields rather than stuffing everything into character_description
6. **Use "pro" model** for production-quality sheets, "flash" for rapid iteration
7. **Use `both_sides=True`** when accessories or features are asymmetric (e.g., earring on one ear)
8. **Use `get_prompt_dictionary()`** for curated reference phrases when building descriptions
9. **Use `generate_pose_sheet`** after `design_character` to quickly generate diverse pose variations
10. **Use `generate_chat_emoji`** to create platform-ready chat stickers from your character
11. **Use `estimate_generation_cost`** before large batch operations to budget API costs
12. **Set `on_block="stop"`** during testing to fail fast instead of wasting retries
13. **Avoid label-like descriptions** — use "has freckles on nose" instead of "Distinguishing features: freckles" to prevent text overlay
14. **Use `output_mode="basic"`** for quick drafts before committing to a full 6-shot sheet
15. **Use character profiles** to avoid repeating appearance descriptions across sessions
16. **Use `create_concept`** to group related generations into named campaigns or series
17. **Use `suggest_outfits`** before `try_on_product` to explore catalog options first

## License

MIT

## Author

Terry.Kim <goandonh@gmail.com>
Co-Author: Claudie
