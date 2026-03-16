# tests/test_prompts.py
"""Tests for style-specific prompt template system."""
import pytest
from prompts import (
    PHOTOREALISTIC_TEMPLATES, ANIMATION_TEMPLATES, DEFAULT_TEMPLATES,
    ALL_SHOT_TYPES, build_prompt, ETHEREAL_MODIFIER,
)
from presets import PHOTO_PRESETS, ANIMATION_PRESETS


def test_all_template_dicts_have_all_shot_types():
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
    assert "Sony" not in result


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
