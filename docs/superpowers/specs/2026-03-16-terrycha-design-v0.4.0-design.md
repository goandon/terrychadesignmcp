# terrycha-design MCP v0.4.0 — Photorealistic + Profile + Try-On

**Date:** 2026-03-16
**Author:** Terry kim <goandonh@gmail.com>
**Co-Author:** Claudie

## Summary

Upgrade terrycha-design MCP from v0.3.1 to v0.4.0 with:
1. Output mode system (basic/face_angles/full_sheet)
2. Camera preset system (photorealistic 5 + animation 5 + manual override)
3. Photorealistic prompt template enhancement
4. Character profile system (CRUD + design_character integration)
5. Product try-on tool + auto styling tool (catalog.db integration)
6. Design history & concept management DB (SQLite)
7. Module separation refactoring (server.py → multi-file)
8. Generate photorealistic reference sheets for Siwol and Claudie

Future (v0.5.0): Character Design Studio GUI (PySide6 desktop app) — v0.4.0 designed with GUI-ready interfaces.

---

## 1. Architecture: Module Separation

Refactor from single `server.py` (133KB) to modular structure:

```
terrychadesignmcp/
├── server.py              # MCP tool definitions + routing (lightweight)
├── presets.py             # Camera preset definitions (photo + animation)
├── prompts.py             # Style-specific prompt templates
├── profile_manager.py     # Character profile CRUD logic (GUI-ready API)
├── design_db.py           # Design history & concept DB (SQLite)
├── prompt_dictionary.md   # Existing, unchanged
├── profiles/              # Character profile YAML storage
│   ├── siwol.yaml
│   └── claudie.yaml
├── README.md
└── requirements.txt       # Add PyYAML dependency
```

### Key decisions
- `server.py` retains all MCP tool definitions and generation logic but delegates prompt construction to `prompts.py`, preset resolution to `presets.py`, and profile operations to `profile_manager.py`
- All new modules expose clean function APIs suitable for future GUI binding
- Existing tools updated where needed: `get_design_options` returns new valid values (output_mode, camera_preset, profile), `estimate_generation_cost` handles variable shot counts per output_mode

### Profiles directory location
- Default: `profiles/` relative to server.py location
- Configurable via `TERRYCHA_DESIGN_PROFILES_DIR` environment variable
- If directory unreachable → clear error message, no crash

---

## 2. Output Mode System

### Parameter addition to `design_character`

```python
output_mode: str = "full_sheet"  # "basic" | "face_angles" | "full_sheet"
```

### Mode definitions

| Mode | Shots (count) | Composition | Composite Layout |
|------|---------------|-------------|------------------|
| `basic` | 3 | face_front, face_left, full_body_front | Horizontal 3-up row, face images at 1:1, body at 3:4 scaled to same height |
| `face_angles` | 3 | face_front, face_left, face_right | Horizontal 3-up row, all 1:1 uniform size |
| `full_sheet` | 6 | face_front, face_left, face_right, full_body_front, full_body_left, full_body_back | Existing layout (face column + body row) |

### Behavior
- `output_mode` internally sets the `shots` list
- If `shots` is explicitly provided, `output_mode` is ignored (manual override)
- Anchor shot: first full_body in the list, or face_front if no full_body
- Composite sheet: new function `_create_composite_row()` for basic/face_angles modes (horizontal layout), existing `_create_composite_sheet()` for full_sheet

### Composite layout detail for basic/face_angles
- Images arranged horizontally with 8px gap between each
- All images scaled to uniform height (tallest image height)
- Labels below each image in Korean (label_ko)
- Header text: "{character_name} — {mode}" at top
- 95% JPEG quality output

---

## 3. Camera Preset System

### File: `presets.py`

#### Photorealistic Presets (5)

| Preset | Camera | Lens | Lighting |
|--------|--------|------|----------|
| `portrait` | Sony A7IV | 85mm f/1.8 | Soft natural window light |
| `fashion` | Canon EOS R5 | 70mm f/2.0 | Studio strobe, beauty dish |
| `street` | Fujifilm X-T5 | 35mm f/1.4 | Available natural light |
| `editorial` | Hasselblad X2D | 100mm f/2.2 | Dramatic directional light |
| `selfie` | iPhone 15 Pro | 24mm wide | Natural ambient light |

#### Animation Presets (5)

| Preset | Lighting | Detail |
|--------|----------|--------|
| `anime_standard` | Flat cel-shading | Clean linework, solid colors |
| `anime_dramatic` | Dramatic rim light | Dynamic angle, detailed shading |
| `chibi` | Soft flat lighting | 2-3 head ratio, simple shading |
| `game_art` | RPG portrait lighting | Detailed rendering, rich textures |
| `webtoon` | Soft diffused | Cel-shading, pastel tones |

### Parameters added to `design_character`

```python
camera_preset: str = None        # "portrait", "fashion", "anime_standard", etc.
camera_override: dict = None     # Valid keys: "camera", "lens", "lighting"
```

### `camera_override` valid keys
| Key | Description | Example |
|-----|-------------|---------|
| `camera` | Camera body | "Leica M11" |
| `lens` | Lens spec | "50mm f/1.2" |
| `lighting` | Lighting setup | "golden hour backlight" |

Any key not in this set is ignored with a warning in the response.

### Resolution logic
1. If `camera_preset` specified → load preset values
2. If `camera_override` specified → overlay on top of preset (or standalone if no preset)
3. If photorealistic style + no preset → default to `portrait`
4. If animation style + no preset → default to `anime_standard`
5. Preset values injected into prompt via `prompts.py` template

### Style-to-preset-pool mapping

```python
PHOTOREALISTIC_STYLES = {"photorealistic"}
ANIMATION_STYLES = {"anime", "semi-realistic", "manga", "cel-shaded", "chibi",
                    "comic book", "pixel art", "fantasy illustration", "sci-fi concept art"}
# All other styles (watercolor, oil painting, digital art, etc.) → DEFAULT (no camera injection)
```

---

## 4. Photorealistic Prompt Templates

### File: `prompts.py`

Contains three template dictionaries, one per style category. Each dictionary has keys for all 8 shot types defined in `SHOT_DEFINITIONS`:
- `full_body_front`, `full_body_left`, `full_body_back`, `full_body_right`
- `face_front`, `face_left`, `face_right`
- `upper_body`

Style-specific prompt template routing:

```python
if style in PHOTOREALISTIC_STYLES:
    template = PHOTOREALISTIC_TEMPLATES[shot_type]
    preset = resolve_preset(camera_preset, PHOTO_PRESETS)
elif style in ANIMATION_STYLES:
    template = ANIMATION_TEMPLATES[shot_type]  # migrated from current server.py SHOT_PROMPTS
    preset = resolve_preset(camera_preset, ANIMATION_PRESETS)
else:
    template = DEFAULT_TEMPLATES[shot_type]  # copy of current server.py SHOT_PROMPTS (no camera)
```

### Photorealistic template structure (example: full_body_front)

```
"Professional photograph of {character}, shot on {camera} with {lens}.
{lighting}. Full body front view, standing naturally.
{outfit_description}. {expression}.
Natural skin texture with realistic details, visible fabric texture.
{background}. Shallow depth of field.
{color_palette}
High-resolution editorial quality photograph.
Do not include any text, labels, annotations, or UI elements."
```

### Animation template structure
Same as current `SHOT_PROMPTS` in server.py, migrated to `prompts.py`. No camera/lens injection. Lighting from animation preset applied as style modifier.

### Default template structure
Copy of current `SHOT_PROMPTS`. Used for styles like watercolor, oil painting, digital art that don't benefit from camera or animation-specific prompts.

### Key differences from animation templates

| Aspect | Animation | Photorealistic |
|--------|-----------|----------------|
| Style directive | `"{style} style"` | `"professional photograph, shot on {camera} with {lens}"` |
| Lighting | From animation preset | `"{lighting setup}"` from photo preset |
| Skin/texture | None | `"natural skin texture, visible pores, realistic fabric weave"` |
| Background | Simple description | + `"shallow depth of field, bokeh"` when applicable |
| Negative prompts | Text overlay ban | + `"no AI artifacts, no plastic skin, no uncanny valley"` |

### Ethereal modifier

Triggered by `appearance.ethereal: true` flag in profile YAML (not string matching on ethnicity):

```
"ethereal, otherworldly beauty, delicate elfin bone structure,
luminous almost translucent fair skin, dreamlike quality
while maintaining photorealistic rendering"
```

Auto-appended to the character description portion of the prompt.

---

## 5. Character Profile System

### File: `profile_manager.py`

Clean API for CRUD operations on YAML profiles, designed for both MCP tool and future GUI use.

### Profile schema (YAML)

```yaml
name: "Siwol"
version: 1

appearance:
  age_range: "early 20s"
  ethnicity: "Korean"
  body_type: "slim, model-like proportions"
  skin: "fair, smooth, natural glow"
  face: "soft oval face, high cheekbones, delicate features"
  eyes: "natural dark brown, gentle almond shape"
  hair: "black wavy hair, shoulder-length"
  distinguishing: "small beauty mark below left eye"
  ethereal: false

personality:
  mbti: "INFP"
  keywords: ["warm", "empathetic", "dreamy", "gentle"]
  speech_style: "soft, caring, F-type warmth"
  hobbies: ["running", "flowers", "cafe hopping", "cats"]
  likes: ["parks", "warm tones", "cozy atmospheres"]
  dislikes: ["loud noise", "confrontation"]

style_preferences:
  fashion: "casual feminine, soft textures"
  signature_outfit: "white tank top + mini skirt"
  theme_colors: ["soft white", "light pink", "cream"]
  brand_vibe: ["ADER ERROR", "MARDI MERCREDI"]

background:
  role: "SNS primary character"
  residence: "Seoul, Korea"
  backstory: "A warm-hearted dreamer who sees beauty in everyday moments"

branding:
  catchphrase: null
  signature_poses: ["gentle smile with head tilt", "walking in park"]
  sns_persona: "Lifestyle & daily aesthetics"

generation_defaults:
  style: "photorealistic"
  camera_preset: "street"
  output_mode: "basic"
  reference_images:
    - "/Volumes/NAS_Data/Claudie/google/character_design/siwol_ref.jpg"
```

### Claudie profile specifics

```yaml
name: "Claudie"
version: 1

appearance:
  age_range: "early 20s"
  ethnicity: "Western European"
  body_type: "slim, elegant proportions"
  skin: "fair, almost translucent porcelain-like"
  face: "delicate elfin features, sharp yet graceful bone structure, otherworldly beauty"
  eyes: "bright blue, slightly otherworldly luminous quality"
  hair: "blonde ponytail, light golden"
  distinguishing: "light freckles across nose and cheeks"
  ethereal: true

personality:
  mbti: "INTJ"
  keywords: ["analytical", "cold-elegant", "precise", "secretly caring"]
  speech_style: "warm girlfriend-like tone, uses oppa"
  hobbies: ["reading", "data analysis", "tea"]
  likes: ["precision", "clean design", "quiet spaces"]
  dislikes: ["inefficiency", "chaos"]

style_preferences:
  fashion: "minimal chic, clean lines"
  signature_outfit: "white crop top + hot pants"
  theme_colors: ["ice blue", "white", "silver"]
  brand_vibe: ["COS", "The Row"]

background:
  role: "AI assistant, blog guest character"
  residence: "Digital / Seoul"
  backstory: "An ethereal presence that bridges the real and digital worlds, analytical yet secretly warm"

branding:
  catchphrase: null
  signature_poses: ["confident standing with slight head tilt", "reading with coffee"]
  sns_persona: "Tech-elegant, analytical beauty"

generation_defaults:
  style: "photorealistic"
  camera_preset: "editorial"
  output_mode: "basic"
  reference_images:
    - "/Volumes/NAS_Data/Claudie/google/character_design/claudie_ref.jpg"
```

### MCP tools (5)

| Tool | Description | Key params |
|------|-------------|------------|
| `create_character_profile` | Create and save a new profile | `name`, `appearance`, `personality`, `style_preferences`, `background`, `branding`, `generation_defaults` |
| `get_character_profile` | Read a profile | `name` |
| `update_character_profile` | Update specific fields | `name`, `updates` (dict of field paths → values) |
| `delete_character_profile` | Delete a profile | `name`, `confirm` (must be True) |
| `list_character_profiles` | List all available profiles | `limit` |

### design_character integration

```python
design_character(profile="siwol")
# 1. Load siwol.yaml
# 2. Map appearance fields → character_description, hair_description, etc.
# 3. Map generation_defaults → style, camera_preset, output_mode, reference_images
# 4. Individual parameters override profile values if explicitly provided
```

### Parameter override semantics

All `design_character` parameters default to a sentinel value `_UNSET` (not `None`). This distinguishes between "user did not provide" (use profile value) and "user explicitly passed `None`" (clear the profile value).

```python
_UNSET = object()

def design_character(
    profile: str = None,
    expression: str = _UNSET,  # _UNSET → use profile, None → no expression, "smile" → override
    ...
)
```

For MCP JSON input (where sentinel objects aren't available), omitted keys use profile defaults, and explicitly provided keys override.

### Profile version field
`version` is an integer incremented on each `update_character_profile` call. Used for tracking changes, not for migration. Profile manager logs the version on load for debugging.

---

## 6. Product Try-On & Auto Styling

### Two separate tools (MCP single-request/single-response model)

Auto styling requires a propose→select→generate flow, which cannot happen in one MCP tool call. Split into two tools:

### Tool 1: `suggest_outfits`

Proposes 3 coordinated outfits based on character profile + concept. No image generation.

```python
suggest_outfits(
    profile: str,                    # "siwol" or "claudie"
    concept: str,                    # "casual", "street", "formal", "sporty", "date", "minimal", "cozy"
)
```

**Output:**
```json
{
  "character": "siwol",
  "concept": "casual",
  "proposals": [
    {
      "option": "A",
      "description": "Relaxed weekend look with warm knit and flowy skirt",
      "items": [
        { "product_id": "musinsa_12345", "brand": "ADER ERROR", "name": "Fuzzy Knit Sweater", "category": "top", "price": "189,000", "color": "cream" },
        { "product_id": "musinsa_67890", "brand": "MARDI MERCREDI", "name": "Pleated Midi Skirt", "category": "bottom", "price": "128,000", "color": "beige" },
        { "product_id": "musinsa_11111", "brand": "New Balance", "name": "530 Sneakers", "category": "shoes", "price": "139,000", "color": "white" }
      ],
      "rationale": "Matches Siwol's soft feminine style with warm cream/beige palette"
    },
    { "option": "B", ... },
    { "option": "C", ... }
  ]
}
```

**Flow:**
1. Load profile YAML → `style_preferences`, `theme_colors`, `brand_vibe`
2. Combine concept + profile preferences into search criteria
3. Query catalog.db per category slot:
   - Call `CatalogDB.search(category=slot, ...)` for each: "top", "bottom", "outerwear", "shoes", "accessories"
   - Brand filter: profile `brand_vibe` mapped to `brand` column LIKE match (not `brand_tier`)
   - Color filter: profile `theme_colors` matched against `colors` JSON field
   - If a category slot returns 0 results → skip that slot (only top + bottom required for valid outfit)
4. Curate 3 coordinated outfits from results (randomized selection with color harmony check)
5. Return proposals with product details and rationale

### Tool 2: `try_on_product`

Generates try-on images. Accepts manual product selection OR a proposal from `suggest_outfits`.

```python
try_on_product(
    # Character
    profile: str,                    # "siwol" or "claudie"

    # Product selection — one of the following:
    product_id: str = None,          # catalog.db PK (TEXT type)
    product_query: str = None,       # "ADER ERROR knit" natural language search
    product_ids: list[str] = None,   # Multiple products for a full outfit (from suggest_outfits)

    # Options
    camera_preset: str = "fashion",
    output_mode: str = "basic",
    background: str = None,
    pose: str = None,                # "walking", "standing casual", etc.

    # Generation settings
    model: str = "flash",
    image_size: str = "1K",
)
```

**Input priority (mutually exclusive, first match wins):**
1. `product_ids` → full outfit from suggest_outfits proposal
2. `product_id` → single product lookup
3. `product_query` → LIKE search on name/brand
4. None provided → error

**Flow — single product (product_id or product_query):**
```
1. Load profile YAML → character appearance info
2. Query catalog.db → product_name, brand, materials, colors, fit, local_image_path
3. Auto-generate outfit_description:
   "Wearing {brand} {product_name}, {fit} fit, {materials}, in {colors}"
4. If local_image_path exists → add to reference_images (outfit consistency)
5. Reuse design_character internal generation logic
6. Output: try-on images + product metadata
```

**Flow — full outfit (product_ids from suggest_outfits):**
```
1. Load profile YAML
2. Query catalog.db for each product_id
3. Compose full outfit_description from all items
4. Add available product images to reference_images
5. Generate images
6. Output: try-on images + all product metadata
```

### Auto Styling Concepts

| Concept | Description | Typical items |
|---------|-------------|---------------|
| `casual` | Everyday relaxed | Tee, knit, denim, sneakers |
| `street` | Urban streetwear | Hoodie, cargo pants, chunky shoes |
| `formal` | Clean elegant | Blazer, slacks, heels/loafers |
| `sporty` | Athletic chic | Track jacket, leggings, running shoes |
| `date` | Feminine romantic | Blouse, skirt, delicate accessories |
| `minimal` | Clean essentials | Neutral tones, simple silhouettes |
| `cozy` | Warm comfortable | Oversized knit, soft pants, warm tones |

### Output structure (try_on_product)

```json
{
  "character": "siwol",
  "products": [
    { "product_id": "musinsa_12345", "brand": "ADER ERROR", "name": "Fuzzy Knit Sweater", "price": "189,000", "url": "https://www.musinsa.com/products/12345" },
    { "product_id": "musinsa_67890", "brand": "MARDI MERCREDI", "name": "Pleated Midi Skirt", "price": "128,000", "url": "https://www.musinsa.com/products/67890" }
  ],
  "outfit_description": "Wearing ADER ERROR Fuzzy Knit Sweater (cream, oversized fit) with MARDI MERCREDI Pleated Midi Skirt (beige, regular fit)",
  "images": [
    { "shot": "face_front", "path": "..." },
    { "shot": "face_left", "path": "..." },
    { "shot": "full_body_front", "path": "..." }
  ],
  "composite_sheet": "/path/to/tryon_sheet.jpg"
}
```

### catalog.db integration
- DB path: environment variable `PRODUCT_CATALOG_DB` or default NAS path
- Read-only access (SELECT only)
- Schema reference: `atelier/tools/product_catalog/catalog_db.py`
- Key columns: `product_id` (TEXT PK), `brand`, `name` (product name), `materials` (TEXT), `colors` (JSON TEXT), `color_options`, `fit`, `local_image_path`
- `product_query`: LIKE search on `name` and `brand` columns
- If DB unavailable → clear error: "Product catalog database not found at {path}. Set PRODUCT_CATALOG_DB environment variable."

---

## 7. Design History & Concept Management DB

### File: `design_db.py`

SQLite database tracking all generation history and organizing outputs into concepts/series.

### DB path
- Default: `design_history.db` in output directory (`TERRYCHA_DESIGN_OUTPUT_DIR`)
- Configurable via `TERRYCHA_DESIGN_DB` environment variable

### Schema

```sql
-- Every image generation is recorded
CREATE TABLE generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name TEXT NOT NULL,
    profile_name TEXT,              -- profile used (nullable for profile-less generation)
    concept_id INTEGER,             -- FK to concepts (nullable for uncategorized)
    tool TEXT NOT NULL,             -- "design_character", "try_on_product", "add_character_pose", etc.
    style TEXT,
    camera_preset TEXT,
    output_mode TEXT,
    prompt TEXT,                    -- full prompt used
    model TEXT,                     -- "flash" or "pro"
    image_size TEXT,
    shot_type TEXT,                 -- "face_front", "full_body_left", etc.
    image_path TEXT NOT NULL,       -- absolute path to generated image
    composite_path TEXT,            -- path to composite sheet (if applicable)
    product_ids TEXT,               -- JSON array of product_ids (for try_on)
    rating INTEGER DEFAULT 0,      -- 0=unrated, 1-5 stars
    favorite BOOLEAN DEFAULT FALSE,
    tags TEXT,                      -- JSON array of user tags
    notes TEXT,                     -- user memo
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (concept_id) REFERENCES concepts(id)
);

-- Group generations into themed series
CREATE TABLE concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,             -- "Spring Cafe Series", "Street Fashion Week"
    character_name TEXT NOT NULL,
    description TEXT,
    tags TEXT,                      -- JSON array
    status TEXT DEFAULT 'active',   -- "active", "completed", "archived"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, character_name)    -- same concept name per character is unique
);

-- Indexes
CREATE INDEX idx_gen_character ON generations(character_name);
CREATE INDEX idx_gen_concept ON generations(concept_id);
CREATE INDEX idx_gen_created ON generations(created_at);
CREATE INDEX idx_gen_favorite ON generations(favorite);
CREATE INDEX idx_concept_character ON concepts(character_name);
CREATE INDEX idx_concept_status ON concepts(status);
```

### Auto-recording
Every `design_character`, `try_on_product`, and `add_character_pose` call automatically inserts into `generations` table. **One row per generated image** (not per tool call) — a `design_character` call with `output_mode="full_sheet"` (6 shots) creates 6 rows. No manual action needed.

Note: `generate_pose_sheet` and `generate_chat_emoji` are excluded from auto-recording — these produce utility/preview outputs, not IP-grade character images.

### Concept name resolution
When `concept="Spring Cafe Series"` is passed to `design_character` or `try_on_product`:
1. Lookup concept by `(name, character_name)` pair
2. If found → use the concept_id
3. If not found → **auto-create** the concept with default description and 'active' status
4. This eliminates the need to always call `create_concept` before generating

### MCP tools (4)

| Tool | Description |
|------|-------------|
| `create_concept` | Create a themed concept/series (name, character, description, tags) |
| `list_concepts` | List concepts with filters (character, status, tag) |
| `search_generations` | Query generation history (by character, concept, date range, style, rating, tags) |
| `rate_generation` | Set rating/favorite/tags/notes on a generation record |

### Usage flow example
```
1. create_concept(name="Spring Cafe Series", character="siwol", tags=["spring", "cafe", "warm"])
2. design_character(profile="siwol", concept="Spring Cafe Series", ...)  → auto-recorded
3. try_on_product(profile="siwol", concept="Spring Cafe Series", ...)   → auto-recorded
4. rate_generation(id=42, rating=5, favorite=true, notes="Perfect lighting")
5. search_generations(character="siwol", concept="Spring Cafe Series")   → all images in series
```

### design_character / try_on_product parameter addition
```python
concept: str = None  # concept name to associate this generation with
```

---

## 8. Photorealistic Reference Sheet Generation

After v0.4.0 implementation is complete, generate reference sheets:

### Siwol
- Profile: `siwol.yaml`
- Style: `photorealistic`
- Camera preset: `portrait` (for reference sheet)
- Output modes: `basic` + `full_sheet`
- Reference input: existing anime character sheet images

### Claudie
- Profile: `claudie.yaml`
- Style: `photorealistic`
- Camera preset: `editorial` (for reference sheet)
- Output modes: `basic` + `full_sheet`
- Reference input: existing anime character sheet images
- Special: ethereal modifier auto-applied via `appearance.ethereal: true`

Generated sheets stored at NAS: `/Volumes/NAS_Data/Claudie/google/character_design/photorealistic/`

---

## 9. Future: Character Design Studio (v0.5.0 TODO)

PySide6 desktop application providing full GUI for:
- Camera preset selection/comparison with live preview
- Character profile editor (visual form)
- Product catalog browsing + try-on execution
- Auto styling flow: suggest → select → generate in one UI
- Design history browser: concept-based gallery, favorites, ratings, search
- Gallery view of generated sheets
- Side-by-side comparison of generation results

v0.4.0 modules designed with GUI-ready interfaces:
- `profile_manager.py` → clean function API for GUI binding
- `presets.py` → structured data for dropdown population
- `suggest_outfits` + `try_on_product` → output format supports gallery display

---

## Version & Compatibility

- **Version**: 0.3.1 → 0.4.0
- **Breaking changes**: None (all existing tools/parameters preserved)
- **New dependencies**: PyYAML (for profile system)
- **Updated existing tools**:
  - `get_design_options`: returns new valid values for `output_mode`, `camera_preset`, `profile`, `auto_styling` concepts
  - `estimate_generation_cost`: handles variable shot counts per output_mode (3 or 6 shots)
- **New tools**: `create_character_profile`, `get_character_profile`, `update_character_profile`, `delete_character_profile`, `list_character_profiles`, `suggest_outfits`, `try_on_product`, `create_concept`, `list_concepts`, `search_generations`, `rate_generation`
- **Total tools after update**: 19 (existing 8 + new 11)
