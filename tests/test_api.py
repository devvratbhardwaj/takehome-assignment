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
