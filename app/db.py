import os
import sqlite3
from pathlib import Path

# Drop-and-recreate on purpose: the JSON file is the source of truth for data, this DB is a rebuildable copy.
SCHEMA = """
DROP VIEW IF EXISTS materials_with_availability;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS materials;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS meta;

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE suppliers (
    supplier_id             TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    location                TEXT NOT NULL,
    standard_lead_time_days INTEGER NOT NULL,
    payment_terms           TEXT NOT NULL
);

CREATE TABLE materials (
    sku                 TEXT PRIMARY KEY,
    description         TEXT NOT NULL,
    category            TEXT NOT NULL,
    spec_grade          TEXT,
    unit_of_measure     TEXT NOT NULL,
    unit_price          REAL NOT NULL CHECK (unit_price >= 0),
    currency            TEXT NOT NULL,
    qty_on_hand         INTEGER NOT NULL CHECK (qty_on_hand >= 0),
    qty_reserved        INTEGER NOT NULL CHECK (qty_reserved >= 0),
    reorder_point       INTEGER NOT NULL,
    min_order_qty       INTEGER NOT NULL,
    primary_supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    warehouse           TEXT NOT NULL,
    discontinued        INTEGER NOT NULL CHECK (discontinued IN (0, 1))
);

CREATE TABLE orders (
    order_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    sku        TEXT NOT NULL REFERENCES materials(sku),
    quantity   INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL,
    line_total REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- qty_available is computed fresh on every read, never stored.
CREATE VIEW materials_with_availability AS
SELECT
    materials.*,
    materials.qty_on_hand - materials.qty_reserved AS qty_available
FROM materials;
"""


def get_connection(database_path: str | Path | None = None) -> sqlite3.Connection:
    if database_path is None:
        database_path = os.environ.get("INVENTORY_DB", "inventory.db")
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
