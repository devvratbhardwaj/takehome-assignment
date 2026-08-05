from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
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
