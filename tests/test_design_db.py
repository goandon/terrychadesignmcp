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
    with pytest.raises(Exception):
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
