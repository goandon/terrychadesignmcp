# terrycha-design MCP v0.4.0 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade terrycha-design MCP from v0.3.1 to v0.4.0 with photorealistic prompts, camera presets, character profiles, product try-on, design history DB, and module separation.

**Architecture:** Extract prompt templates, camera presets, profile management, and design DB into separate modules (`prompts.py`, `presets.py`, `profile_manager.py`, `design_db.py`). `server.py` becomes a thin routing layer that delegates to these modules. All modules expose clean function APIs for future GUI binding (v0.5.0).

**Tech Stack:** Python 3.13, FastMCP, google-genai, Pillow, PyYAML, SQLite3 (stdlib)

**Spec:** `docs/superpowers/specs/2026-03-16-terrycha-design-v0.4.0-design.md`

**Existing codebase:** Single `server.py` (3371 lines) at `h:/Git/terrychadesignmcp/`

---

## Chunk 1: Foundation — presets.py + prompts.py + output_mode

Independent modules with no external dependencies beyond what exists. This chunk creates the data/template layer.

### Task 1: Create `presets.py` — Camera Preset Definitions

**Files:**
- Create: `h:/Git/terrychadesignmcp/presets.py`
- Create: `h:/Git/terrychadesignmcp/tests/test_presets.py`

- [ ] **Step 1: Write tests for preset system**

```python
# tests/test_presets.py
"""Tests for camera preset resolution system."""
import pytest
from presets import (
    PHOTO_PRESETS, ANIMATION_PRESETS,
    PHOTOREALISTIC_STYLES, ANIMATION_STYLES,
    resolve_preset, VALID_OVERRIDE_KEYS,
)


def test_photo_presets_have_required_keys():
    """Each photo preset must have camera, lens, lighting."""
    for name, preset in PHOTO_PRESETS.items():
        assert "camera" in preset, f"{name} missing 'camera'"
        assert "lens" in preset, f"{name} missing 'lens'"
        assert "lighting" in preset, f"{name} missing 'lighting'"


def test_animation_presets_have_required_keys():
    """Each animation preset must have lighting, detail."""
    for name, preset in ANIMATION_PRESETS.items():
        assert "lighting" in preset, f"{name} missing 'lighting'"
        assert "detail" in preset, f"{name} missing 'detail'"


def test_resolve_preset_photo():
    result = resolve_preset("portrait", "photorealistic")
    assert result["camera"] == "Sony A7IV"
    assert result["lens"] == "85mm f/1.8"


def test_resolve_preset_animation():
    result = resolve_preset("anime_standard", "anime")
    assert result["lighting"] == "Flat cel-shading"


def test_resolve_preset_default_for_photorealistic():
    """No preset + photorealistic style → default to portrait."""
    result = resolve_preset(None, "photorealistic")
    assert result == PHOTO_PRESETS["portrait"]


def test_resolve_preset_default_for_animation():
    """No preset + animation style → default to anime_standard."""
    result = resolve_preset(None, "anime")
    assert result == ANIMATION_PRESETS["anime_standard"]


def test_resolve_preset_default_style_returns_none():
    """No preset + non-photo/animation style → None (no camera injection)."""
    result = resolve_preset(None, "watercolor")
    assert result is None


def test_resolve_preset_with_override():
    result = resolve_preset("portrait", "photorealistic", override={"lens": "50mm f/1.2"})
    assert result["lens"] == "50mm f/1.2"
    assert result["camera"] == "Sony A7IV"  # not overridden


def test_resolve_preset_override_only():
    result = resolve_preset(None, "watercolor", override={"lighting": "golden hour"})
    assert result == {"lighting": "golden hour"}


def test_resolve_preset_invalid_override_key_ignored():
    result = resolve_preset("portrait", "photorealistic", override={"film_stock": "Kodak"})
    assert "film_stock" not in result


def test_resolve_preset_invalid_name_raises():
    with pytest.raises(ValueError, match="Unknown preset"):
        resolve_preset("nonexistent", "photorealistic")


def test_style_sets_no_overlap():
    """Photo and animation style sets must not overlap."""
    assert PHOTOREALISTIC_STYLES.isdisjoint(ANIMATION_STYLES)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_presets.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'presets'`

- [ ] **Step 3: Implement `presets.py`**

```python
# presets.py
"""Camera preset definitions for photorealistic and animation styles.

Author: Terry kim <goandonh@gmail.com>
Co-Author: Claudie
"""

from typing import Optional

# -- Style category sets ---------------------------------------------------

PHOTOREALISTIC_STYLES = {"photorealistic"}

ANIMATION_STYLES = {
    "anime", "semi-realistic", "manga", "cel-shaded", "chibi",
    "comic book", "pixel art", "fantasy illustration", "sci-fi concept art",
}

# -- Photorealistic camera presets -----------------------------------------

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

# -- Animation presets -----------------------------------------------------

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

# -- Valid override keys ---------------------------------------------------

VALID_OVERRIDE_KEYS = {"camera", "lens", "lighting"}

# -- All preset names for validation ---------------------------------------

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
        # Auto-detect based on style
        if style in PHOTOREALISTIC_STYLES:
            result = dict(PHOTO_PRESETS["portrait"])
        elif style in ANIMATION_STYLES:
            result = dict(ANIMATION_PRESETS["anime_standard"])
        # else: no preset for this style → result stays None

    # Apply overrides
    if override:
        if result is None:
            result = {}
        for key, value in override.items():
            if key in VALID_OVERRIDE_KEYS:
                result[key] = value
            # Invalid keys silently ignored (warning added at caller level)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_presets.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add presets.py tests/test_presets.py
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add camera preset system (presets.py)

Photo presets: portrait, fashion, street, editorial, selfie
Animation presets: anime_standard, anime_dramatic, chibi, game_art, webtoon
resolve_preset() with auto-detection and override support

Co-Authored-By: Claudie"
```

---

### Task 2: Create `prompts.py` — Style-Specific Prompt Templates

**Files:**
- Create: `h:/Git/terrychadesignmcp/prompts.py`
- Create: `h:/Git/terrychadesignmcp/tests/test_prompts.py`
- Read: `h:/Git/terrychadesignmcp/server.py:1441-1487` (existing `_build_character_prompt` and `SHOT_PROMPTS`)

- [ ] **Step 1: Read existing prompt templates from server.py**

Read `server.py` lines 138-530 (SHOT_DEFINITIONS, SHOT_PROMPTS, style constants) to understand the exact current format. These will be migrated to `prompts.py` as DEFAULT_TEMPLATES and ANIMATION_TEMPLATES.

- [ ] **Step 2: Write tests for prompt system**

```python
# tests/test_prompts.py
"""Tests for style-specific prompt template system."""
import pytest
from prompts import (
    PHOTOREALISTIC_TEMPLATES, ANIMATION_TEMPLATES, DEFAULT_TEMPLATES,
    ALL_SHOT_TYPES, build_prompt, ETHEREAL_MODIFIER,
)
from presets import PHOTO_PRESETS, ANIMATION_PRESETS


def test_all_template_dicts_have_all_shot_types():
    """Every template dict must have keys for all 8 shot types."""
    for name, templates in [
        ("PHOTOREALISTIC", PHOTOREALISTIC_TEMPLATES),
        ("ANIMATION", ANIMATION_TEMPLATES),
        ("DEFAULT", DEFAULT_TEMPLATES),
    ]:
        for shot in ALL_SHOT_TYPES:
            assert shot in templates, f"{name}_TEMPLATES missing '{shot}'"


def test_photorealistic_template_contains_camera_placeholders():
    tpl = PHOTOREALISTIC_TEMPLATES["full_body_front"]
    assert "{camera}" in tpl
    assert "{lens}" in tpl
    assert "{lighting}" in tpl


def test_animation_template_no_camera_placeholders():
    tpl = ANIMATION_TEMPLATES["full_body_front"]
    assert "{camera}" not in tpl
    assert "{lens}" not in tpl


def test_default_template_no_camera_placeholders():
    tpl = DEFAULT_TEMPLATES["full_body_front"]
    assert "{camera}" not in tpl


def test_build_prompt_photorealistic():
    result = build_prompt(
        shot_type="full_body_front",
        style="photorealistic",
        character="young woman, fair skin, blue eyes",
        outfit="white dress",
        expression="gentle smile",
        background="park bench",
        color_palette="warm tones",
        preset=PHOTO_PRESETS["portrait"],
        ethereal=False,
    )
    assert "Sony A7IV" in result
    assert "85mm f/1.8" in result
    assert "white dress" in result
    assert "natural skin texture" in result.lower() or "professional photograph" in result.lower()


def test_build_prompt_animation():
    result = build_prompt(
        shot_type="face_front",
        style="anime",
        character="pink-haired girl",
        outfit="school uniform",
        expression="happy",
        background="classroom",
        color_palette=None,
        preset=ANIMATION_PRESETS["anime_standard"],
        ethereal=False,
    )
    assert "anime" in result.lower() or "style" in result.lower()
    assert "Sony" not in result  # no camera


def test_build_prompt_default_style():
    result = build_prompt(
        shot_type="full_body_front",
        style="watercolor",
        character="woman in garden",
        outfit="floral dress",
        expression="peaceful",
        background="flower garden",
        color_palette=None,
        preset=None,
        ethereal=False,
    )
    assert "watercolor" in result.lower()
    assert "Sony" not in result


def test_build_prompt_ethereal_modifier():
    result = build_prompt(
        shot_type="face_front",
        style="photorealistic",
        character="blonde woman",
        outfit="white crop top",
        expression="neutral",
        background="studio",
        color_palette=None,
        preset=PHOTO_PRESETS["editorial"],
        ethereal=True,
    )
    assert "ethereal" in result.lower()
    assert "elfin" in result.lower()


def test_build_prompt_no_overlay_instruction():
    """All prompts must include the anti-overlay instruction."""
    result = build_prompt(
        shot_type="full_body_front",
        style="photorealistic",
        character="test",
        outfit="test",
        expression="neutral",
        background="white",
        color_palette=None,
        preset=PHOTO_PRESETS["portrait"],
        ethereal=False,
    )
    assert "do not" in result.lower() and "text" in result.lower()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'prompts'`

- [ ] **Step 4: Implement `prompts.py`**

Create `prompts.py` with:
1. `ALL_SHOT_TYPES` — list of all 8 shot type keys
2. `PHOTOREALISTIC_TEMPLATES` — dict of 8 templates with `{camera}`, `{lens}`, `{lighting}` placeholders
3. `ANIMATION_TEMPLATES` — migrated from current `SHOT_PROMPTS` in `server.py` (lines ~350-524)
4. `DEFAULT_TEMPLATES` — copy of `ANIMATION_TEMPLATES` without animation-specific modifiers
5. `ETHEREAL_MODIFIER` — string constant
6. `NO_OVERLAY_INSTRUCTION` — migrated from `server.py`
7. `build_prompt()` — routes to correct template, fills placeholders, appends ethereal/overlay instructions

Key implementation notes:
- Read `server.py` lines 350-524 to get exact `SHOT_PROMPTS` dict and migrate verbatim
- Photorealistic templates replace `"{style} style"` with `"professional photograph, shot on {camera} with {lens}"` and add skin/texture realism phrases
- `build_prompt()` signature:
  ```python
  def build_prompt(
      shot_type: str, style: str, character: str, outfit: str,
      expression: str, background: str, color_palette: str | None,
      preset: dict | None, ethereal: bool = False,
  ) -> str:
  ```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_prompts.py -v`
Expected: All 9 tests PASS

- [ ] **Step 6: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add prompts.py tests/test_prompts.py
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add style-specific prompt templates (prompts.py)

Photorealistic, animation, and default template sets for all 8 shot types.
build_prompt() with camera preset injection and ethereal modifier.
Migrated SHOT_PROMPTS from server.py.

Co-Authored-By: Claudie"
```

---

### Task 3: Add `output_mode` Support and `_create_composite_row()`

**Files:**
- Modify: `h:/Git/terrychadesignmcp/server.py` (add output_mode parameter, new composite function)
- Create: `h:/Git/terrychadesignmcp/tests/test_output_mode.py`

- [ ] **Step 1: Write tests for output mode shot list resolution**

```python
# tests/test_output_mode.py
"""Tests for output mode shot resolution and composite row creation."""
import pytest


# -- Shot resolution tests (logic to be added to server.py) --

OUTPUT_MODE_SHOTS = {
    "basic": ["face_front", "face_left", "full_body_front"],
    "face_angles": ["face_front", "face_left", "face_right"],
    "full_sheet": ["face_front", "face_left", "face_right",
                   "full_body_front", "full_body_left", "full_body_back"],
}

VALID_OUTPUT_MODES = set(OUTPUT_MODE_SHOTS.keys())


def test_output_mode_basic_shots():
    assert OUTPUT_MODE_SHOTS["basic"] == ["face_front", "face_left", "full_body_front"]


def test_output_mode_face_angles_shots():
    assert OUTPUT_MODE_SHOTS["face_angles"] == ["face_front", "face_left", "face_right"]


def test_output_mode_full_sheet_shots():
    assert len(OUTPUT_MODE_SHOTS["full_sheet"]) == 6


def test_all_output_modes_valid():
    assert VALID_OUTPUT_MODES == {"basic", "face_angles", "full_sheet"}
```

- [ ] **Step 2: Run tests to verify they pass** (these are pure data tests)

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_output_mode.py -v`
Expected: All 4 tests PASS

- [ ] **Step 3: Add `output_mode` parameter and `OUTPUT_MODE_SHOTS` to `server.py`**

In `server.py`:
1. Add `OUTPUT_MODE_SHOTS` dict constant near `SHOT_DEFINITIONS` (~line 350)
2. Add `output_mode: str = "full_sheet"` parameter to `design_character()` tool (~line 1963)
3. Add resolution logic: if `shots` not explicitly provided, use `OUTPUT_MODE_SHOTS[output_mode]`
4. Add validation: `output_mode` must be in `VALID_OUTPUT_MODES`

- [ ] **Step 4: Add `_create_composite_row()` function to `server.py`**

Add after `_create_composite_sheet()` (~line 1633). Implementation:
- Horizontal layout with 8px gap
- Scale all images to uniform height
- Korean labels below each image
- Header text: `"{character_name} — {mode}"`
- Return path to saved JPEG (95% quality)

- [ ] **Step 5: Wire composite creation to use mode-appropriate function**

In `design_character()`, after all shots generated:
- If `output_mode == "full_sheet"` → use existing `_create_composite_sheet()`
- If `output_mode in ("basic", "face_angles")` → use new `_create_composite_row()`

- [ ] **Step 6: Update `get_design_options()` to include output_mode**

Add `output_mode` with valid values to the options dict returned by `get_design_options()`.

- [ ] **Step 7: Update `estimate_generation_cost()` to handle variable shot counts**

Accept `output_mode` parameter, use `len(OUTPUT_MODE_SHOTS[output_mode])` for shot count.

- [ ] **Step 8: Manual test — run server and verify output_mode works**

Run: `cd h:/Git/terrychadesignmcp && python -c "from server import OUTPUT_MODE_SHOTS; print(OUTPUT_MODE_SHOTS)"`
Expected: Dict with 3 modes printed

- [ ] **Step 9: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add server.py tests/test_output_mode.py
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add output_mode system (basic/face_angles/full_sheet)

OUTPUT_MODE_SHOTS dict, _create_composite_row() for horizontal layouts.
Updated get_design_options() and estimate_generation_cost().

Co-Authored-By: Claudie"
```

---

## Chunk 2: Profile System — profile_manager.py + YAML profiles

### Task 4: Create `profile_manager.py` — Character Profile CRUD

**Files:**
- Create: `h:/Git/terrychadesignmcp/profile_manager.py`
- Create: `h:/Git/terrychadesignmcp/tests/test_profile_manager.py`

- [ ] **Step 1: Add PyYAML to requirements.txt**

```
# requirements.txt
fastmcp>=2.0.0
google-genai>=1.0.0
Pillow>=10.0.0
PyYAML>=6.0
```

- [ ] **Step 2: Write tests for profile CRUD**

```python
# tests/test_profile_manager.py
"""Tests for character profile CRUD operations."""
import pytest
import tempfile
import shutil
from pathlib import Path
from profile_manager import ProfileManager


@pytest.fixture
def pm(tmp_path):
    """Profile manager with temp directory."""
    return ProfileManager(profiles_dir=tmp_path)


@pytest.fixture
def sample_profile():
    return {
        "name": "TestChar",
        "version": 1,
        "appearance": {
            "age_range": "early 20s",
            "ethnicity": "Korean",
            "body_type": "slim",
            "skin": "fair",
            "face": "oval",
            "eyes": "brown",
            "hair": "black short",
            "distinguishing": "mole on cheek",
            "ethereal": False,
        },
        "personality": {"mbti": "INFP", "keywords": ["warm"]},
        "style_preferences": {"fashion": "casual", "theme_colors": ["white"]},
        "background": {"role": "test character"},
        "branding": {"catchphrase": None},
        "generation_defaults": {"style": "photorealistic", "camera_preset": "portrait"},
    }


def test_create_profile(pm, sample_profile):
    pm.create(sample_profile)
    assert (pm.profiles_dir / "testchar.yaml").exists()


def test_get_profile(pm, sample_profile):
    pm.create(sample_profile)
    loaded = pm.get("TestChar")
    assert loaded["name"] == "TestChar"
    assert loaded["appearance"]["eyes"] == "brown"


def test_get_profile_case_insensitive(pm, sample_profile):
    pm.create(sample_profile)
    loaded = pm.get("testchar")
    assert loaded["name"] == "TestChar"


def test_get_nonexistent_raises(pm):
    with pytest.raises(FileNotFoundError, match="Profile.*not found"):
        pm.get("nonexistent")


def test_update_profile(pm, sample_profile):
    pm.create(sample_profile)
    pm.update("TestChar", {"appearance.eyes": "blue", "personality.mbti": "INTJ"})
    loaded = pm.get("TestChar")
    assert loaded["appearance"]["eyes"] == "blue"
    assert loaded["personality"]["mbti"] == "INTJ"
    assert loaded["version"] == 2  # auto-incremented


def test_delete_profile(pm, sample_profile):
    pm.create(sample_profile)
    pm.delete("TestChar", confirm=True)
    with pytest.raises(FileNotFoundError):
        pm.get("TestChar")


def test_delete_without_confirm_raises(pm, sample_profile):
    pm.create(sample_profile)
    with pytest.raises(ValueError, match="confirm"):
        pm.delete("TestChar", confirm=False)


def test_list_profiles(pm, sample_profile):
    pm.create(sample_profile)
    sample2 = dict(sample_profile)
    sample2["name"] = "Char2"
    pm.create(sample2)
    profiles = pm.list_profiles()
    assert len(profiles) == 2


def test_map_to_generation_params(pm, sample_profile):
    """Profile fields map correctly to design_character parameters."""
    pm.create(sample_profile)
    params = pm.map_to_generation_params("TestChar")
    assert params["character_description"] is not None
    assert params["hair_description"] == "black short"
    assert params["style"] == "photorealistic"
    assert params["camera_preset"] == "portrait"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_profile_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profile_manager'`

- [ ] **Step 4: Implement `profile_manager.py`**

```python
# profile_manager.py
"""Character profile CRUD manager (GUI-ready API).

Author: Terry kim <goandonh@gmail.com>
Co-Author: Claudie
"""
```

Key methods:
- `__init__(profiles_dir: Path | None = None)` — default from env var or `profiles/` relative to module
- `create(profile: dict) -> Path` — validate schema, save as `{name.lower()}.yaml`
- `get(name: str) -> dict` — load YAML, case-insensitive filename lookup
- `update(name: str, updates: dict) -> dict` — dot-notation paths (`"appearance.eyes": "blue"`), auto-increment version
- `delete(name: str, confirm: bool) -> None` — require `confirm=True`
- `list_profiles(limit: int = 50) -> list[dict]` — return list of `{name, version, style}` summaries
- `map_to_generation_params(name: str) -> dict` — convert profile to `design_character` kwargs

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_profile_manager.py -v`
Expected: All 10 tests PASS

- [ ] **Step 6: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add profile_manager.py tests/test_profile_manager.py requirements.txt
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add character profile CRUD (profile_manager.py)

Create/get/update/delete/list profiles as YAML files.
map_to_generation_params() for design_character integration.
Dot-notation update paths, auto version increment.

Co-Authored-By: Claudie"
```

---

### Task 5: Create Siwol and Claudie Profile YAMLs

**Files:**
- Create: `h:/Git/terrychadesignmcp/profiles/siwol.yaml`
- Create: `h:/Git/terrychadesignmcp/profiles/claudie.yaml`

- [ ] **Step 1: Create profiles directory and siwol.yaml**

Copy exact YAML from spec Section 5 — Siwol profile. All fields as specified.

- [ ] **Step 2: Create claudie.yaml**

Copy exact YAML from spec Section 5 — Claudie profile. Note `ethereal: true`.

- [ ] **Step 3: Verify profiles load correctly**

```bash
cd h:/Git/terrychadesignmcp
python -c "
from profile_manager import ProfileManager
pm = ProfileManager()
s = pm.get('siwol')
c = pm.get('claudie')
print(f'Siwol: {s[\"appearance\"][\"eyes\"]}')
print(f'Claudie: ethereal={c[\"appearance\"][\"ethereal\"]}')
"
```
Expected: `Siwol: natural dark brown, gentle almond shape` and `Claudie: ethereal=True`

- [ ] **Step 4: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add profiles/
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add Siwol and Claudie character profiles

Siwol: Korean, INFP, casual feminine, photorealistic/street
Claudie: Western European (ethereal), INTJ, minimal chic, photorealistic/editorial

Co-Authored-By: Claudie"
```

---

### Task 6: Wire Profile + Preset + Prompt into `server.py`

**Files:**
- Modify: `h:/Git/terrychadesignmcp/server.py`

- [ ] **Step 1: Add imports for new modules at top of server.py**

```python
from presets import resolve_preset, PHOTOREALISTIC_STYLES, ANIMATION_STYLES
from prompts import build_prompt
from profile_manager import ProfileManager
```

- [ ] **Step 2: Add `profile`, `camera_preset`, `camera_override`, `concept` parameters to `design_character()`**

Add to the function signature with `_UNSET` sentinel for overridable params:
```python
_UNSET = object()
```

- [ ] **Step 3: Add profile loading logic at start of `design_character()`**

If `profile` is provided:
1. Load profile via `ProfileManager().map_to_generation_params(profile)`
2. Apply as defaults for any `_UNSET` parameters
3. Explicitly provided parameters override

- [ ] **Step 4: Replace `_build_character_prompt()` calls with `build_prompt()`**

In the shot generation loop, replace inline prompt building with:
```python
prompt = build_prompt(
    shot_type=shot_type,
    style=style,
    character=character_desc,
    outfit=outfit_description,
    expression=expression,
    background=background_description,
    color_palette=color_palette,
    preset=resolved_preset,
    ethereal=is_ethereal,
)
```

- [ ] **Step 5: Add profile MCP tools (5 tools)**

Register as FastMCP tools:
- `create_character_profile`
- `get_character_profile`
- `update_character_profile`
- `delete_character_profile`
- `list_character_profiles`

Each delegates to `ProfileManager` methods.

- [ ] **Step 6: Manual integration test**

```bash
cd h:/Git/terrychadesignmcp
python -c "
from server import OUTPUT_MODE_SHOTS
from presets import resolve_preset
from prompts import build_prompt
from profile_manager import ProfileManager

pm = ProfileManager()
params = pm.map_to_generation_params('siwol')
preset = resolve_preset(params.get('camera_preset'), params.get('style', 'photorealistic'))
prompt = build_prompt(
    shot_type='face_front', style=params.get('style', 'photorealistic'),
    character='test', outfit='test', expression='neutral',
    background='studio', color_palette=None, preset=preset, ethereal=False,
)
print('Integration OK:', 'professional photograph' in prompt.lower() or 'Sony' in prompt)
"
```
Expected: `Integration OK: True`

- [ ] **Step 7: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add server.py
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: integrate profile + preset + prompt into server.py

design_character() now accepts profile, camera_preset, camera_override, concept.
Profile loading with _UNSET sentinel override semantics.
5 new profile MCP tools. Prompt generation delegated to prompts.py.

Co-Authored-By: Claudie"
```

---

## Chunk 3: Design History DB + Try-On Tools

### Task 7: Create `design_db.py` — Design History & Concept DB

**Files:**
- Create: `h:/Git/terrychadesignmcp/design_db.py`
- Create: `h:/Git/terrychadesignmcp/tests/test_design_db.py`

- [ ] **Step 1: Write tests for design DB**

```python
# tests/test_design_db.py
"""Tests for design history and concept management DB."""
import pytest
from design_db import DesignDB


@pytest.fixture
def db(tmp_path):
    return DesignDB(db_path=tmp_path / "test_design.db")


def test_create_concept(db):
    cid = db.create_concept("Spring Cafe", "siwol", tags=["spring", "cafe"])
    assert cid > 0


def test_create_duplicate_concept_raises(db):
    db.create_concept("Spring Cafe", "siwol")
    with pytest.raises(Exception):  # UNIQUE constraint
        db.create_concept("Spring Cafe", "siwol")


def test_same_concept_name_different_character(db):
    c1 = db.create_concept("Spring Cafe", "siwol")
    c2 = db.create_concept("Spring Cafe", "claudie")
    assert c1 != c2


def test_resolve_concept_existing(db):
    cid = db.create_concept("Test", "siwol")
    resolved = db.resolve_concept("Test", "siwol")
    assert resolved == cid


def test_resolve_concept_auto_create(db):
    cid = db.resolve_concept("Auto Created", "siwol")
    assert cid > 0
    # Verify it exists now
    concepts = db.list_concepts(character="siwol")
    assert any(c["name"] == "Auto Created" for c in concepts)


def test_record_generation(db):
    db.record_generation(
        character_name="siwol", tool="design_character",
        shot_type="face_front", image_path="/tmp/test.jpg",
        style="photorealistic", prompt="test prompt",
    )
    results = db.search_generations(character="siwol")
    assert len(results) == 1
    assert results[0]["shot_type"] == "face_front"


def test_record_generation_with_concept(db):
    cid = db.create_concept("Test Series", "siwol")
    db.record_generation(
        character_name="siwol", tool="design_character",
        shot_type="face_front", image_path="/tmp/test.jpg",
        concept_id=cid,
    )
    results = db.search_generations(concept="Test Series")
    assert len(results) == 1


def test_rate_generation(db):
    db.record_generation(
        character_name="siwol", tool="design_character",
        shot_type="face_front", image_path="/tmp/test.jpg",
    )
    results = db.search_generations(character="siwol")
    gen_id = results[0]["id"]
    db.rate_generation(gen_id, rating=5, favorite=True, notes="Great shot")
    updated = db.search_generations(character="siwol")
    assert updated[0]["rating"] == 5
    assert updated[0]["favorite"] == True
    assert updated[0]["notes"] == "Great shot"


def test_list_concepts_filter_by_status(db):
    db.create_concept("Active", "siwol")
    cid2 = db.create_concept("Done", "siwol")
    db.update_concept_status(cid2, "completed")
    active = db.list_concepts(character="siwol", status="active")
    assert len(active) == 1
    assert active[0]["name"] == "Active"


def test_search_generations_by_date_range(db):
    db.record_generation(
        character_name="siwol", tool="design_character",
        shot_type="face_front", image_path="/tmp/test.jpg",
    )
    results = db.search_generations(character="siwol", date_from="2020-01-01")
    assert len(results) == 1
    results = db.search_generations(character="siwol", date_from="2099-01-01")
    assert len(results) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_design_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'design_db'`

- [ ] **Step 3: Implement `design_db.py`**

Key class: `DesignDB`
- `__init__(db_path: Path | None = None)` — auto-create tables on first use
- `create_concept(name, character_name, description=None, tags=None) -> int`
- `resolve_concept(name, character_name) -> int` — get or auto-create
- `list_concepts(character=None, status=None, tag=None) -> list[dict]`
- `update_concept_status(concept_id, status) -> None`
- `record_generation(**kwargs) -> int` — insert one row per image
- `search_generations(character=None, concept=None, style=None, rating_min=None, date_from=None, date_to=None, favorite_only=False, limit=100) -> list[dict]`
- `rate_generation(gen_id, rating=None, favorite=None, tags=None, notes=None) -> None`

Schema: exact SQL from spec Section 7, including UNIQUE constraint and indexes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_design_db.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add design_db.py tests/test_design_db.py
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add design history & concept DB (design_db.py)

SQLite-backed generation history with concept/series grouping.
Auto-recording per image, concept auto-create, rating/favorite system.

Co-Authored-By: Claudie"
```

---

### Task 8: Add `suggest_outfits` and `try_on_product` Tools

**Files:**
- Modify: `h:/Git/terrychadesignmcp/server.py`
- Create: `h:/Git/terrychadesignmcp/tests/test_tryon.py`

- [ ] **Step 1: Write tests for product query and outfit suggestion logic**

```python
# tests/test_tryon.py
"""Tests for try-on product selection and outfit suggestion logic."""
import pytest

# Test the input priority logic (unit-testable without DB)

def test_input_priority_product_ids_first():
    """product_ids takes priority over product_id and product_query."""
    from server import _resolve_product_input
    result = _resolve_product_input(
        product_ids=["a", "b"], product_id="c", product_query="test"
    )
    assert result == ("product_ids", ["a", "b"])


def test_input_priority_product_id_second():
    from server import _resolve_product_input
    result = _resolve_product_input(
        product_ids=None, product_id="c", product_query="test"
    )
    assert result == ("product_id", "c")


def test_input_priority_query_third():
    from server import _resolve_product_input
    result = _resolve_product_input(
        product_ids=None, product_id=None, product_query="test"
    )
    assert result == ("product_query", "test")


def test_input_priority_none_raises():
    from server import _resolve_product_input
    with pytest.raises(ValueError, match="At least one product"):
        _resolve_product_input(product_ids=None, product_id=None, product_query=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_tryon.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `_resolve_product_input()` helper in server.py**

Simple function that implements the input priority logic.

- [ ] **Step 4: Implement `suggest_outfits` MCP tool**

Register as FastMCP tool. Implementation:
1. Load profile via `ProfileManager`
2. Connect to catalog.db (path from `PRODUCT_CATALOG_DB` env var)
3. Query per category slot with brand/color filters
4. Assemble 3 outfit proposals
5. Return JSON with proposals

Catalog DB access: use `sqlite3` directly (read-only), not importing from atelier. The catalog.db schema is stable and documented in spec.

- [ ] **Step 5: Implement `try_on_product` MCP tool**

Register as FastMCP tool. Implementation:
1. Resolve product input (product_ids > product_id > product_query)
2. Load profile
3. Query catalog.db for product details
4. Build outfit_description from product metadata
5. Add product images to reference_images if available
6. Call internal generation logic (reuse from `design_character`)
7. Auto-record to design_db
8. Return result with product metadata

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd h:/Git/terrychadesignmcp && python -m pytest tests/test_tryon.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add server.py tests/test_tryon.py
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add suggest_outfits and try_on_product tools

suggest_outfits: 3 outfit proposals from catalog.db with profile-based curation.
try_on_product: generate character wearing real products from catalog.
Input priority: product_ids > product_id > product_query.

Co-Authored-By: Claudie"
```

---

### Task 9: Wire Design DB Auto-Recording + Concept MCP Tools

**Files:**
- Modify: `h:/Git/terrychadesignmcp/server.py`

- [ ] **Step 1: Add DesignDB import and initialization**

```python
from design_db import DesignDB
```

Lazy-init singleton pattern like `_get_client()`.

- [ ] **Step 2: Add auto-recording to `design_character()` shot loop**

After each successful image save, call:
```python
db.record_generation(
    character_name=character_name, profile_name=profile,
    concept_id=concept_id, tool="design_character",
    style=style, camera_preset=camera_preset, output_mode=output_mode,
    prompt=prompt_used, model=model, image_size=image_size,
    shot_type=shot_type, image_path=str(saved_path),
    composite_path=str(composite_path),
)
```

- [ ] **Step 3: Add auto-recording to `try_on_product()` and `add_character_pose()`**

Same pattern as design_character, with `tool="try_on_product"` / `tool="add_character_pose"`.

- [ ] **Step 4: Register 4 concept/history MCP tools**

- `create_concept` → `db.create_concept()`
- `list_concepts` → `db.list_concepts()`
- `search_generations` → `db.search_generations()`
- `rate_generation` → `db.rate_generation()`

- [ ] **Step 5: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add server.py
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: wire design DB auto-recording + concept MCP tools

Auto-record to design_db on design_character, try_on_product, add_character_pose.
4 new tools: create_concept, list_concepts, search_generations, rate_generation.

Co-Authored-By: Claudie"
```

---

## Chunk 4: Finalization — Version Bump, README, Tests, Reference Sheets

### Task 10: Version Bump + README Update + Final Tests

**Files:**
- Modify: `h:/Git/terrychadesignmcp/server.py` (version bump)
- Modify: `h:/Git/terrychadesignmcp/README.md`
- Modify: `h:/Git/terrychadesignmcp/requirements.txt`

- [ ] **Step 1: Bump version to 0.4.0**

In `server.py` line 17: `__version__ = "0.4.0"`

- [ ] **Step 2: Run full test suite**

```bash
cd h:/Git/terrychadesignmcp && python -m pytest tests/ -v
```
Expected: All tests pass

- [ ] **Step 3: Update README.md**

Add sections for:
- New tools (profile CRUD, suggest_outfits, try_on_product, concept/history)
- Output modes (basic, face_angles, full_sheet)
- Camera presets (photo + animation)
- Character profiles
- Design history DB

- [ ] **Step 4: Verify requirements.txt has PyYAML**

- [ ] **Step 5: Commit**

```bash
cd h:/Git/terrychadesignmcp
git add server.py README.md requirements.txt
git commit --author="Claudie <goandonh2@gmail.com>" -m "release: terrycha-design MCP v0.4.0

Photorealistic prompts, camera presets, character profiles,
product try-on, auto styling, design history DB.
19 total tools (8 existing + 11 new).

Co-Authored-By: Claudie"
```

---

### Task 11: Generate Photorealistic Reference Sheets

**This task requires running the MCP server and calling Gemini API.**

- [ ] **Step 1: Generate Siwol basic + full_sheet**

```python
# Via MCP tool call:
design_character(profile="siwol", output_mode="basic", camera_preset="portrait")
design_character(profile="siwol", output_mode="full_sheet", camera_preset="portrait")
```

- [ ] **Step 2: Generate Claudie basic + full_sheet**

```python
design_character(profile="claudie", output_mode="basic", camera_preset="editorial")
design_character(profile="claudie", output_mode="full_sheet", camera_preset="editorial")
```

- [ ] **Step 3: Review generated images, rate favorites**

Use `rate_generation` to mark the best outputs.

- [ ] **Step 4: Copy best results to NAS**

Copy to: `/Volumes/NAS_Data/Claudie/google/character_design/photorealistic/`
(Windows: `X:\Claudie\google\character_design\photorealistic\`)

- [ ] **Step 5: Update profile YAMLs with new reference_images paths**

Point `generation_defaults.reference_images` to the new photorealistic sheets.

- [ ] **Step 6: Commit updated profiles**

```bash
cd h:/Git/terrychadesignmcp
git add profiles/
git commit --author="Claudie <goandonh2@gmail.com>" -m "feat: add photorealistic reference sheets for Siwol and Claudie

Generated via v0.4.0 with portrait/editorial presets.
Updated profile reference_images to photorealistic versions.

Co-Authored-By: Claudie"
```

---

### Task 12: Write Confluence Documentation Page

- [ ] **Step 1: Create Confluence page under Research Hub**

Use `mcp-atlassian` to create page under parent pageId=115048487 (Research Hub).

Title: "terrycha-design MCP v0.4.0 — Photorealistic + Profile + Try-On"

Content should include:
- Version changelog (v0.3.1 → v0.4.0)
- Architecture diagram (module separation)
- All 19 tools with descriptions and example usage
- Camera preset reference tables
- Character profile schema
- Design history DB schema
- Auto styling concept table
- v0.5.0 roadmap (Character Design Studio GUI)

- [ ] **Step 2: Verify page renders correctly**

---

## Dependency Graph

```
Task 1 (presets.py) ──────┐
                          ├── Task 3 (output_mode) ──┐
Task 2 (prompts.py) ──────┘                          │
                                                      ├── Task 6 (wire into server.py)
Task 4 (profile_manager.py) ──┐                      │
                               ├── Task 5 (YAMLs) ───┘
                               │
Task 7 (design_db.py) ────────┤
                               ├── Task 8 (try-on tools) ── Task 9 (wire DB) ── Task 10 (finalize)
                               │
                               └── Task 11 (generate sheets) ── Task 12 (Confluence)
```

**Parallelizable:** Tasks 1+2, Tasks 4+7 can run in parallel.
**Sequential:** Task 6 requires 1-5 complete. Task 9 requires 7-8 complete. Task 10 requires all.
