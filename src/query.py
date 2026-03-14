# -*- coding: utf-8 -*-
"""
Main Q&A flow: intent -> retrieve -> Letta answer or "我不知道".
Calls ask_agent() when retrieval returns relevant chunks.
Supports DEBUG_RAG and trace_id for debugging.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from src.config import (
    DEBUG_RAG,
    DEBUG_RESPONSE_INCLUDE_CONTEXT,
    LETTA_AGENT_ID,
    RAG_SIMILARITY_THRESHOLD,
    RAG_TOP_K,
)
from src.embedding import embed_single
from src.intent import is_hr_handbook_related
from src.letta_agent import ask_agent
from src.vector_store import create_pool, search

logger = logging.getLogger(__name__)

ANSWER_UNKNOWN = "我不知道。"


def _unknown_for_question(question: str) -> str:
    """Return 'I don't know' in a language matching the question."""
    q = (question or "").strip()
    if any("一" <= ch <= "鿿" for ch in q):
        return "我不知道。"
    return "I don't know."


def _debug_log(trace_id: str, stage: str, data: dict[str, Any]) -> None:
    if not DEBUG_RAG:
        return
    logger.debug(
        "trace_id=%s stage=%s %s",
        trace_id,
        stage,
        json.dumps(data, ensure_ascii=False, default=str)[:2000],
    )


async def answer(
    question: str,
    pool=None,
    agent_id: str | None = None,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
    trace_id: str | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Answer one question. Returns dict with keys: answer, source, trace_id,
    and optionally debug (if DEBUG_RAG or debug=True).
    """
    tid = trace_id or str(uuid.uuid4())
    agent_id = agent_id or LETTA_AGENT_ID
    unknown = _unknown_for_question(question)
    close_pool = False
    if pool is None:
        pool = None

    debug_info: dict[str, Any] = {}
    if DEBUG_RAG or debug:
        debug_info["trace_id"] = tid
        debug_info["question"] = question

    try:
        related = is_hr_handbook_related(question)
        if DEBUG_RAG or debug:
            debug_info["intent_related"] = related
        _debug_log(tid, "intent", {"intent_related": related})

        if not related:
            return {
                "answer": unknown,
                "source": "intent_not_related",
                "trace_id": tid,
                **({"debug": debug_info} if (DEBUG_RAG or debug or DEBUG_RESPONSE_INCLUDE_CONTEXT) else {}),
            }

        if pool is None:
            pool = await create_pool()
            close_pool = True

        try:
            query_embedding = embed_single(question)
        except Exception as e:
            logger.exception("Embedding failed: %s", e)
            if DEBUG_RAG or debug:
                debug_info["embed_error"] = str(e)
            return {
                "answer": unknown,
                "source": "embed_error",
                "trace_id": tid,
                **({"debug": debug_info} if (DEBUG_RAG or debug) else {}),
            }

        hits = await search(
            pool,
            query_embedding,
            top_k=top_k or RAG_TOP_K,
            similarity_threshold=similarity_threshold or RAG_SIMILARITY_THRESHOLD,
        )

        if DEBUG_RAG or debug:
            debug_info["retrieval"] = {
                "top_k": top_k or RAG_TOP_K,
                "similarity_threshold": similarity_threshold or RAG_SIMILARITY_THRESHOLD,
                "num_hits": len(hits),
                "hits": [
                    {
                        "chapter_title": h.get("chapter_title"),
                        "similarity": round(h.get("similarity", 0), 4),
                        "content_preview": (h.get("content") or "")[:200],
                    }
                    for h in hits
                ],
            }
        _debug_log(tid, "retrieval", debug_info.get("retrieval", {}))

        if not hits:
            return {
                "answer": unknown,
                "source": "no_relevant_chunks",
                "trace_id": tid,
                **({"debug": debug_info} if (DEBUG_RAG or debug or DEBUG_RESPONSE_INCLUDE_CONTEXT) else {}),
            }

        context = "\n\n---\n\n".join(h.get("content", "") for h in hits)
        if DEBUG_RAG or debug:
            debug_info["context_preview"] = context[:500] + "..." if len(context) > 500 else context

        if not agent_id:
            logger.warning("LETTA_AGENT_ID not set; returning context only for debug")
            return {
                "answer": unknown,
                "source": "no_agent",
                "trace_id": tid,
                **({"debug": debug_info} if (DEBUG_RAG or debug) else {}),
            }

        try:
            reply = ask_agent(agent_id, context, question)
        except Exception as e:
            logger.exception("Letta agent call failed: %s", e)
            if DEBUG_RAG or debug:
                debug_info["agent_error"] = str(e)
            return {
                "answer": unknown,
                "source": "agent_error",
                "trace_id": tid,
                **({"debug": debug_info} if (DEBUG_RAG or debug) else {}),
            }

        if DEBUG_RAG or debug:
            debug_info["agent_reply"] = reply
        _debug_log(tid, "agent_reply", {"agent_reply": reply[:300] if reply else ""})

        return {
            "answer": reply.strip() or unknown,
            "source": "agent",
            "trace_id": tid,
            **({"debug": debug_info} if (DEBUG_RAG or debug or DEBUG_RESPONSE_INCLUDE_CONTEXT) else {}),
        }
    finally:
        if close_pool and pool:
            await pool.close()


async def run_chat_loop() -> None:
    """交互式命令行问答循环。"""
    pool = await create_pool()
    print("HR 手册问答 (输入 exit 或 quit 退出)")
    print("---")
    try:
        while True:
            try:
                q = input("你: ").strip()
            except EOFError:
                break
            if not q:
                continue
            if q.lower() in ("exit", "quit"):
                break
            result = await answer(q, pool=pool)
            print("助手:", result.get("answer") or _unknown_for_question(q))
            if result.get("debug") and DEBUG_RAG:
                print("[DEBUG]", json.dumps(result["debug"], ensure_ascii=False, indent=2)[:1500])
    finally:
        await pool.close()


if __name__ == "__main__":
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.config import LOG_LEVEL

    parser = argparse.ArgumentParser(description="HR handbook Q&A")
    parser.add_argument("--debug", action="store_true", help="Include debug info in responses")
    parser.add_argument("--single", type=str, metavar="QUESTION", help="Single question (no loop)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if args.single:
        async def _one():
            r = await answer(args.single, debug=args.debug)
            print(r.get("answer") or _unknown_for_question(args.single))
            if r.get("debug"):
                print(json.dumps(r["debug"], ensure_ascii=False, indent=2))
        asyncio.run(_one())
    else:
        asyncio.run(run_chat_loop())
