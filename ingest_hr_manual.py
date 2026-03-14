"""
Ingest HR.pdf: chunk by chapters, embed, store in PostgreSQL (pgvector).
Idempotent: deletes existing HR.pdf source rows before insert.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.chunking import chunk_hr_manual
from src.config import HR_PDF_PATH, LOG_LEVEL
from src.embedding import embed_texts
from src.vector_store import (
    create_pool,
    delete_by_source,
    ensure_extension_and_table,
    insert_chunks,
)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    pdf_path = Path(HR_PDF_PATH)
    if not pdf_path.is_file():
        logger.error("PDF not found: %s", pdf_path)
        sys.exit(1)

    logger.info("Chunking PDF: %s", pdf_path)
    chunks = chunk_hr_manual(pdf_path)
    logger.info("Chunks: %d", len(chunks))
    if not chunks:
        logger.warning("No chunks produced; check PDF content and chapter patterns.")
        return

    texts = [c["text"] for c in chunks]
    logger.info("Embedding %d texts...", len(texts))
    embeddings = embed_texts(texts)
    if len(embeddings) != len(chunks):
        logger.error("Embedding count mismatch")
        sys.exit(1)

    pool = await create_pool()
    try:
        await ensure_extension_and_table(pool)
        deleted = await delete_by_source(pool)
        logger.info("Deleted %d existing rows for source", deleted)
        await insert_chunks(pool, chunks, embeddings)
    finally:
        await pool.close()

    logger.info("Ingestion complete. Total chunks in DB: %d", len(chunks))


if __name__ == "__main__":
    asyncio.run(main())
