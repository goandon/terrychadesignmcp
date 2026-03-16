# tests/test_presets.py
"""Tests for camera preset resolution system."""
import pytest
from presets import (
    PHOTO_PRESETS, ANIMATION_PRESETS,
    PHOTOREALISTIC_STYLES, ANIMATION_STYLES,
    resolve_preset, VALID_OVERRIDE_KEYS,
)


def test_photo_presets_have_required_keys():
    for name, preset in PHOTO_PRESETS.items():
        assert "camera" in preset, f"{name} missing 'camera'"
        assert "lens" in preset, f"{name} missing 'lens'"
        assert "lighting" in preset, f"{name} missing 'lighting'"


def test_animation_presets_have_required_keys():
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
    result = resolve_preset(None, "photorealistic")
    assert result == PHOTO_PRESETS["portrait"]


def test_resolve_preset_default_for_animation():
    result = resolve_preset(None, "anime")
    assert result == ANIMATION_PRESETS["anime_standard"]


def test_resolve_preset_default_style_returns_none():
    result = resolve_preset(None, "watercolor")
    assert result is None


def test_resolve_preset_with_override():
    result = resolve_preset("portrait", "photorealistic", override={"lens": "50mm f/1.2"})
    assert result["lens"] == "50mm f/1.2"
    assert result["camera"] == "Sony A7IV"


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
    assert PHOTOREALISTIC_STYLES.isdisjoint(ANIMATION_STYLES)
