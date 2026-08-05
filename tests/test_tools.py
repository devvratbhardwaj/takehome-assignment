import json

import pytest

from app.db import get_connection, init_schema
from app.tools import (
    get_stock,
    get_suppliers,
    place_order,
    quote_order,
    search_materials,
)


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


@pytest.fixture
def database_path(tmp_path, monkeypatch):
    ## Tools resolve INVENTORY_DB themselves, so the fixture seeds a file DB.
    path = tmp_path / "tools.db"
    monkeypatch.setenv("INVENTORY_DB", str(path))
    connection = get_connection(path)
    init_schema(connection)
    connection.executemany(
        "INSERT INTO suppliers VALUES (?, ?, ?, ?, ?)",
        [
            ("SUP-001", "Northline Steel Supply", "Hamilton, ON", 10, "NET30"),
            ("SUP-009", "Lakeshore Metal Products", "Oakville, ON", 21, "NET60"),
        ],
    )
    insert_material(connection)
    insert_material(
        connection,
        sku="SKU-OVER",
        description="W12x40 beam",
        category="structural_steel",
        qty_on_hand=4,
        qty_reserved=6,
    )
    connection.commit()
    connection.close()
    return path


def test_search_returns_json_payload(database_path):
    results = json.loads(search_materials.invoke({"query": "rebar 15m"}))
    assert [material["sku"] for material in results] == ["SKU-1"]
    assert results[0]["qty_available"] == 7
    assert "note" not in results[0]


def test_search_no_match_returns_empty_json_list(database_path):
    assert json.loads(search_materials.invoke({"query": "epoxy 25M"})) == []


def test_get_stock_over_allocated_carries_note(database_path):
    stock = json.loads(get_stock.invoke({"sku": "SKU-OVER"}))
    assert stock["qty_available"] == -2
    assert stock["orderable_qty"] == 0
    assert stock["over_allocated"] is True
    assert "reservations" in stock["note"]


def test_get_stock_unknown_sku_returns_error_object(database_path):
    assert json.loads(get_stock.invoke({"sku": "SKU-NOPE"})) == {
        "error": "unknown_sku",
        "sku": "SKU-NOPE",
    }


def test_quote_order_prices_without_persisting(database_path):
    quote = json.loads(quote_order.invoke({"sku": "SKU-1", "quantity": 5}))
    assert quote["status"] == "quote"
    assert quote["line_total"] == 5.0
    assert quote["fulfillable"] is True
    connection = get_connection(database_path)
    reserved = connection.execute(
        "SELECT qty_reserved FROM materials WHERE sku = 'SKU-1'"
    ).fetchone()[0]
    connection.close()
    assert reserved == 3


def test_place_order_confirms_and_persists(database_path):
    result = json.loads(place_order.invoke({"sku": "SKU-1", "quantity": 2}))
    assert result["status"] == "confirmed"
    assert result["line_total"] == 2.0
    connection = get_connection(database_path)
    reserved = connection.execute(
        "SELECT qty_reserved FROM materials WHERE sku = 'SKU-1'"
    ).fetchone()[0]
    connection.close()
    assert reserved == 5


def test_place_order_relays_rejection(database_path):
    result = json.loads(place_order.invoke({"sku": "SKU-1", "quantity": 100}))
    assert result["status"] == "rejected"
    assert result["reason"] == "insufficient_stock"
    assert result["orderable_qty"] == 7


def test_get_suppliers_filters_by_category(database_path):
    suppliers = json.loads(get_suppliers.invoke({"category": "rebar"}))
    assert [supplier["supplier_id"] for supplier in suppliers] == ["SUP-001"]


def test_tool_schemas_expose_expected_args():
    assert set(search_materials.args) == {"query"}
    assert set(get_stock.args) == {"sku"}
    assert set(quote_order.args) == {"sku", "quantity"}
    assert set(place_order.args) == {"sku", "quantity"}
    assert set(get_suppliers.args) == {"supplier_id", "category"}
    for wrapped in (search_materials, get_stock, quote_order, place_order, get_suppliers):
        assert wrapped.description
