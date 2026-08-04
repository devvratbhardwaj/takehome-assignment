import json
import sqlite3
from pathlib import Path

from app.db import get_connection, init_schema
from app.models import InventoryData


DATA_PATH = Path(__file__).resolve().parent.parent / "raw_data" / "inventory_data.json"


def ingest(
    connection: sqlite3.Connection, json_path: str | Path = DATA_PATH
) -> dict[str, int]:

    ## Validating before touching the DB
    data = InventoryData.model_validate_json(Path(json_path).read_text())

    init_schema(connection)

    meta = data.meta.model_dump()
    meta["definitions"] = json.dumps(meta["definitions"])
    connection.executemany(
        "INSERT INTO meta (key, value) VALUES (?, ?)", list(meta.items())
    )
    connection.executemany(
        "INSERT INTO suppliers VALUES"
        " (:supplier_id, :name, :location, :standard_lead_time_days, :payment_terms)",
        [supplier.model_dump() for supplier in data.suppliers],
    )
    connection.executemany(
        "INSERT INTO materials VALUES"
        " (:sku, :description, :category, :spec_grade, :unit_of_measure, :unit_price,"
        " :currency, :qty_on_hand, :qty_reserved, :reorder_point, :min_order_qty,"
        " :primary_supplier_id, :warehouse, :discontinued)",
        [material.model_dump() for material in data.materials],
    )
    connection.commit()
    return {"suppliers": len(data.suppliers), "materials": len(data.materials)}


if __name__ == "__main__":
    connection = get_connection()
    counts = ingest(connection)
    connection.close()
    print(f"Ingested {counts['suppliers']} suppliers, {counts['materials']} materials")
