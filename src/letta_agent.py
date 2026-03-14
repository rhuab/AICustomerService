# -*- coding: utf-8 -*-

"""Letta agent for HR handbook Q&A (Standard RAG: context injected by app)."""
from __future__ import annotations

import logging
from typing import Any

from letta_client import Letta

from src.config import LETTA_API_KEY

logger = logging.getLogger(__name__)

PERSONA = """你是一个基于公司HR手册的问答助手。请仅根据下面提供的「知识库上下文」回答用户问题。
如果上下文中没有与问题相关的内容，或信息不足，请明确回答「我不知道」。
不要编造或推测手册中未出现的内容。
无论用户使用什么语言提问，请尽量使用与用户问题相同的语言进行回答；如果无法判断，则使用中文作答。"""


def get_client() -> Letta:
    if not LETTA_API_KEY:
        raise ValueError("LETTA_API_KEY is not set")
    return Letta(api_key=LETTA_API_KEY)


def create_hr_agent(client: Letta | None = None) -> Any:
    """Create the HR handbook agent. Returns agent object with .id."""
    c = client or get_client()
    agent = c.agents.create(
        name="HR Handbook Assistant",
        description="Answers questions based on provided HR handbook context only.",
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
        ],
    )
    logger.info("Created agent: %s (id=%s)", agent.name, agent.id)
    return agent


def ask_agent(
    agent_id: str,
    context: str,
    question: str,
    client: Letta | None = None,
) -> str:
    """Send context + question to the agent and return the assistant reply text."""
    c = client or get_client()
    prompt = (
        "知识库上下文：\n"
        f"{context}\n\n"
        f"用户问题：{question}\n\n"
        "请根据上述上下文回答，并使用与用户问题相同的语言作答；"
        "若无关或不足则用相同语言表达“我不知道”。"
    )
    response = c.agents.messages.create(
        agent_id=agent_id,
        messages=[{"role": "user", "content": prompt}],
    )
    for msg in response.messages:
        if getattr(msg, "message_type", None) == "assistant_message":
            return getattr(msg, "content", "") or ""
    return ""
