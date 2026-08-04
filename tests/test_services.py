import pytest

from app.db import get_connection, init_schema
from app.services import get_suppliers


@pytest.fixture
def connection():
    connection = get_connection(":memory:")
    init_schema(connection)
    connection.executemany(
        "INSERT INTO suppliers VALUES (?, ?, ?, ?, ?)",
        [
            ("SUP-001", "Northline Steel Supply", "Hamilton, ON", 10, "NET30"),
            ("SUP-002", "Grand River Rebar Ltd.", "Cambridge, ON", 7, "NET30"),
            ("SUP-009", "Lakeshore Metal Products", "Oakville, ON", 21, "NET60"),
        ],
    )
    yield connection
    connection.close()


def insert_material(connection, **overrides):
    material = {
        "sku": "SKU-1",
        "description": "Rebar 15M",
        "category": "rebar",
        "spec_grade": "400W",
        "unit_of_measure": "each",
        "unit_price": 1.0,
        "currency": "CAD",
        "qty_on_hand": 10,
        "qty_reserved": 3,
        "reorder_point": 5,
        "min_order_qty": 1,
        "primary_supplier_id": "SUP-001",
        "warehouse": "W1",
        "discontinued": 0,
    }
    material.update(overrides)
    columns = ", ".join(material)
    placeholders = ", ".join(":" + column for column in material)
    connection.execute(
        f"INSERT INTO materials ({columns}) VALUES ({placeholders})", material
    )


def test_all_suppliers_returned_without_filters(connection):
    suppliers = get_suppliers(connection)
    assert [supplier["supplier_id"] for supplier in suppliers] == [
        "SUP-001",
        "SUP-002",
        "SUP-009",
    ]
    assert suppliers[0]["name"] == "Northline Steel Supply"
    assert suppliers[0]["standard_lead_time_days"] == 10
    assert suppliers[0]["payment_terms"] == "NET30"


def test_filter_by_supplier_id(connection):
    suppliers = get_suppliers(connection, supplier_id="SUP-002")
    assert [supplier["supplier_id"] for supplier in suppliers] == ["SUP-002"]


def test_unknown_supplier_id_returns_empty_list(connection):
    assert get_suppliers(connection, supplier_id="SUP-999") == []


def test_filter_by_category_returns_distinct_primary_suppliers(connection):
    insert_material(connection, sku="RBR-1", category="rebar", primary_supplier_id="SUP-002")
    insert_material(connection, sku="RBR-2", category="rebar", primary_supplier_id="SUP-002")
    insert_material(connection, sku="STL-1", category="structural_steel", primary_supplier_id="SUP-001")
    suppliers = get_suppliers(connection, category="rebar")
    assert [supplier["supplier_id"] for supplier in suppliers] == ["SUP-002"]


def test_category_with_no_materials_returns_empty_list(connection):
    assert get_suppliers(connection, category="lumber") == []
