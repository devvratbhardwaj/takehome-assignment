import threading

import pytest

from app.db import get_connection, init_schema
from app.services import (
    get_stock,
    get_suppliers,
    place_order,
    quote_order,
    search_materials,
)


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
    connection.commit()
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
    ## Committed so place_order's BEGIN IMMEDIATE never nests inside seeding.
    connection.commit()


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


def test_supplier_category_filter_is_case_insensitive(connection):
    insert_material(connection, sku="RBR-1", category="rebar", primary_supplier_id="SUP-002")
    suppliers = get_suppliers(connection, category="Rebar")
    assert [supplier["supplier_id"] for supplier in suppliers] == ["SUP-002"]


def test_search_matches_description_case_insensitively(connection):
    insert_material(connection, sku="RBR-15M-400W", description="15M deformed rebar, 6 m length")
    insert_material(connection, sku="STL-W12X40-A992", description="W12x40 wide flange beam", category="structural_steel")
    results = search_materials(connection, "Rebar")
    assert [result["sku"] for result in results] == ["RBR-15M-400W"]


def test_search_matches_sku_and_spec_grade_tokens(connection):
    insert_material(
        connection,
        sku="STL-W12X40-A992",
        description="W12x40 wide flange beam",
        category="structural_steel",
        spec_grade="ASTM A992",
    )
    assert [r["sku"] for r in search_materials(connection, "w12x40")] == ["STL-W12X40-A992"]
    assert [r["sku"] for r in search_materials(connection, "a992")] == ["STL-W12X40-A992"]


def test_search_requires_every_token_to_match(connection):
    insert_material(connection, sku="RBR-15M-400W", description="15M deformed rebar, 6 m length")
    insert_material(connection, sku="RBR-20M-400W", description="20M deformed rebar, 6 m length")
    results = search_materials(connection, "15m rebar")
    assert [result["sku"] for result in results] == ["RBR-15M-400W"]


def test_search_returns_empty_list_when_nothing_matches(connection):
    insert_material(connection, sku="RBR-15M-EPOXY", description="15M epoxy coated rebar, 6 m length")
    insert_material(connection, sku="RBR-20M-EPOXY", description="20M epoxy coated rebar, 6 m length")
    assert search_materials(connection, "25m epoxy rebar") == []


def test_search_matches_plural_query_against_singular_description(connection):
    insert_material(connection, sku="RBR-20M-400W", description="20M deformed rebar, 6 m length")
    results = search_materials(connection, "20M rebars")
    assert [result["sku"] for result in results] == ["RBR-20M-400W"]


def test_search_normalizes_unit_words_and_punctuation(connection):
    insert_material(connection, sku="STL-PL38-A36", description="Steel plate 3/8 in, 4x8 ft sheet", category="structural_steel")
    for query in ('3/8 inch steel plate', '3/8" steel plate', '3/8 in steel plate'):
        assert [r["sku"] for r in search_materials(connection, query)] == ["STL-PL38-A36"], query


def test_search_drops_stop_words_from_order_phrasings(connection):
    insert_material(connection, sku="STL-PL38-A36", description="Steel plate 3/8 in, 4x8 ft sheet", category="structural_steel")
    results = search_materials(connection, "3 sheets of 3/8 inch steel plate")
    assert [result["sku"] for result in results] == ["STL-PL38-A36"]


def test_search_drops_single_character_tokens(connection):
    insert_material(connection, sku="FST-A325-34X2", description="A325 structural bolt 3/4 x 2 in, hex", category="fasteners")
    insert_material(connection, sku="RBR-15M-400W", description="15M deformed rebar, 6 m length")
    results = search_materials(connection, "3/4 x 2 bolt")
    assert [result["sku"] for result in results] == ["FST-A325-34X2"]


def test_search_finds_discontinued_materials(connection):
    insert_material(connection, sku="STL-PL38-A36", description="Steel plate 3/8 in, 4x8 ft sheet", category="structural_steel", discontinued=1)
    results = search_materials(connection, "3/8 steel plate")
    assert [result["sku"] for result in results] == ["STL-PL38-A36"]
    assert results[0]["discontinued"]


def test_search_category_filter_is_case_insensitive(connection):
    insert_material(connection, sku="RBR-15M-400W", description="15M deformed rebar")
    results = search_materials(connection, "rebar", category="Rebar")
    assert [result["sku"] for result in results] == ["RBR-15M-400W"]


def test_search_category_filter_narrows_results(connection):
    insert_material(connection, sku="STL-PL38-A36", description="Steel plate 3/8 in", category="structural_steel")
    insert_material(connection, sku="MSC-BAND-STL", description="Steel banding roll", category="misc")
    results = search_materials(connection, "steel", category="structural_steel")
    assert [result["sku"] for result in results] == ["STL-PL38-A36"]


def test_search_matches_material_with_null_spec_grade(connection):
    insert_material(connection, sku="MSC-POLY-6MIL", description="Poly sheeting 6 mil", spec_grade=None)
    results = search_materials(connection, "poly")
    assert [result["sku"] for result in results] == ["MSC-POLY-6MIL"]


def test_get_stock_returns_full_payload_for_healthy_sku(connection):
    insert_material(
        connection,
        sku="RBR-15M-400W",
        description="15M deformed rebar, 6 m length",
        unit_price=27.85,
        qty_on_hand=120,
        qty_reserved=0,
        reorder_point=25,
    )
    stock = get_stock(connection, "RBR-15M-400W")
    assert stock["qty_available"] == 120
    assert stock["orderable_qty"] == 120
    assert stock["over_allocated"] is False
    assert stock["needs_reorder"] is False
    assert stock["unit_price"] == 27.85
    assert stock["unit_of_measure"] == "each"
    assert stock["warehouse"] == "W1"


def test_get_stock_over_allocated_sku(connection):
    insert_material(connection, sku="STL-W12X40-A992", qty_on_hand=4, qty_reserved=6)
    stock = get_stock(connection, "STL-W12X40-A992")
    assert stock["qty_available"] == -2
    assert stock["orderable_qty"] == 0
    assert stock["over_allocated"] is True


def test_get_stock_fully_reserved_sku_is_not_over_allocated(connection):
    insert_material(connection, sku="RBR-20M-EPOXY", qty_on_hand=18, qty_reserved=18)
    stock = get_stock(connection, "RBR-20M-EPOXY")
    assert stock["qty_available"] == 0
    assert stock["orderable_qty"] == 0
    assert stock["over_allocated"] is False


def test_get_stock_unknown_sku_returns_none(connection):
    assert get_stock(connection, "RBR-25M-EPOXY") is None


def test_get_stock_flags_needs_reorder(connection):
    insert_material(connection, sku="RBR-20M-EPOXY", qty_on_hand=18, qty_reserved=18, reorder_point=30)
    assert get_stock(connection, "RBR-20M-EPOXY")["needs_reorder"] is True


def test_get_stock_still_reports_discontinued_sku(connection):
    insert_material(connection, sku="STL-PL38-A36", qty_on_hand=6, qty_reserved=2, discontinued=1)
    stock = get_stock(connection, "STL-PL38-A36")
    assert stock["discontinued"]
    assert stock["qty_available"] == 4


def test_search_results_carry_availability_fields(connection):
    insert_material(connection, sku="RBR-15M-400W", description="15M deformed rebar", qty_on_hand=10, qty_reserved=3)
    result = search_materials(connection, "rebar")[0]
    assert result["qty_available"] == 7
    assert result["orderable_qty"] == 7
    assert result["over_allocated"] is False


def reserved_qty(connection, sku):
    return connection.execute(
        "SELECT qty_reserved FROM materials WHERE sku = :sku", {"sku": sku}
    ).fetchone()[0]


def order_count(connection):
    return connection.execute("SELECT count(*) FROM orders").fetchone()[0]


def test_place_order_confirms_and_reserves_stock(connection):
    insert_material(connection, sku="RBR-15M-400W", unit_price=27.85, qty_on_hand=120, qty_reserved=0)
    result = place_order(connection, "RBR-15M-400W", 100)
    assert result["status"] == "confirmed"
    assert result["quantity"] == 100
    assert result["unit_price"] == 27.85
    assert result["line_total"] == 2785.0
    assert result["order_id"] is not None
    assert reserved_qty(connection, "RBR-15M-400W") == 100
    assert get_stock(connection, "RBR-15M-400W")["qty_available"] == 20
    assert order_count(connection) == 1


def test_place_order_rejects_more_than_available(connection):
    insert_material(connection, sku="RBR-15M-400W", qty_on_hand=120, qty_reserved=0)
    result = place_order(connection, "RBR-15M-400W", 500)
    assert result["status"] == "rejected"
    assert result["reason"] == "insufficient_stock"
    assert result["orderable_qty"] == 120
    assert reserved_qty(connection, "RBR-15M-400W") == 0
    assert order_count(connection) == 0


def test_place_order_rejects_discontinued_even_with_stock(connection):
    insert_material(connection, sku="STL-PL38-A36", qty_on_hand=6, qty_reserved=2, discontinued=1)
    result = place_order(connection, "STL-PL38-A36", 3)
    assert result["status"] == "rejected"
    assert result["reason"] == "discontinued"
    assert order_count(connection) == 0


def test_place_order_rejects_unknown_sku(connection):
    result = place_order(connection, "RBR-25M-EPOXY", 10)
    assert result["status"] == "rejected"
    assert result["reason"] == "unknown_sku"


@pytest.mark.parametrize("quantity", [0, -5])
def test_place_order_rejects_invalid_quantity(connection, quantity):
    insert_material(connection, sku="RBR-15M-400W")
    result = place_order(connection, "RBR-15M-400W", quantity)
    assert result["status"] == "rejected"
    assert result["reason"] == "invalid_quantity"


def test_place_order_rejects_fully_reserved_sku(connection):
    insert_material(connection, sku="RBR-20M-EPOXY", qty_on_hand=18, qty_reserved=18)
    result = place_order(connection, "RBR-20M-EPOXY", 1)
    assert result["reason"] == "insufficient_stock"
    assert result["orderable_qty"] == 0
    assert result["over_allocated"] is False


def test_place_order_rejects_over_allocated_sku(connection):
    insert_material(connection, sku="STL-W12X40-A992", qty_on_hand=4, qty_reserved=6)
    result = place_order(connection, "STL-W12X40-A992", 1)
    assert result["reason"] == "insufficient_stock"
    assert result["orderable_qty"] == 0
    assert result["qty_available"] == -2
    assert result["over_allocated"] is True


def test_place_order_ignores_min_order_qty(connection):
    ## Spec rule 6: min_order_qty governs restocking, never customer orders.
    insert_material(connection, sku="RBR-15M-400W", qty_on_hand=120, min_order_qty=25)
    assert place_order(connection, "RBR-15M-400W", 1)["status"] == "confirmed"


def test_place_order_matches_sku_case_insensitively(connection):
    insert_material(connection, sku="RBR-15M-400W", qty_on_hand=120, qty_reserved=0)
    result = place_order(connection, "rbr-15m-400w", 10)
    assert result["status"] == "confirmed"
    assert result["sku"] == "RBR-15M-400W"
    assert reserved_qty(connection, "RBR-15M-400W") == 10


def test_get_stock_matches_sku_case_insensitively(connection):
    insert_material(connection, sku="RBR-15M-400W")
    assert get_stock(connection, "rbr-15m-400w")["sku"] == "RBR-15M-400W"


def test_quote_order_prices_without_reserving(connection):
    insert_material(connection, sku="RBR-15M-400W", unit_price=27.85, qty_on_hand=120, qty_reserved=0)
    quote = quote_order(connection, "RBR-15M-400W", 100)
    assert quote["status"] == "quote"
    assert quote["line_total"] == 2785.0
    assert quote["fulfillable"] is True
    assert reserved_qty(connection, "RBR-15M-400W") == 0
    assert order_count(connection) == 0


def test_quote_order_still_prices_unfulfillable_quantities(connection):
    insert_material(connection, sku="RBR-15M-400W", unit_price=27.85, qty_on_hand=120, qty_reserved=0)
    quote = quote_order(connection, "RBR-15M-400W", 500)
    assert quote["status"] == "quote"
    assert quote["line_total"] == 13925.0
    assert quote["fulfillable"] is False
    assert quote["orderable_qty"] == 120


def test_quote_order_ignores_min_order_qty(connection):
    ## Spec rule 6 again: a 1-unit quote is fulfillable despite min_order_qty=25.
    insert_material(connection, sku="RBR-15M-400W", qty_on_hand=120, min_order_qty=25)
    assert quote_order(connection, "RBR-15M-400W", 1)["fulfillable"] is True


def test_quote_order_rejects_unknown_and_discontinued(connection):
    insert_material(connection, sku="STL-PL38-A36", discontinued=1)
    assert quote_order(connection, "RBR-25M-EPOXY", 10)["reason"] == "unknown_sku"
    assert quote_order(connection, "STL-PL38-A36", 1)["reason"] == "discontinued"
    assert quote_order(connection, "STL-PL38-A36", 0)["reason"] == "invalid_quantity"


def test_place_order_allows_exactly_available_quantity(connection):
    insert_material(connection, sku="RBR-15M-400W", qty_on_hand=120, qty_reserved=0)
    assert place_order(connection, "RBR-15M-400W", 120)["status"] == "confirmed"
    assert get_stock(connection, "RBR-15M-400W")["qty_available"] == 0


def test_concurrent_orders_cannot_oversell(tmp_path):
    path = tmp_path / "race.db"
    connection = get_connection(path)
    init_schema(connection)
    connection.execute(
        "INSERT INTO suppliers VALUES"
        " ('SUP-001', 'Northline Steel Supply', 'Hamilton, ON', 10, 'NET30')"
    )
    insert_material(connection, qty_on_hand=10, qty_reserved=0)
    connection.close()

    barrier = threading.Barrier(2)
    results = []

    def order():
        thread_connection = get_connection(path)
        try:
            barrier.wait()
            results.append(place_order(thread_connection, "SKU-1", 7))
        finally:
            thread_connection.close()

    threads = [threading.Thread(target=order) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(result["status"] for result in results) == ["confirmed", "rejected"]
    connection = get_connection(path)
    reserved = reserved_qty(connection, "SKU-1")
    connection.close()
    assert reserved == 7
