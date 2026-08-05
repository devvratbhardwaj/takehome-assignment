import json

from app import services
from app.db import get_connection

from langchain.tools import tool


def _annotated(material: dict) -> dict:
    if material["over_allocated"]:
        material["note"] = (
            "Reserved stock exceeds on-hand stock; nothing can be promised"
            " until existing reservations are resolved."
        )
    return material


@tool
def search_materials(query: str) -> str:
    """Search the materials catalogue by keywords matched against SKU,
    description, spec grade and category. Every keyword must match, so
    prefer few, specific words describing the material itself; an empty
    result means no such material exists — never substitute a different
    one."""
    connection = get_connection()
    try:
        results = services.search_materials(connection, query)
    finally:
        connection.close()
    return json.dumps([_annotated(material) for material in results])


@tool
def get_stock(sku: str) -> str:
    """Look up one material by exact SKU: stock levels, availability,
    pricing and supplier. Returns an unknown_sku error for SKUs not in
    the catalogue."""
    connection = get_connection()
    try:
        stock = services.get_stock(connection, sku)
    finally:
        connection.close()
    if stock is None:
        return json.dumps({"error": "unknown_sku", "sku": sku})
    return json.dumps(_annotated(stock))


@tool
def quote_order(sku: str, quantity: int) -> str:
    """Price a quantity of a material without ordering or reserving anything.
    Use this for every price/cost question. The quote carries the computed
    line_total plus a fulfillable flag and orderable_qty showing whether the
    quantity could actually be shipped. Rejections (unknown_sku, discontinued,
    invalid_quantity) mirror place_order."""
    connection = get_connection()
    try:
        return json.dumps(services.quote_order(connection, sku, quantity))
    finally:
        connection.close()


@tool
def place_order(sku: str, quantity: int) -> str:
    """Place an order for a material. Only call when the user clearly asks to
    order; use quote_order for price questions. Rejections carry a structured
    reason (unknown_sku, discontinued, insufficient_stock, invalid_quantity);
    relay it faithfully — never retry with altered numbers."""
    connection = get_connection()
    try:
        return json.dumps(services.place_order(connection, sku, quantity))
    finally:
        connection.close()


@tool
def get_suppliers(supplier_id: str | None = None, category: str | None = None) -> str:
    """List suppliers with lead times and payment terms, optionally filtered
    by supplier_id (format SUP-001) or by the material category they primarily
    supply (same category values as search_materials; some categories have two
    suppliers — report all rows). No filters returns all nine suppliers, which
    is cheap — use that to resolve a supplier by name."""
    connection = get_connection()
    try:
        return json.dumps(services.get_suppliers(connection, supplier_id, category))
    finally:
        connection.close()
