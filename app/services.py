import sqlite3


def _with_presentation_fields(row: sqlite3.Row) -> dict:
    material = dict(row)
    material["orderable_qty"] = max(0, material["qty_available"])
    material["over_allocated"] = material["qty_available"] < 0
    return material


def search_materials(
    connection: sqlite3.Connection,
    query: str,
    category: str | None = None,
) -> list[dict]:
    # spec_grade is nullable; without COALESCE the whole haystack would be NULL.
    haystack = "lower(sku || ' ' || description || ' ' || coalesce(spec_grade, '') || ' ' || category)"
    clauses = []
    params: dict = {}
    for index, token in enumerate(query.lower().split()):
        clauses.append(f"{haystack} LIKE :token{index}")
        params[f"token{index}"] = f"%{token}%"
    if not clauses:
        return []
    if category is not None:
        clauses.append("category = :category")
        params["category"] = category
    sql = (
        "SELECT * FROM materials_with_availability WHERE "
        + " AND ".join(clauses)
        + " ORDER BY sku"
    )
    return [_with_presentation_fields(row) for row in connection.execute(sql, params)]


def get_stock(connection: sqlite3.Connection, sku: str) -> dict | None:
    row = connection.execute(
        "SELECT * FROM materials_with_availability WHERE sku = :sku", {"sku": sku}
    ).fetchone()
    if row is None:
        return None
    stock = _with_presentation_fields(row)
    stock["needs_reorder"] = stock["qty_available"] <= stock["reorder_point"]
    return stock


def get_suppliers(
    connection: sqlite3.Connection,
    supplier_id: str | None = None,
    category: str | None = None,
) -> list[dict]:
    query = "SELECT DISTINCT suppliers.* FROM suppliers"
    clauses = []
    params = {}
    if category is not None:
        query += (
            " JOIN materials ON materials.primary_supplier_id = suppliers.supplier_id"
        )
        clauses.append("materials.category = :category")
        params["category"] = category
    if supplier_id is not None:
        clauses.append("suppliers.supplier_id = :supplier_id")
        params["supplier_id"] = supplier_id
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY suppliers.supplier_id"
    return [dict(row) for row in connection.execute(query, params)]
