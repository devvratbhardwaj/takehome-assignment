import sqlite3


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
