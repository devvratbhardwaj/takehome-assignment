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
