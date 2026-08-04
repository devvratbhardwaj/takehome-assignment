import pytest

from app.db import get_connection
from app.ingest import DATA_PATH, ingest

# Snapshot of the current feed; update if raw_data/inventory_data.json changes.
EXPECTED_COUNTS = {"suppliers": 9, "materials": 77}


@pytest.fixture
def connection():
    connection = get_connection(":memory:")
    yield connection
    connection.close()


def test_real_feed_lands(connection):
    counts = ingest(connection, DATA_PATH)
    assert counts == EXPECTED_COUNTS
    over_allocated_beam = connection.execute(
        "SELECT qty_available FROM materials_with_availability"
        " WHERE sku = 'STL-W12X40-A992'"
    ).fetchone()
    assert over_allocated_beam["qty_available"] == -2


def test_ingest_is_idempotent(connection):
    ingest(connection, DATA_PATH)
    counts = ingest(connection, DATA_PATH)
    assert counts == EXPECTED_COUNTS
    material_count = connection.execute("SELECT count(*) FROM materials").fetchone()[0]
    assert material_count == EXPECTED_COUNTS["materials"]


def test_raw_file_untouched_by_ingest(connection):
    before = DATA_PATH.read_bytes()
    ingest(connection, DATA_PATH)
    assert DATA_PATH.read_bytes() == before


def test_meta_stored_as_key_value(connection):
    ingest(connection, DATA_PATH)
    as_of_date = connection.execute(
        "SELECT value FROM meta WHERE key = 'as_of_date'"
    ).fetchone()
    assert as_of_date["value"] == "2026-08-01"
