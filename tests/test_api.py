import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    ## INVENTORY_DB must point at a temp path before the lifespan opens the DB.
    monkeypatch.setenv("INVENTORY_DB", str(tmp_path / "test.db"))
    from app.main import app

    with TestClient(app) as client:
        yield client


def test_all_suppliers_returned_without_filters(client):
    response = client.get("/api/suppliers")
    assert response.status_code == 200
    suppliers = response.json()
    assert len(suppliers) == 9
    assert set(suppliers[0]) == {
        "supplier_id",
        "name",
        "location",
        "standard_lead_time_days",
        "payment_terms",
    }


def test_filter_by_supplier_id(client):
    response = client.get("/api/suppliers", params={"supplier_id": "SUP-001"})
    assert response.status_code == 200
    assert [supplier["supplier_id"] for supplier in response.json()] == ["SUP-001"]


def test_filter_by_category(client):
    response = client.get("/api/suppliers", params={"category": "structural_steel"})
    assert response.status_code == 200
    assert [supplier["supplier_id"] for supplier in response.json()] == [
        "SUP-001",
        "SUP-009",
    ]


def test_unknown_supplier_id_returns_empty_list(client):
    response = client.get("/api/suppliers", params={"supplier_id": "SUP-999"})
    assert response.status_code == 200
    assert response.json() == []


def test_search_passes_availability_fields_through(client):
    response = client.get("/api/materials/search", params={"query": "W12x40"})
    assert response.status_code == 200
    materials = response.json()
    assert [material["sku"] for material in materials] == ["STL-W12X40-A992"]
    assert materials[0]["qty_available"] == -2
    assert materials[0]["orderable_qty"] == 0
    assert materials[0]["over_allocated"] is True


def test_search_with_category_filter(client):
    response = client.get(
        "/api/materials/search", params={"query": "15M", "category": "rebar"}
    )
    assert response.status_code == 200
    materials = response.json()
    assert all(material["category"] == "rebar" for material in materials)
    assert "RBR-15M-400W" in [material["sku"] for material in materials]


def test_search_no_match_returns_empty_list(client):
    response = client.get("/api/materials/search", params={"query": "unobtainium"})
    assert response.status_code == 200
    assert response.json() == []


def test_search_without_query_param_is_rejected(client):
    response = client.get("/api/materials/search")
    assert response.status_code == 422


def test_stock_passes_service_payload_through(client):
    response = client.get("/api/materials/STL-W12X40-A992")
    assert response.status_code == 200
    stock = response.json()
    assert stock["sku"] == "STL-W12X40-A992"
    assert stock["qty_on_hand"] == 4
    assert stock["qty_reserved"] == 6
    assert stock["qty_available"] == -2
    assert stock["orderable_qty"] == 0
    assert stock["over_allocated"] is True
    assert stock["needs_reorder"] is True


def test_stock_unknown_sku_returns_404(client):
    response = client.get("/api/materials/NOPE-123")
    assert response.status_code == 404
    assert "NOPE-123" in response.json()["detail"]


def test_order_confirmed_returns_201_and_reserves_stock(client):
    response = client.post(
        "/api/orders", json={"sku": "RBR-15M-400W", "quantity": 10}
    )
    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "confirmed"
    assert order["order_id"] == 1
    assert order["unit_price"] == 27.85
    assert order["line_total"] == 278.5
    assert order["currency"] == "CAD"

    stock = client.get("/api/materials/RBR-15M-400W").json()
    assert stock["qty_reserved"] == 10
    assert stock["qty_available"] == 110


def test_order_insufficient_stock_returns_409_with_payload(client):
    response = client.post(
        "/api/orders", json={"sku": "RBR-15M-400W", "quantity": 500}
    )
    assert response.status_code == 409
    assert response.json() == {
        "status": "rejected",
        "reason": "insufficient_stock",
        "sku": "RBR-15M-400W",
        "requested_qty": 500,
        "orderable_qty": 120,
        "qty_available": 120,
        "over_allocated": False,
    }


def test_order_over_allocated_sku_rejected_with_flags(client):
    response = client.post(
        "/api/orders", json={"sku": "STL-W12X40-A992", "quantity": 1}
    )
    assert response.status_code == 409
    rejection = response.json()
    assert rejection["reason"] == "insufficient_stock"
    assert rejection["orderable_qty"] == 0
    assert rejection["qty_available"] == -2
    assert rejection["over_allocated"] is True


def test_order_discontinued_returns_409(client):
    response = client.post("/api/orders", json={"sku": "STL-PL38-A36", "quantity": 1})
    assert response.status_code == 409
    assert response.json() == {
        "status": "rejected",
        "reason": "discontinued",
        "sku": "STL-PL38-A36",
    }


def test_order_unknown_sku_returns_404(client):
    response = client.post("/api/orders", json={"sku": "NOPE-123", "quantity": 1})
    assert response.status_code == 404
    assert response.json() == {
        "status": "rejected",
        "reason": "unknown_sku",
        "sku": "NOPE-123",
    }


def test_reset_restores_feed_state(client):
    client.post("/api/orders", json={"sku": "RBR-15M-400W", "quantity": 10})
    response = client.post("/api/admin/reset")
    assert response.status_code == 200
    assert response.json() == {"suppliers": 9, "materials": 77}
    stock = client.get("/api/materials/RBR-15M-400W").json()
    assert stock["qty_reserved"] == 0
    assert stock["qty_available"] == 120


def test_order_invalid_quantity_returns_422(client):
    response = client.post("/api/orders", json={"sku": "RBR-15M-400W", "quantity": 0})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "quantity"]


def test_root_serves_chat_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
