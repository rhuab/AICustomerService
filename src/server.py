# -*- coding: utf-8 -*-
"""FastAPI web server for HR handbook Q&A with per-user memory and admin API."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.config import ADMIN_API_KEY, DEBUG_RAG, LOG_LEVEL, SERVER_HOST, SERVER_PORT
from src.query import answer as rag_answer
from src.user_manager import user_manager
from src.vector_store import create_pool

logger = logging.getLogger(__name__)

_pool = None
_pool_lock = None


async def get_pool():
    """Lazy-init asyncpg pool on first use so the server can start without PG."""
    global _pool, _pool_lock
    if _pool is not None:
        return _pool
    import asyncio
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    async with _pool_lock:
        if _pool is not None:
            return _pool
        _pool = await create_pool()
        logger.info("asyncpg pool created (lazy init)")
        return _pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        _pool = await create_pool()
        logger.info("Server started, asyncpg pool ready")
    except Exception as e:
        logger.error("Could not connect to PostgreSQL on startup: %s.", e)
    yield
    if _pool is not None:
        await _pool.close()
        logger.info("Server stopped, pool closed")


app = FastAPI(
    title="HR Handbook Q&A",
    description="RAG-based HR handbook chatbot with per-user Letta memory",
    lifespan=lifespan,
)


# ── Request / Response models ──


class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, examples=["user_001"])
    question: str = Field(..., min_length=1, max_length=2000, examples=["annual leave policy?"])
    debug: bool = Field(False, description="Include debug info in response")


class AskResponse(BaseModel):
    answer: str
    source: str
    trace_id: str
    cached: bool = False
    debug: dict[str, Any] | None = None


class UserInfo(BaseModel):
    user_id: str
    agent_id: str
    created_at: float
    cached_questions: int


class ClearMemoryResponse(BaseModel):
    success: bool
    message: str


# ── Auth dependency ──


def require_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")) -> str:
    if not ADMIN_API_KEY:
        raise HTTPException(503, "ADMIN_API_KEY not configured on server")
    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(403, "Invalid admin key")
    return x_admin_key


# ── User Q&A endpoint ──


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    """Answer a user question. Uses per-user Letta agent with conversation memory.
    Returns cached result if the same question was asked before by this user."""
    cached = user_manager.get_cached_answer(req.user_id, req.question)
    if cached is not None:
        logger.info("Cache hit: user=%s question=%s", req.user_id, req.question[:60])
        return AskResponse(
            answer=cached.get("answer", ""),
            source="cache",
            trace_id=cached.get("trace_id", ""),
            cached=True,
            debug=cached.get("debug") if req.debug else None,
        )

    session = user_manager.get_or_create_session(req.user_id)
    tid = str(uuid.uuid4())

    pool = await get_pool()

    result = await rag_answer(
        question=req.question,
        pool=pool,
        agent_id=session.agent_id,
        trace_id=tid,
        debug=req.debug,
    )

    user_manager.cache_answer(req.user_id, req.question, result)

    return AskResponse(
        answer=result.get("answer", ""),
        source=result.get("source", ""),
        trace_id=result.get("trace_id", tid),
        cached=False,
        debug=result.get("debug") if req.debug else None,
    )


# ── Admin endpoints ──


@app.get("/api/admin/users", response_model=list[UserInfo], dependencies=[Depends(require_admin)])
async def list_users():
    """List all active user sessions."""
    return user_manager.list_users()


@app.delete("/api/admin/users/{user_id}/memory", response_model=ClearMemoryResponse, dependencies=[Depends(require_admin)])
async def clear_user_memory(user_id: str):
    """Clear a user's Letta agent and answer cache. The next question will create a fresh agent."""
    ok = user_manager.clear_user_memory(user_id)
    if ok:
        return ClearMemoryResponse(success=True, message=f"Memory cleared for user {user_id}")
    raise HTTPException(404, f"User {user_id} not found")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "timestamp": time.time(),
        "db_pool": "connected" if _pool is not None else "not_connected",
    }


# ── Entry point ──


def main():
    import uvicorn
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(
        "src.server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level=LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
