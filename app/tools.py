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
def search_materials(query: str, category: str | None = None) -> str:
    """Search the materials catalogue by keywords matched against SKU,
    description, spec grade and category. An empty result means no such
    material exists — never substitute a different one."""
    connection = get_connection()
    try:
        results = services.search_materials(connection, query, category)
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
def place_order(sku: str, quantity: int) -> str:
    """Place an order for a material. Rejections carry a structured reason
    (unknown_sku, discontinued, insufficient_stock, invalid_quantity);
    relay it faithfully — never retry with altered numbers."""
    connection = get_connection()
    try:
        return json.dumps(services.place_order(connection, sku, quantity))
    finally:
        connection.close()


@tool
def get_suppliers(supplier_id: str | None = None, category: str | None = None) -> str:
    """List suppliers with lead times and payment terms, optionally filtered
    by supplier_id or by the material category they primarily supply. No
    filters returns all suppliers."""
    connection = get_connection()
    try:
        return json.dumps(services.get_suppliers(connection, supplier_id, category))
    finally:
        connection.close()
