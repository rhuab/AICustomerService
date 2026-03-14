# -*- coding: utf-8 -*-

"""Configuration from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# API keys
LETTA_API_KEY: str = os.getenv("LETTA_API_KEY", "").strip()
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
# Set after creating agent once (e.g. run create_agent.py)
LETTA_AGENT_ID: str = os.getenv("LETTA_AGENT_ID", "").strip()

# PostgreSQL
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://localhost:5432/hr_rag",
).strip()

# Embedding
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIM: int = 1536  # text-embedding-3-small

# RAG (configurable)
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


RAG_TOP_K: int = _int_env("RAG_TOP_K", 5)
# Cosine similarity threshold: only chunks with similarity >= this are used (0..1)
RAG_SIMILARITY_THRESHOLD: float = _float_env("RAG_SIMILARITY_THRESHOLD", 0.7)

# Debug
DEBUG_RAG: bool = os.getenv("DEBUG_RAG", "false").lower() in ("true", "1", "yes")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
DEBUG_RESPONSE_INCLUDE_CONTEXT: bool = os.getenv(
    "DEBUG_RESPONSE_INCLUDE_CONTEXT", "false"
).lower() in ("true", "1", "yes")

# HR PDF source (for ingestion)
HR_PDF_PATH: str = os.getenv("HR_PDF_PATH", "HR.pdf").strip()

# Web server
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0").strip()
SERVER_PORT: int = _int_env("SERVER_PORT", 8000)
ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "").strip()
