from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.agent import get_agent
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

INDEX_PAGE = Path(__file__).resolve().parent.parent / "static" / "index.html"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(INDEX_PAGE)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    messages = [message.model_dump() for message in request.history]
    messages.append({"role": "user", "content": request.message})
    result = get_agent().invoke({"messages": messages})
    return {"reply": result["messages"][-1].content}
