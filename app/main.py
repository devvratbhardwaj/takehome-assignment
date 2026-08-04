from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.db import get_connection
from app.ingest import ingest


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection = get_connection()
    ingest(connection)
    connection.close()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(router)
