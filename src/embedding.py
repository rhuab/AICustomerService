# -*- coding: utf-8 -*-

"""OpenAI embeddings for RAG."""
from __future__ import annotations

import logging

from openai import OpenAI

from src.config import EMBEDDING_MODEL, OPENAI_API_KEY

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def embed_texts(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """Embed a list of texts with OpenAI. Returns list of embedding vectors."""
    if not texts:
        return []
    client = _get_client()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        for e in sorted(resp.data, key=lambda x: x.index):
            all_embeddings.append(e.embedding)
        logger.debug("Embedded batch %d-%d", i, min(i + batch_size, len(texts)))
    return all_embeddings


def embed_single(text: str) -> list[float]:
    """Embed a single text. Returns one embedding vector."""
    return embed_texts([text])[0]
