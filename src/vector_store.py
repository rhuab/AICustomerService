# -*- coding: utf-8 -*-

"""Vector store using PostgreSQL + pgvector with asyncpg connection pool."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from src.config import (
    DATABASE_URL,
    EMBEDDING_DIM,
    RAG_SIMILARITY_THRESHOLD,
    RAG_TOP_K,
)

logger = logging.getLogger(__name__)

TABLE_NAME = "hr_chunks"
SOURCE_LABEL = "HR.pdf"


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Register pgvector type on each new connection in the pool."""
    await register_vector(conn)


def _get_conn_kwargs() -> dict[str, Any]:
    """Parse DATABASE_URL into asyncpg.connect kwargs if needed."""
    # asyncpg accepts dsn=DATABASE_URL directly
    return {"dsn": DATABASE_URL}


async def create_pool(
    min_size: int = 1,
    max_size: int = 10,
    **kwargs: Any,
) -> asyncpg.Pool:
    """Create asyncpg connection pool with pgvector registered."""
    pool = await asyncpg.create_pool(
        **_get_conn_kwargs(),
        min_size=min_size,
        max_size=max_size,
        init=_init_connection,
        **kwargs,
    )
    return pool


async def ensure_extension_and_table(pool: asyncpg.Pool) -> None:
    """Create vector extension and hr_chunks table if not exist."""
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await register_vector(conn)
        source_default = SOURCE_LABEL.replace("'", "''")
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                content text NOT NULL,
                embedding vector({EMBEDDING_DIM}) NOT NULL,
                chapter_title text,
                chapter_index int,
                chunk_index int,
                source text DEFAULT '{source_default}'
            )
            """
        )
    logger.info("Extension and table %s ready", TABLE_NAME)


async def delete_by_source(pool: asyncpg.Pool, source: str = SOURCE_LABEL) -> int:
    """Delete all rows with given source. Returns deleted count."""
    async with pool.acquire() as conn:
        await register_vector(conn)
        result = await conn.execute(
            f"DELETE FROM {TABLE_NAME} WHERE source = $1",
            source,
        )
    # Result like "DELETE 42"
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def insert_chunks(
    pool: asyncpg.Pool,
    chunks: list[dict[str, Any]],
    embeddings: list[list[float]],
    source: str = SOURCE_LABEL,
) -> None:
    """Insert chunk texts and their embeddings into the table."""
    if len(chunks) != len(embeddings):
        raise ValueError("chunks and embeddings length must match")
    async with pool.acquire() as conn:
        await register_vector(conn)
        for i, (chunk, emb) in enumerate[tuple[dict[str, Any], list[float]]](zip(chunks, embeddings)):
            await conn.execute(
                f"""
                INSERT INTO {TABLE_NAME}
                (id, content, embedding, chapter_title, chapter_index, chunk_index, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                str(uuid.uuid4()),
                chunk.get("text", ""),
                emb,
                chunk.get("chapter_title"),
                chunk.get("chapter_index"),
                chunk.get("chunk_index"),
                source,
            )
        logger.info("Inserted %d chunks into %s", len(chunks), TABLE_NAME)


async def search(
    pool: asyncpg.Pool,
    query_embedding: list[float],
    top_k: int | None = None,
    similarity_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """
    Search for closest chunks by cosine distance.
    Returns list of dicts with content, chapter_title, chapter_index, distance, similarity.
    Only returns rows where similarity >= similarity_threshold.
    """
    k = top_k if top_k is not None else RAG_TOP_K
    thresh = similarity_threshold if similarity_threshold is not None else RAG_SIMILARITY_THRESHOLD
    # pgvector <=> is cosine distance; for normalized vectors similarity = 1 - distance
    # So we want distance <= (1 - thresh)
    max_distance = 1.0 - thresh

    async with pool.acquire() as conn:
        await register_vector(conn)
        rows = await conn.fetch(
            f"""
            SELECT content, chapter_title, chapter_index,
                   (embedding <=> $1::vector) AS distance
            FROM {TABLE_NAME}
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            query_embedding,
            k,
        )

    result = []
    for r in rows:
        distance = float(r["distance"])
        similarity = 1.0 - distance
        if similarity < thresh:
            continue
        result.append({
            "content": r["content"],
            "chapter_title": r["chapter_title"],
            "chapter_index": r["chapter_index"],
            "distance": distance,
            "similarity": similarity,
        })
    return result
