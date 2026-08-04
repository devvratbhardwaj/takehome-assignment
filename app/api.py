import sqlite3
from collections.abc import Iterator

from fastapi import APIRouter, Depends

from app.db import get_connection
from app.services import get_suppliers, search_materials

router = APIRouter(prefix="/api")


def db_connection() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@router.get("/materials/search")
def materials_search(
    query: str,
    category: str | None = None,
    connection: sqlite3.Connection = Depends(db_connection),
) -> list[dict]:
    return search_materials(connection, query, category=category)


@router.get("/suppliers")
def suppliers(
    supplier_id: str | None = None,
    category: str | None = None,
    connection: sqlite3.Connection = Depends(db_connection),
) -> list[dict]:
    return get_suppliers(connection, supplier_id=supplier_id, category=category)
