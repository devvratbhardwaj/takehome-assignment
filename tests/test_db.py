import sqlite3

import pytest

from app.db import get_connection, init_schema


@pytest.fixture
def connection():
    connection = get_connection(":memory:")
    init_schema(connection)
    connection.execute(
        "INSERT INTO suppliers VALUES ('SUP-001', 'Steel Co', 'Toronto, ON', 7, 'Net 30')"
    )
    yield connection
    connection.close()


def insert_material(connection, **overrides):
    material = {
        "sku": "SKU-1",
        "description": "Rebar 15M",
        "category": "Rebar",
        "spec_grade": "400W",
        "unit_of_measure": "tonne",
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


def test_init_schema_runs_twice_and_wipes_data(connection):
    insert_material(connection)
    init_schema(connection)
    assert connection.execute("SELECT count(*) FROM materials").fetchone()[0] == 0


def test_material_with_unknown_supplier_is_rejected(connection):
    with pytest.raises(sqlite3.IntegrityError):
        insert_material(connection, primary_supplier_id="NO-SUCH-SUPPLIER")


def test_negative_stock_is_rejected(connection):
    with pytest.raises(sqlite3.IntegrityError):
        insert_material(connection, qty_on_hand=-1)


def test_zero_quantity_order_is_rejected(connection):
    insert_material(connection)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO orders (sku, quantity, unit_price, line_total)"
            " VALUES ('SKU-1', 0, 1.0, 0.0)"
        )


def test_view_derives_qty_available(connection):
    insert_material(connection, qty_on_hand=10, qty_reserved=3)
    row = connection.execute(
        "SELECT qty_available FROM materials_with_availability WHERE sku = 'SKU-1'"
    ).fetchone()
    assert row["qty_available"] == 7
