import pytest
from app.models import Material
from pydantic import ValidationError

def make_material(**overrides) -> Material:
    base = dict(
        sku="TEST-SKU", 
        description="test item", 
        category="misc",
        spec_grade=None, 
        unit_of_measure="each", 
        unit_price=1.0,
        currency="CAD", 
        qty_on_hand=0, 
        qty_reserved=0, 
        reorder_point=0,
        min_order_qty=1, 
        primary_supplier_id="TEST-SUP-001",
        warehouse="TEST-WH-A", 
        discontinued=False,
    )
    return Material(**base | overrides)


def test_qty_available_is_derived():
    assert make_material(qty_on_hand=100, qty_reserved=24).qty_available == 76


def test_qty_available_can_be_negative_when_over_allocated():
    assert make_material(qty_on_hand=4, qty_reserved=6).qty_available == -2


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_material(surprise_field=123)
