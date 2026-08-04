import sqlite3
from collections.abc import Iterator

from fastapi import APIRouter, Depends

from app.db import get_connection
from app.services import get_suppliers

router = APIRouter(prefix="/api")


def db_connection() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()


@router.get("/suppliers")
def suppliers(
    supplier_id: str | None = None,
    category: str | None = None,
    connection: sqlite3.Connection = Depends(db_connection),
) -> list[dict]:
    return get_suppliers(connection, supplier_id=supplier_id, category=category)
