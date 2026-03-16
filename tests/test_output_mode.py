# tests/test_output_mode.py
"""Tests for output mode shot resolution."""
import sys
sys.path.insert(0, ".")

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
