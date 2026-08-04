# Drop-and-recreate on purpose: the JSON file is the source of truth for data, this DB is a rebuildable copy.
SCHEMA = """
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
"""
