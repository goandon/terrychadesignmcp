# tests/test_tryon.py
"""Tests for try-on product selection logic."""
import sys
sys.path.insert(0, ".")


def test_input_priority_product_ids_first():
    from server import _resolve_product_input
    result = _resolve_product_input(product_ids=["a", "b"], product_id="c", product_query="test")
    assert result == ("product_ids", ["a", "b"])


def test_input_priority_product_id_second():
    from server import _resolve_product_input
    result = _resolve_product_input(product_ids=None, product_id="c", product_query="test")
    assert result == ("product_id", "c")


def test_input_priority_query_third():
    from server import _resolve_product_input
    result = _resolve_product_input(product_ids=None, product_id=None, product_query="test")
    assert result == ("product_query", "test")


def test_input_priority_none_raises():
    import pytest
    from server import _resolve_product_input
    with pytest.raises(ValueError, match="At least one product"):
        _resolve_product_input(product_ids=None, product_id=None, product_query=None)
