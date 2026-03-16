# tests/test_profile_manager.py
"""Tests for character profile CRUD operations."""
import pytest
from profile_manager import ProfileManager


@pytest.fixture
def pm(tmp_path):
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
    assert loaded["version"] == 2


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
    pm.create(sample_profile)
    params = pm.map_to_generation_params("TestChar")
    assert params["hair_description"] == "black short"
    assert params["style"] == "photorealistic"
    assert params["camera_preset"] == "portrait"
