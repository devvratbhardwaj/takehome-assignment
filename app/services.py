import sqlite3

# spec_grade is nullable; without COALESCE the whole haystack would be NULL.
_HAYSTACK = "lower(sku || ' ' || description || ' ' || coalesce(spec_grade, '') || ' ' || category)"

# Only units the feed's descriptions actually use.
_UNIT_SYNONYMS = {"inch": "in", "inches": "in", "foot": "ft", "feet": "ft"}

_EDGE_PUNCTUATION = "\"'.,()!?"

_PARTIAL_MATCH_LIMIT = 5


def _with_presentation_fields(row: sqlite3.Row, match: str | None = None) -> dict:
    material = dict(row)
    material["orderable_qty"] = max(0, material["qty_available"])
    material["over_allocated"] = material["qty_available"] < 0
    if match is not None:
        material["match"] = match
    return material


def _normalize_tokens(query: str) -> list[str]:
    tokens = []
    for raw in query.lower().split():
        token = raw.strip(_EDGE_PUNCTUATION)
        token = _UNIT_SYNONYMS.get(token, token)
        # Single characters ("x" in "3/4 x 2") match nearly every row.
        if len(token) > 1:
            tokens.append(token)
    return tokens


def _token_clauses(tokens: list[str]) -> tuple[list[str], dict]:
    clauses = []
    params: dict = {}
    for index, token in enumerate(tokens):
        variants = [token]
        # Naive plural: "rebars" must also try "rebar".
        if token.endswith("s") and len(token) > 3:
            variants.append(token[:-1])
        likes = []
        for variant_index, variant in enumerate(variants):
            key = f"token{index}_{variant_index}"
            likes.append(f"{_HAYSTACK} LIKE :{key}")
            params[key] = f"%{variant}%"
        clauses.append("(" + " OR ".join(likes) + ")")
    return clauses, params


def search_materials(
    connection: sqlite3.Connection,
    query: str,
    category: str | None = None,
) -> list[dict]:
    tokens = _normalize_tokens(query)
    if not tokens:
        return []
    clauses, params = _token_clauses(tokens)
    category_filter = ""
    if category is not None:
        category_filter = " AND lower(category) = lower(:category)"
        params["category"] = category
    exact_sql = (
        "SELECT * FROM materials_with_availability WHERE "
        + " AND ".join(clauses)
        + category_filter
        + " ORDER BY sku"
    )
    rows = connection.execute(exact_sql, params).fetchall()
    if rows:
        return [_with_presentation_fields(row, match="exact") for row in rows]
    if len(clauses) < 2:
        return []
    # Near-misses for the agent to offer as alternatives, best-matching first.
    score = " + ".join(f"({clause})" for clause in clauses)
    partial_sql = (
        "SELECT * FROM materials_with_availability WHERE ("
        + " OR ".join(clauses)
        + ")"
        + category_filter
        + f" ORDER BY {score} DESC, sku LIMIT {_PARTIAL_MATCH_LIMIT}"
    )
    return [
        _with_presentation_fields(row, match="partial")
        for row in connection.execute(partial_sql, params)
    ]


def get_stock(connection: sqlite3.Connection, sku: str) -> dict | None:
    row = connection.execute(
        "SELECT * FROM materials_with_availability WHERE sku = :sku COLLATE NOCASE",
        {"sku": sku},
    ).fetchone()
    if row is None:
        return None
    stock = _with_presentation_fields(row)
    stock["needs_reorder"] = stock["qty_available"] <= stock["reorder_point"]
    return stock


def _order_context(
    connection: sqlite3.Connection, sku: str, quantity: int
) -> tuple[dict | None, dict | None]:
    if quantity < 1:
        return None, {
            "status": "rejected",
            "reason": "invalid_quantity",
            "sku": sku,
            "requested_qty": quantity,
        }
    stock = get_stock(connection, sku)
    if stock is None:
        return None, {"status": "rejected", "reason": "unknown_sku", "sku": sku}
    if stock["discontinued"]:
        return stock, {
            "status": "rejected",
            "reason": "discontinued",
            "sku": stock["sku"],
        }
    return stock, None


def quote_order(connection: sqlite3.Connection, sku: str, quantity: int) -> dict:
    stock, rejection = _order_context(connection, sku, quantity)
    if rejection is not None:
        return rejection
    return {
        "status": "quote",
        "sku": stock["sku"],
        "quantity": quantity,
        "unit_price": stock["unit_price"],
        "line_total": round(stock["unit_price"] * quantity, 2),
        "currency": stock["currency"],
        "fulfillable": quantity <= stock["orderable_qty"],
        "orderable_qty": stock["orderable_qty"],
    }


def place_order(connection: sqlite3.Connection, sku: str, quantity: int) -> dict:
    ## Write lock up front: the availability check and the reserve bump must be
    ## one atomic unit, or two concurrent orders can both pass the check and oversell.
    connection.execute("BEGIN IMMEDIATE")
    try:
        stock, rejection = _order_context(connection, sku, quantity)
        if rejection is not None:
            return rejection
        # Canonical casing for the insert; get_stock matches case-insensitively.
        sku = stock["sku"]
        if quantity > stock["orderable_qty"]:
            return {
                "status": "rejected",
                "reason": "insufficient_stock",
                "sku": sku,
                "requested_qty": quantity,
                "orderable_qty": stock["orderable_qty"],
                "qty_available": stock["qty_available"],
                "over_allocated": stock["over_allocated"],
            }
        line_total = round(stock["unit_price"] * quantity, 2)
        cursor = connection.execute(
            "INSERT INTO orders (sku, quantity, unit_price, line_total)"
            " VALUES (:sku, :quantity, :unit_price, :line_total)",
            {
                "sku": sku,
                "quantity": quantity,
                "unit_price": stock["unit_price"],
                "line_total": line_total,
            },
        )
        connection.execute(
            "UPDATE materials SET qty_reserved = qty_reserved + :quantity WHERE sku = :sku",
            {"quantity": quantity, "sku": sku},
        )
        connection.commit()
        return {
            "status": "confirmed",
            "order_id": cursor.lastrowid,
            "sku": sku,
            "quantity": quantity,
            "unit_price": stock["unit_price"],
            "line_total": line_total,
            "currency": stock["currency"],
        }
    finally:
        if connection.in_transaction:
            connection.rollback()


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
        clauses.append("lower(materials.category) = lower(:category)")
        params["category"] = category
    if supplier_id is not None:
        clauses.append("suppliers.supplier_id = :supplier_id")
        params["supplier_id"] = supplier_id
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY suppliers.supplier_id"
    return [dict(row) for row in connection.execute(query, params)]
